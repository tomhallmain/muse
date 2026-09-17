"""Bluesky (AT Protocol) feed client.

Reads configured feed generators through ``app.bsky.feed.getFeed``. Two access
paths, mirroring the Reddit client:

- The public AppView host, which is documented as serving read-only
  ``app.bsky.*`` queries with no authentication. Used when no credentials are
  configured, so the topic can work with nothing but a feed URI in config.
- An app password, exchanged for a session token via
  ``com.atproto.server.createSession``. Used when a handle and app password are
  configured. Unlike Reddit's client ID and secret, an app password acts as the
  account -- it is scoped so it cannot change the real password or delete the
  account, but it is a user credential.

Uses requests directly rather than the atproto SDK: these are two plain XRPC
calls, requests is already a dependency, and a session is created per fetch
rather than kept alive, so there is no token refresh to manage.

Named feeds rather than open search: a search term is a firehose with extra
steps, and the feed list is this topic's source allowlist.
"""

import random
import re
from typing import List, Optional

import requests

from extensions.social_filter import (
    SocialSourceUnusable,
    assemble_payload,
    filter_items,
    iso_age_hours,
    source_is_blacklisted,
)
from extensions.soup_utils import WebConnectionException
from utils.config import config
from utils.logging_setup import get_logger

logger = get_logger(__name__)

_USER_AGENT = "Muse/1.0"
_TIMEOUT_SECONDS = 10
# Read-only AppView; no account, no token.
_APPVIEW_HOST = "public.api.bsky.app"
# Where an app password is exchanged for a session token.
_PDS_HOST = "bsky.social"
# Feeds read per fetch, sampled from the configured list, as for subreddits.
_MAX_FEEDS_PER_FETCH = 3
# Post text carries URLs and handles literally; facets annotate byte ranges
# rather than replacing them, so neither may reach the LLM as written.
_URL = re.compile(r'https?://\S+|\b(?:www\.)\S+\.[a-z]{2,}(?:/\S*)?', re.IGNORECASE)
_HANDLE = re.compile(r'@[\w.-]+')
_WHITESPACE = re.compile(r'\s+')
# Labels that mean the post should not be surfaced at all, as opposed to merely
# being flagged. Any label at all already counts as sensitive.
_HIDE_LABELS = {"!hide", "!takedown", "!suspend"}


def visible_text(text: str) -> str:
    """The speakable text of a post, with handles and links removed.

    Hashtags are left as words; they read aloud fine and carry the subject.
    """
    if not text:
        return ""
    text = _URL.sub(' ', text)
    text = _HANDLE.sub(' ', text)
    return _WHITESPACE.sub(' ', text).strip()


def feed_name(feed_uri: str) -> str:
    """The readable part of a feed's AT-URI: its record key.

    ``at://did:plc:abc.../app.bsky.feed.generator/whats-hot`` -> ``whats-hot``.
    This is what the source blacklist matches and what the payload names, since
    the URI itself says nothing a listener would recognise.
    """
    return (feed_uri or "").rstrip("/").rsplit("/", 1)[-1]


class BlueskyItem:
    """One post from a feed, reduced to the fields that may be spoken."""

    def __init__(self, post: dict, feed: str):
        record = post.get("record") or {}
        author = post.get("author") or {}
        self.source = "Bluesky"
        self.feed = feed
        self.title = visible_text(record.get("text") or "")
        self.score = int(post.get("likeCount") or 0) + int(post.get("repostCount") or 0)
        self.replies = int(post.get("replyCount") or 0)
        self.age_hours = iso_age_hours(post.get("indexedAt") or record.get("createdAt"))
        langs = record.get("langs") or []
        self.language = str(langs[0]) if langs else ""
        # Any label is a moderation signal, whatever its value: the label set
        # grows, and a post someone has labelled is not one to read out.
        labels = [str(label.get("val") or "") for label in
                  (post.get("labels") or []) + (author.get("labels") or [])]
        self.sensitive = bool(labels)
        self.restricted = any(label in _HIDE_LABELS for label in labels)
        self.filter_text = "\n".join([self.title, " ".join(labels), feed])

    def _age_str(self) -> str:
        if self.age_hours < 2:
            return "in the last hour"
        if self.age_hours < 24:
            return f"{int(self.age_hours)} hours ago"
        return "yesterday"

    def _engagement_str(self) -> str:
        if self.score < 100:
            return ""
        if self.score < 1000:
            return " (some engagement)"
        return " (very high engagement)"

    def __str__(self):
        return f"{self.title} (posted to {self.source} {self._age_str()}){self._engagement_str()}"


class BlueskyAPI:

    def __init__(self, feeds: Optional[List[str]] = None) -> None:
        configured = feeds if feeds is not None else config.bluesky_feeds
        self.feeds = [uri.strip() for uri in configured if uri and uri.strip()]
        self._token = None

    def _has_credentials(self) -> bool:
        return bool(config.bluesky_handle) and bool(config.bluesky_app_password)

    def _allowed_feeds(self) -> List[str]:
        """The configured feed list, minus blacklisted names, sampled down.

        The feed list is the source gate for this topic; there is no path here
        that reads an unfiltered firehose.
        """
        allowed = [uri for uri in self.feeds if not source_is_blacklisted(feed_name(uri))]
        if not allowed:
            raise SocialSourceUnusable(
                "No Bluesky feeds are configured (bluesky_feeds)" if not self.feeds
                else "Every configured Bluesky feed is blacklisted"
            )
        if len(allowed) > _MAX_FEEDS_PER_FETCH:
            allowed = random.sample(allowed, _MAX_FEEDS_PER_FETCH)
        return allowed

    def _session_token(self) -> str:
        """A session token for the configured app password, created once.

        Tokens are short-lived, and a fetch happens once every few hours, so one
        is created per client rather than refreshed.
        """
        if self._token is not None:
            return self._token
        url = f"https://{_PDS_HOST}/xrpc/com.atproto.server.createSession"
        try:
            response = requests.post(
                url,
                json={"identifier": config.bluesky_handle,
                      "password": config.bluesky_app_password},
                headers={"User-Agent": _USER_AGENT},
                timeout=_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise WebConnectionException(f"Failed to reach {url}: {e}")
        if response.status_code in (400, 401, 403):
            raise SocialSourceUnusable(
                f"Bluesky rejected the app password for {config.bluesky_handle} "
                f"(HTTP {response.status_code}); check bluesky_app_password"
            )
        if not response.ok:
            raise WebConnectionException(f"{url} returned HTTP {response.status_code}")
        try:
            token = (response.json() or {}).get("accessJwt")
        except ValueError as e:
            raise WebConnectionException(f"{url} returned unreadable JSON: {e}")
        if not token:
            raise WebConnectionException(f"{url} returned no access token")
        self._token = token
        return token

    def _get_feed(self, feed_uri: str, limit: int) -> List[dict]:
        """The ``feed`` array for one feed generator.

        The AppView host answers without credentials; the PDS host needs the
        session token. Which one is used follows from whether an app password is
        configured.
        """
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        if self._has_credentials():
            host = _PDS_HOST
            headers["Authorization"] = f"Bearer {self._session_token()}"
        else:
            host = _APPVIEW_HOST
        url = f"https://{host}/xrpc/app.bsky.feed.getFeed"
        try:
            response = requests.get(
                url,
                params={"feed": feed_uri, "limit": limit},
                headers=headers,
                timeout=_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise WebConnectionException(f"Failed to reach {url}: {e}")
        if response.status_code in (401, 403):
            raise SocialSourceUnusable(
                f"{host} refused an unauthenticated read (HTTP {response.status_code}); "
                f"configure bluesky_handle and bluesky_app_password"
            )
        if response.status_code == 400:
            # An unknown or deleted feed generator reports as a bad request.
            raise SocialSourceUnusable(
                f"Bluesky does not recognise the feed {feed_uri}; check bluesky_feeds"
            )
        if not response.ok:
            raise WebConnectionException(f"{url} returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as e:
            raise WebConnectionException(f"{url} returned unreadable JSON: {e}")
        feed = (payload or {}).get("feed")
        if not isinstance(feed, list):
            raise WebConnectionException(f"{url} returned no feed")
        return feed

    def get_items(self, limit_per_feed: int = 30) -> List[BlueskyItem]:
        feeds = self._allowed_feeds()
        # Authenticate before the loop. A credential failure is not a per-feed
        # problem -- no feed will answer -- so it is raised as itself rather
        # than counted as one feed skipped, and a rejected login is attempted
        # once instead of once per feed.
        if self._has_credentials():
            self._session_token()
        items: List[BlueskyItem] = []
        failures = []
        reasons = []
        for feed_uri in feeds:
            name = feed_name(feed_uri)
            try:
                entries = self._get_feed(feed_uri, limit_per_feed)
            except (WebConnectionException, SocialSourceUnusable) as e:
                # One unreachable or unknown feed should not lose the rest.
                logger.warning(f"Skipping Bluesky feed {name}: {e}")
                failures.append(name)
                if str(e) not in reasons:
                    reasons.append(str(e))
                continue
            for entry in entries:
                post = (entry or {}).get("post")
                if isinstance(post, dict):
                    items.append(BlueskyItem(post, name))
        if not items:
            raise SocialSourceUnusable(
                f"No posts were returned from {failures}: {'; '.join(reasons)}"
                if failures else "No posts were returned"
            )
        return items

    @staticmethod
    def _without_reposts(items: List[BlueskyItem]) -> List[BlueskyItem]:
        """One post surfacing in two feeds is one post. Deduplicated before the
        shared filter, so a repeat does not spend the attrition budget."""
        seen = set()
        unique = []
        for item in items:
            if item.title and item.title not in seen:
                seen.add(item.title)
                unique.append(item)
        return unique

    def _in_configured_language(self, items: List[BlueskyItem]) -> List[BlueskyItem]:
        """Items the DJ can read out. A feed is multilingual, and an unset
        language is left in rather than guessed at."""
        allowed = [code.lower() for code in config.bluesky_languages]
        if not allowed:
            return items
        return [i for i in items
                if not i.language or i.language.lower().split("-")[0] in allowed]

    def get_news(self, total: int = 12) -> str:
        """The filtered payload for the prompt.

        Named to match the other sources so the topic handler dispatches the
        same way for all of them.
        """
        items = self._without_reposts(self._in_configured_language(self.get_items()))
        items = filter_items(
            items,
            min_score=config.bluesky_min_score,
            max_age_hours=config.bluesky_max_age_hours,
            min_surviving=config.social_min_surviving_items,
            max_rejection_ratio=config.social_max_rejection_ratio,
        )
        items.sort(key=lambda item: item.score, reverse=True)
        feeds = sorted({item.feed for item in items})
        return assemble_payload(
            f"Posts people are sharing today on Bluesky (feeds: {', '.join(feeds)}):",
            items, total=total,
        )
