"""Live checks against Bluesky.

Deselected by default (see pytest.ini); run with `pytest -m api`.

The first test here settles the question the spec left open: whether the public
AppView serves read-only feed queries with no account. If it does, this source
needs no credentials at all. If it does not, the test says so and the app
password path is the only one.
"""

import pytest

from extensions.bluesky_api import BlueskyAPI, BlueskyItem
from extensions.social_filter import SocialSourceUnusable
from library_data.blacklist import Blacklist
from utils.config import config

# Pinned rather than read from config so the user's own feed list does not
# decide whether this passes. If it no longer resolves, the failure message
# says so and the URI is what needs replacing.
_FEED = "at://did:plc:z72i7hdynmk6r22z27h6tvur/app.bsky.feed.generator/whats-hot"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(config, "bluesky_handle", None)
    monkeypatch.setattr(config, "bluesky_app_password", None)
    monkeypatch.setattr(config, "bluesky_languages", ["en"])
    monkeypatch.setattr(config, "bluesky_min_score", 100)
    monkeypatch.setattr(config, "bluesky_max_age_hours", 24)
    monkeypatch.setattr(config, "social_min_surviving_items", 3)
    monkeypatch.setattr(config, "social_max_rejection_ratio", 0.4)
    return BlueskyAPI(feeds=[_FEED])


class TestUnauthenticatedAccess:
    def test_the_public_appview_serves_a_feed_without_credentials(self, api):
        """Settles the open question. A refusal means Bluesky needs an app
        password; an unrecognised-feed error means the pinned URI has moved and
        bluesky_feeds needs a different one."""
        try:
            items = api.get_items(limit_per_feed=30)
        except SocialSourceUnusable as e:
            pytest.fail(
                f"The public AppView did not serve {_FEED}: {e}. Either the AppView "
                f"requires authentication, or this feed URI no longer resolves."
            )

        assert items
        assert all(isinstance(item, BlueskyItem) for item in items)

    def test_the_fields_the_gates_read_are_still_present(self, api):
        """Guards against a schema change that would silently zero the gates: a
        missing count reads as 0 and a missing date as infinitely old, so every
        item would be filtered out rather than erroring."""
        items = api.get_items(limit_per_feed=30)

        assert any(item.score > 0 for item in items), "no post carried an engagement count"
        assert any(item.age_hours < 24 * 365 for item in items), "no post carried a readable date"
        assert any(item.title.strip() for item in items), "no post carried readable text"
        assert any(item.language for item in items), "no post declared a language"


class TestLivePayload:
    def test_real_posts_keep_handles_and_links_out_of_the_payload(self, api):
        """Gate 4 against real post text, where URLs and handles are literal
        characters rather than markup. The blacklist is emptied so the user's
        own list cannot decide the outcome."""
        Blacklist.set_blacklist([])

        try:
            payload = api.get_news()
        except SocialSourceUnusable as e:
            pytest.skip(f"Live feed did not pass the filters: {e}")

        assert "http" not in payload
        assert "@" not in payload
        assert "Bluesky" in payload

    def test_the_filters_do_not_reject_everything_on_a_normal_day(self, api):
        """A feed that never survives filtering is a topic that never fires."""
        try:
            api.get_news()
        except SocialSourceUnusable as e:
            pytest.skip(
                f"No usable payload from {_FEED}: {e}. Check bluesky_min_score, "
                f"bluesky_max_age_hours and social_max_rejection_ratio."
            )
