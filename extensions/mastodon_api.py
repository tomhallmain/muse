"""Mastodon trending-posts client.

Reads ``/api/v1/trends/statuses`` from a configured instance. That endpoint
needs no account, no app registration and no token on an instance that leaves
public read open, so this source works with nothing but a hostname in config.

Uses requests directly rather than Mastodon.py: the whole client is one
unauthenticated GET, and requests is already a dependency.
"""

import html
import re
from typing import List

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
# Mastodon renders mentions, hashtags and links as anchors. Hashtag anchors
# carry "hashtag" in their class and their text is a word worth keeping; every
# other anchor is a handle or a URL, neither of which may reach the LLM.
_HASHTAG_ANCHOR = re.compile(r'<a\b[^>]*class="[^"]*hashtag[^"]*"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_ANY_ANCHOR = re.compile(r'<a\b[^>]*>.*?</a>', re.IGNORECASE | re.DOTALL)
_BLOCK_BOUNDARY = re.compile(r'</p>|<br\s*/?>', re.IGNORECASE)
_ANY_TAG = re.compile(r'<[^<]+?>')
_WHITESPACE = re.compile(r'\s+')


def visible_text(content_html: str) -> str:
    """The speakable text of a status, with handles and URLs removed.

    Block boundaries become spaces first, or stripping the tags would run the
    last word of a paragraph into the first word of the next. Entities are
    unescaped but percent sequences are left alone, being literal in post text.
    """
    if not content_html:
        return ""
    text = _HASHTAG_ANCHOR.sub(r'\1', content_html)
    text = _ANY_ANCHOR.sub(' ', text)
    text = _BLOCK_BOUNDARY.sub(' ', text)
    text = _ANY_TAG.sub('', text)
    return _WHITESPACE.sub(' ', html.unescape(text)).strip()


class MastodonItem:
    """One trending status, reduced to the fields that may be spoken."""

    def __init__(self, status: dict, instance: str):
        self.source = instance
        self.title = visible_text(status.get("content", ""))
        self.score = int(status.get("reblogs_count") or 0) + int(status.get("favourites_count") or 0)
        self.language = status.get("language") or ""
        self.age_hours = iso_age_hours(status.get("created_at"))
        # A content warning is the author saying the post needs one, so it is
        # treated the same as the instance's own sensitive flag.
        self.sensitive = bool(status.get("sensitive")) or bool((status.get("spoiler_text") or "").strip())
        self.restricted = status.get("visibility", "public") != "public"
        self.filter_text = "\n".join([
            self.title,
            status.get("spoiler_text") or "",
            " ".join(tag.get("name", "") for tag in status.get("tags") or []),
        ])

    def _age_str(self) -> str:
        if self.age_hours < 2:
            return "in the last hour"
        if self.age_hours < 24:
            return f"{int(self.age_hours)} hours ago"
        return "yesterday"

    def _engagement_str(self) -> str:
        if self.score < 50:
            return ""
        if self.score < 200:
            return " (some engagement)"
        return " (very high engagement)"

    def __str__(self):
        return f"{self.title} (posted on {self.source} {self._age_str()}){self._engagement_str()}"


class MastodonAPI:

    def __init__(self, instance: str = "") -> None:
        self.instance = (instance or config.mastodon_instance or "").strip().rstrip("/")
        self.instance = re.sub(r"^https?://", "", self.instance)

    def _endpoint(self) -> str:
        return f"https://{self.instance}/api/v1/trends/statuses"

    def get_items(self, limit: int = 40) -> List[MastodonItem]:
        """Trending statuses from the configured instance.

        The instance is the whole source allowlist for this topic, so a
        blacklisted instance name means no fetch at all.
        """
        if not self.instance:
            raise SocialSourceUnusable("No Mastodon instance is configured")
        if source_is_blacklisted(self.instance):
            raise SocialSourceUnusable(f"Mastodon instance is blacklisted: {self.instance}")

        url = self._endpoint()
        try:
            response = requests.get(
                url,
                params={"limit": limit},
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
                timeout=_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise WebConnectionException(f"Failed to reach {url}: {e}")
        if response.status_code == 401 or response.status_code == 403:
            raise SocialSourceUnusable(
                f"{self.instance} requires authentication for public reads "
                f"(HTTP {response.status_code})"
            )
        if not response.ok:
            raise WebConnectionException(f"{url} returned HTTP {response.status_code}")
        try:
            statuses = response.json()
        except ValueError as e:
            raise WebConnectionException(f"{url} returned unreadable JSON: {e}")
        if not isinstance(statuses, list):
            raise WebConnectionException(f"{url} returned {type(statuses).__name__}, expected a list")
        return [MastodonItem(status, self.instance) for status in statuses]

    def _in_configured_language(self, items: List[MastodonItem]) -> List[MastodonItem]:
        """Items the DJ can read out. A trending feed is multilingual, and an
        unset language is left in rather than guessed at."""
        allowed = [code.lower() for code in config.mastodon_languages]
        if not allowed:
            return items
        return [i for i in items if not i.language or i.language.lower().split("-")[0] in allowed]

    def get_news(self, total: int = 12) -> str:
        """The filtered payload for the prompt.

        Named to match HackerNewsSouper.get_news and NewsAPI.get_news so the
        topic handler dispatches the same way for all three.
        """
        items = self._in_configured_language(self.get_items())
        items = filter_items(
            items,
            min_score=config.mastodon_min_score,
            max_age_hours=config.mastodon_max_age_hours,
            min_surviving=config.social_min_surviving_items,
            max_rejection_ratio=config.social_max_rejection_ratio,
        )
        items.sort(key=lambda i: i.score, reverse=True)
        return assemble_payload(
            f"Posts people are sharing today on {self.instance}:", items, total=total
        )
