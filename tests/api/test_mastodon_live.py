"""Live checks against a real Mastodon instance.

Deselected by default (see pytest.ini); run with `pytest -m api`. These reach a
third-party server over the network, so they are slow, they can fail for
reasons that have nothing to do with this code, and they must never run in a
normal suite.

What they are for is the one thing offline tests cannot cover: whether the
assumption the whole source rests on -- that the trending endpoint serves
public reads with no account, no app registration and no token -- is still
true, and whether real post content still gets through the gates intact.
"""

import pytest

from extensions.mastodon_api import MastodonAPI, MastodonItem
from extensions.social_filter import SocialSourceUnusable
from library_data.blacklist import Blacklist
from utils.config import config

# Pinned rather than read from config so a user's own instance choice does not
# decide whether this passes.
_INSTANCE = "mastodon.social"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(config, "mastodon_languages", ["en"])
    monkeypatch.setattr(config, "mastodon_min_score", 5)
    monkeypatch.setattr(config, "mastodon_max_age_hours", 24)
    monkeypatch.setattr(config, "social_min_surviving_items", 3)
    monkeypatch.setattr(config, "social_max_rejection_ratio", 0.4)
    return MastodonAPI(instance=_INSTANCE)


class TestUnauthenticatedAccess:
    def test_trending_statuses_need_no_credentials(self, api):
        """The premise of this source. A 401 or 403 here means the instance has
        closed public read and the source needs a different instance or a token."""
        items = api.get_items(limit=20)

        assert items, f"{_INSTANCE} returned no trending statuses"
        assert all(isinstance(item, MastodonItem) for item in items)

    def test_the_fields_the_item_reads_are_still_present(self, api):
        """Guards against a schema change that would silently zero the gates --
        a missing count reads as 0 and a missing timestamp as infinitely old,
        so every item would be filtered out rather than erroring."""
        items = api.get_items(limit=20)

        assert any(item.score > 0 for item in items), "no item carried an engagement count"
        assert any(item.age_hours < 24 * 365 for item in items), "no item carried a readable date"
        assert any(item.title.strip() for item in items), "no item carried readable text"


class TestLivePayload:
    def test_real_posts_keep_handles_and_links_out_of_the_payload(self, api, monkeypatch):
        """Gate 4 against real markup. The blacklist is emptied so the user's
        own list cannot decide the outcome."""
        Blacklist.set_blacklist([])

        try:
            payload = api.get_news()
        except SocialSourceUnusable as e:
            pytest.skip(f"Live feed did not pass the filters: {e}")

        assert "http" not in payload
        assert "@" not in payload
        assert _INSTANCE in payload

    def test_the_filters_do_not_reject_everything_on_a_normal_day(self, api):
        """A feed that never survives filtering is a topic that never fires.
        Runs against the real blacklist, so a failure here may mean the
        thresholds are too tight for this instance rather than a code fault."""
        try:
            api.get_news()
        except SocialSourceUnusable as e:
            pytest.fail(
                f"No usable payload from {_INSTANCE}: {e}. Check mastodon_min_score, "
                f"mastodon_max_age_hours and social_max_rejection_ratio against this instance."
            )
