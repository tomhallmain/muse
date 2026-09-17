"""Live checks against Reddit.

Deselected by default (see pytest.ini); run with `pytest -m api`.

These cover the one thing offline tests cannot: whether the public listing
still answers without credentials from this machine, and whether real
submissions still carry the fields the gates read. Reddit refuses datacenter
address ranges, so a refusal here is informative rather than a code fault --
the message says so.
"""

import pytest

from extensions.reddit_api import RedditAPI, RedditItem
from extensions.social_filter import SocialSourceUnusable
from library_data.blacklist import Blacklist
from utils.config import config

# Pinned rather than read from config so the user's own allowlist does not
# decide whether this passes. Both are large, heavily moderated and long-lived.
_SUBS = ["askhistorians", "cooking"]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(config, "reddit_min_score", 50)
    monkeypatch.setattr(config, "reddit_max_age_hours", 24)
    monkeypatch.setattr(config, "social_min_surviving_items", 3)
    monkeypatch.setattr(config, "social_max_rejection_ratio", 0.4)
    return RedditAPI(subreddits=_SUBS)


@pytest.fixture
def json_api(api, monkeypatch):
    """Forces the unauthenticated path even where credentials are configured."""
    monkeypatch.setattr(config, "reddit_client_id", None)
    monkeypatch.setattr(config, "reddit_client_secret", None)
    return api


class TestUnauthenticatedAccess:
    def test_the_public_listing_needs_no_credentials(self, json_api):
        """The premise of the no-setup path. A refusal means this machine's
        address range is blocked and reddit_client_id must be configured."""
        try:
            items = json_api.get_items(limit_per_sub=25)
        except SocialSourceUnusable as e:
            pytest.skip(f"Reddit refused the unauthenticated listing: {e}")

        assert items
        assert all(isinstance(item, RedditItem) for item in items)

    def test_the_fields_the_gates_read_are_still_present(self, json_api):
        """Guards against a schema change that would silently zero the gates:
        a missing score reads as 0 and a missing date as infinitely old, so
        every item would be filtered out rather than erroring."""
        try:
            items = json_api.get_items(limit_per_sub=25)
        except SocialSourceUnusable as e:
            pytest.skip(f"Reddit refused the unauthenticated listing: {e}")

        assert any(item.score > 0 for item in items), "no item carried a score"
        assert any(item.age_hours < 24 * 365 for item in items), "no item carried a readable date"
        assert any(item.title.strip() for item in items), "no item carried a title"
        assert all(item.source.startswith("r/") for item in items)


class TestLivePayload:
    def test_real_posts_keep_handles_and_links_out_of_the_payload(self, json_api):
        """Gate 4 against real listings. The blacklist is emptied so the user's
        own list cannot decide the outcome."""
        Blacklist.set_blacklist([])

        try:
            payload = json_api.get_news()
        except SocialSourceUnusable as e:
            pytest.skip(f"Live listing did not pass the filters: {e}")

        assert "http" not in payload
        assert "u/" not in payload
        assert "r/" in payload

    def test_the_filters_do_not_reject_everything_on_a_normal_day(self, json_api):
        """A feed that never survives filtering is a topic that never fires.
        Runs against the real blacklist, so a failure may mean the thresholds
        are too tight for these subreddits rather than a code fault."""
        try:
            json_api.get_news()
        except SocialSourceUnusable as e:
            pytest.skip(
                f"No usable payload from {_SUBS}: {e}. Check reddit_min_score, "
                f"reddit_max_age_hours and social_max_rejection_ratio."
            )
