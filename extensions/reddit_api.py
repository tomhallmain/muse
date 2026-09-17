"""Reddit top-submission client.

Two fetch paths, both free:

- PRAW with a registered script app's client ID and secret. The app-only grant
  carries no user scopes, so no account credentials are stored and
  ``reddit.read_only`` is True. Used when both keys are configured and praw is
  installed.
- The public ``/top.json`` listing, which needs no credentials at all. Used
  otherwise, so the topic works before any setup. Reddit rate-limits it and
  refuses datacenter address ranges, so it cannot be the only path.

Both paths produce the same listing dicts, which RedditItem parses.
"""

import random
import time
from typing import List, Optional

import requests

from extensions.social_filter import (
    SocialSourceUnusable,
    assemble_payload,
    filter_items,
    source_is_blacklisted,
)
from extensions.soup_utils import WebConnectionException
from utils.config import config
from utils.logging_setup import get_logger

logger = get_logger(__name__)

# Reddit asks for a descriptive agent and throttles generic ones harder.
_USER_AGENT = "python:muse:1.0 (Muse desktop music player)"
_TIMEOUT_SECONDS = 10
# Subreddits read per fetch, sampled from the configured list. The
# unauthenticated listing allows roughly ten requests a minute, and sampling
# also varies which communities the DJ draws from between spots.
_MAX_SUBREDDITS_PER_FETCH = 5
# Self-text carried into the blacklist check. The whole body can run to
# thousands of words, and the part that sets a post's subject is at the top.
_SELFTEXT_FILTER_CHARS = 500


class RedditItem:
    """One submission, reduced to the fields that may be spoken."""

    def __init__(self, data: dict):
        self.title = (data.get("title") or "").strip()
        self.source = f"r/{data.get('subreddit') or ''}"
        self.score = int(data.get("score") or 0)
        self.comments = int(data.get("num_comments") or 0)
        self.age_hours = self._age_hours(data.get("created_utc"))
        self.sensitive = bool(data.get("over_18")) or bool(data.get("spoiler"))
        self.restricted = (
            bool(data.get("quarantine"))
            or data.get("subreddit_type", "public") != "public"
        )
        # Structural rather than content: a pinned announcement is not a post
        # people are discussing, and every subreddit has a couple.
        self.announcement = bool(data.get("stickied")) or bool(data.get("pinned"))
        self.filter_text = "\n".join([
            self.title,
            data.get("link_flair_text") or "",
            (data.get("selftext") or "")[:_SELFTEXT_FILTER_CHARS],
            data.get("subreddit") or "",
        ])

    @staticmethod
    def _age_hours(created_utc) -> float:
        """Hours since posting. An unreadable timestamp reads as ancient, so the
        age gate drops the item rather than letting it through unchecked."""
        try:
            created = float(created_utc)
        except (TypeError, ValueError):
            logger.warning(f"Unreadable Reddit timestamp: {created_utc}")
            return float("inf")
        return max(0.0, (time.time() - created) / 3600.0)

    def _age_str(self) -> str:
        if self.age_hours < 2:
            return "in the last hour"
        if self.age_hours < 24:
            return f"{int(self.age_hours)} hours ago"
        return "yesterday"

    def _engagement_str(self) -> str:
        if self.comments < 100:
            return ""
        if self.comments < 500:
            return " (some discussion)"
        return " (a great deal of discussion)"

    def __str__(self):
        return f"{self.title} (posted to {self.source} {self._age_str()}){self._engagement_str()}"


class RedditAPI:

    def __init__(self, subreddits: Optional[List[str]] = None) -> None:
        configured = subreddits if subreddits is not None else config.reddit_subreddits
        self.subreddits = [name.strip().lstrip("/").removeprefix("r/")
                           for name in configured if name and name.strip()]
        self._reddit = None

    def _has_credentials(self) -> bool:
        return bool(config.reddit_client_id) and bool(config.reddit_client_secret)

    def _allowed_subreddits(self) -> List[str]:
        """The configured allowlist, minus blacklisted names, sampled down.

        The allowlist is the source gate for this topic: an open firehose
        cannot be filtered into safety by keyword matching, so there is no
        path here that reads r/all or r/popular.
        """
        allowed = [name for name in self.subreddits if not source_is_blacklisted(name)]
        if not allowed:
            raise SocialSourceUnusable(
                "No usable subreddits are configured" if not self.subreddits
                else "Every configured subreddit is blacklisted"
            )
        if len(allowed) > _MAX_SUBREDDITS_PER_FETCH:
            allowed = random.sample(allowed, _MAX_SUBREDDITS_PER_FETCH)
        return allowed

    def _fetch_via_json(self, name: str, limit: int) -> List[dict]:
        url = f"https://www.reddit.com/r/{name}/top.json"
        try:
            response = requests.get(
                url,
                params={"t": "day", "limit": limit},
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
                timeout=_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise WebConnectionException(f"Failed to reach {url}: {e}")
        if response.status_code in (401, 403, 429):
            raise SocialSourceUnusable(
                f"Reddit refused the unauthenticated listing (HTTP {response.status_code}); "
                f"configure reddit_client_id to use the API"
            )
        if not response.ok:
            raise WebConnectionException(f"{url} returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as e:
            raise WebConnectionException(f"{url} returned unreadable JSON: {e}")
        children = (payload or {}).get("data", {}).get("children")
        if not isinstance(children, list):
            raise WebConnectionException(f"{url} returned no listing")
        return [child.get("data", {}) for child in children if isinstance(child, dict)]

    def _praw_client(self):
        """The read-only client, built once. Each construction would otherwise
        fetch its own access token."""
        if self._reddit is None:
            import praw

            self._reddit = praw.Reddit(
                client_id=config.reddit_client_id,
                client_secret=config.reddit_client_secret,
                user_agent=_USER_AGENT,
            )
        return self._reddit

    def _fetch_via_praw(self, name: str, limit: int) -> List[dict]:
        """Listing dicts in the same shape _fetch_via_json returns.

        The subreddit's own flags are read once per subreddit; reading them off
        each submission would lazy-load the same object once per post.
        """
        subreddit = self._praw_client().subreddit(name)
        sub_flags = {
            "subreddit_type": getattr(subreddit, "subreddit_type", "public"),
            "quarantine": bool(getattr(subreddit, "quarantine", False)),
        }
        items = []
        for submission in subreddit.top(time_filter="day", limit=limit):
            items.append({
                "title": getattr(submission, "title", ""),
                "subreddit": name,
                "score": getattr(submission, "score", 0),
                "num_comments": getattr(submission, "num_comments", 0),
                "created_utc": getattr(submission, "created_utc", None),
                "over_18": getattr(submission, "over_18", False),
                "spoiler": getattr(submission, "spoiler", False),
                "stickied": getattr(submission, "stickied", False),
                "pinned": getattr(submission, "pinned", False),
                "link_flair_text": getattr(submission, "link_flair_text", ""),
                "selftext": getattr(submission, "selftext", ""),
                **sub_flags,
            })
        return items

    def get_items(self, limit_per_sub: int = 25) -> List[RedditItem]:
        use_praw = self._has_credentials()
        items: List[RedditItem] = []
        failures = []
        reasons = []
        for name in self._allowed_subreddits():
            try:
                if use_praw:
                    try:
                        raw = self._fetch_via_praw(name, limit_per_sub)
                    except ImportError:
                        logger.info("praw is not installed; using the public listing")
                        use_praw = False
                    except Exception as e:
                        # Bad credentials or a praw-side error should not lose
                        # the topic while the public listing still answers.
                        logger.warning(f"Reddit API path failed ({e}); using the public listing")
                        use_praw = False
                if not use_praw:
                    raw = self._fetch_via_json(name, limit_per_sub)
            except (WebConnectionException, SocialSourceUnusable) as e:
                # One unreachable or refused subreddit should not lose the rest.
                logger.warning(f"Skipping r/{name}: {e}")
                failures.append(name)
                if str(e) not in reasons:
                    reasons.append(str(e))
                continue
            items.extend(RedditItem(data) for data in raw)
        if not items:
            # Every skip reason is carried out, deduplicated: when the whole
            # fetch failed for one cause, that cause is the only thing worth
            # reading and it is what says how to fix it.
            raise SocialSourceUnusable(
                f"No submissions were returned from {failures}: {'; '.join(reasons)}"
                if failures else "No submissions were returned"
            )
        return items

    @staticmethod
    def _without_announcements(items: List[RedditItem]) -> List[RedditItem]:
        """Drops pinned and stickied posts before the shared filter, so they do
        not spend the attrition budget that content rejections are measured
        against."""
        return [item for item in items if not item.announcement]

    def get_news(self, total: int = 12) -> str:
        """The filtered payload for the prompt.

        Named to match HackerNewsSouper.get_news and NewsAPI.get_news so the
        topic handler dispatches the same way for all of them.
        """
        items = self._without_announcements(self.get_items())
        items = filter_items(
            items,
            min_score=config.reddit_min_score,
            max_age_hours=config.reddit_max_age_hours,
            min_surviving=config.social_min_surviving_items,
            max_rejection_ratio=config.social_max_rejection_ratio,
        )
        items.sort(key=lambda item: item.score, reverse=True)
        sources = sorted({item.source for item in items})
        return assemble_payload(
            f"Posts people are discussing today on {', '.join(sources)}:", items, total=total
        )
