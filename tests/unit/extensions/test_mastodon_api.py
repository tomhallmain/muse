"""Unit tests for extensions.mastodon_api. No network: every fetch is a
stubbed requests.get.

The visible_text tests carry most of the weight. It is what keeps handles and
URLs out of the payload, which the DJ's prompt cannot be relied on to do and
which the blacklist does not cover.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from extensions.mastodon_api import MastodonAPI, MastodonItem, visible_text
from extensions.social_filter import SocialSourceUnusable
from extensions.soup_utils import WebConnectionException
from library_data.blacklist import Blacklist, BlacklistItem
from utils.config import config

_INSTANCE = "example.social"

# Mastodon's own markup for a post carrying a hashtag, a mention and a link.
_RICH_CONTENT = (
    '<p>Just restored an old '
    '<a href="https://example.social/tags/typewriter" class="mention hashtag" rel="tag">'
    '#<span>typewriter</span></a> &amp; it types beautifully.<br />'
    'Thanks <span class="h-card"><a href="https://example.social/@someone" '
    'class="u-url mention">@<span>someone</span></a></span> for the tip &mdash; '
    '<a href="https://blog.example.com/post" target="_blank" rel="nofollow noopener">'
    '<span class="invisible">https://</span><span class="ellipsis">blog.example.com/po</span>'
    '<span class="invisible">st</span></a></p>'
)


def _status(content="<p>An ordinary post about bread</p>", reblogs=20, favourites=40,
            sensitive=False, spoiler="", visibility="public", language="en",
            age_hours=1.0, tags=None):
    created = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=age_hours)
    return {
        "content": content,
        "reblogs_count": reblogs,
        "favourites_count": favourites,
        "sensitive": sensitive,
        "spoiler_text": spoiler,
        "visibility": visibility,
        "language": language,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "tags": tags or [],
        # Present in the real payload and deliberately never read:
        "account": {"acct": "someone@example.social", "username": "someone"},
        "url": "https://example.social/@someone/1",
    }


@pytest.fixture(autouse=True)
def _mastodon_config(monkeypatch):
    monkeypatch.setattr(config, "mastodon_instance", _INSTANCE)
    monkeypatch.setattr(config, "mastodon_languages", ["en"])
    monkeypatch.setattr(config, "mastodon_min_score", 5)
    monkeypatch.setattr(config, "mastodon_max_age_hours", 24)
    monkeypatch.setattr(config, "social_min_surviving_items", 3)
    monkeypatch.setattr(config, "social_max_rejection_ratio", 0.4)
    Blacklist.set_blacklist([BlacklistItem("badword")])
    yield
    Blacklist.clear()


def _response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json.return_value = payload
    return response


@pytest.mark.unit
class TestVisibleText:
    def test_a_hashtag_keeps_its_word(self):
        assert "#typewriter" in visible_text(_RICH_CONTENT)

    def test_a_mention_is_removed(self):
        text = visible_text(_RICH_CONTENT)

        assert "someone" not in text
        assert "@" not in text

    def test_a_link_is_removed(self):
        text = visible_text(_RICH_CONTENT)

        assert "blog.example.com" not in text
        assert "http" not in text

    def test_block_boundaries_become_spaces(self):
        """Stripping the tags without this runs the last word of a line into
        the first word of the next."""
        text = visible_text("<p>First line.<br />Second line.</p><p>Third line.</p>")

        assert text == "First line. Second line. Third line."

    def test_entities_are_unescaped(self):
        assert visible_text("<p>bread &amp; butter</p>") == "bread & butter"

    def test_a_percent_sign_survives(self):
        assert visible_text("<p>Storage at 50% &amp; rising</p>") == "Storage at 50% & rising"

    def test_empty_content_is_empty(self):
        assert visible_text("") == ""
        assert visible_text(None) == ""


@pytest.mark.unit
class TestMastodonItem:
    def test_score_is_boosts_plus_favourites(self):
        assert MastodonItem(_status(reblogs=3, favourites=4), _INSTANCE).score == 7

    def test_missing_counts_read_as_zero(self):
        status = _status()
        status["reblogs_count"] = None
        del status["favourites_count"]

        assert MastodonItem(status, _INSTANCE).score == 0

    def test_the_sensitive_flag_is_carried(self):
        assert MastodonItem(_status(sensitive=True), _INSTANCE).sensitive is True

    def test_a_content_warning_counts_as_sensitive(self):
        """A content warning is the author saying the post needs one."""
        assert MastodonItem(_status(spoiler="cw: food"), _INSTANCE).sensitive is True

    def test_non_public_visibility_is_restricted(self):
        assert MastodonItem(_status(visibility="unlisted"), _INSTANCE).restricted is True
        assert MastodonItem(_status(visibility="public"), _INSTANCE).restricted is False

    def test_age_is_read_from_the_timestamp(self):
        item = MastodonItem(_status(age_hours=5.0), _INSTANCE)

        assert 4.9 < item.age_hours < 5.2

    def test_an_unreadable_timestamp_reads_as_ancient(self):
        """Infinite age fails the age gate, so a post whose date cannot be read
        is dropped rather than passed through unchecked."""
        status = _status()
        status["created_at"] = "not a date"

        assert MastodonItem(status, _INSTANCE).age_hours == float("inf")

    def test_a_missing_timestamp_reads_as_ancient(self):
        status = _status()
        del status["created_at"]

        assert MastodonItem(status, _INSTANCE).age_hours == float("inf")

    def test_filter_text_covers_the_warning_and_the_tags(self):
        item = MastodonItem(
            _status(spoiler="cw: badword", tags=[{"name": "baking"}]), _INSTANCE
        )

        assert "badword" in item.filter_text
        assert "baking" in item.filter_text

    def test_the_rendered_item_exposes_no_author_or_url(self):
        rendered = str(MastodonItem(_status(content=_RICH_CONTENT), _INSTANCE))

        assert "someone" not in rendered
        assert "http" not in rendered
        assert "@" not in rendered
        assert _INSTANCE in rendered


@pytest.mark.unit
class TestGetItems:
    def test_statuses_become_items(self):
        with patch("extensions.mastodon_api.requests.get", return_value=_response([_status()] * 3)):
            items = MastodonAPI().get_items()

        assert len(items) == 3
        assert all(isinstance(item, MastodonItem) for item in items)

    def test_an_unconfigured_instance_is_unusable(self, monkeypatch):
        monkeypatch.setattr(config, "mastodon_instance", "")

        with pytest.raises(SocialSourceUnusable):
            MastodonAPI().get_items()

    def test_a_blacklisted_instance_is_never_fetched(self):
        Blacklist.set_blacklist([BlacklistItem("badword")])

        with patch("extensions.mastodon_api.requests.get") as get:
            with pytest.raises(SocialSourceUnusable):
                MastodonAPI(instance="badword.social").get_items()

        get.assert_not_called()

    def test_a_scheme_in_the_configured_instance_is_tolerated(self):
        assert MastodonAPI(instance="https://example.social/").instance == _INSTANCE

    def test_an_instance_requiring_auth_is_unusable_not_a_connection_error(self):
        """Public read being closed is a configuration problem, not a network
        fault, so the DJ should not apologize for connectivity."""
        with patch("extensions.mastodon_api.requests.get", return_value=_response([], 401)):
            with pytest.raises(SocialSourceUnusable):
                MastodonAPI().get_items()

    def test_a_server_error_is_a_connection_error(self):
        with patch("extensions.mastodon_api.requests.get", return_value=_response([], 503)):
            with pytest.raises(WebConnectionException):
                MastodonAPI().get_items()

    def test_an_unreachable_host_is_a_connection_error(self):
        import requests as requests_mod

        with patch("extensions.mastodon_api.requests.get",
                   side_effect=requests_mod.ConnectionError("no route")):
            with pytest.raises(WebConnectionException):
                MastodonAPI().get_items()

    def test_a_non_list_payload_is_a_connection_error(self):
        with patch("extensions.mastodon_api.requests.get",
                   return_value=_response({"error": "nope"})):
            with pytest.raises(WebConnectionException):
                MastodonAPI().get_items()


@pytest.mark.unit
class TestGetNews:
    def test_the_payload_holds_the_surviving_posts(self):
        statuses = [_status(content=f"<p>Ordinary post {i}</p>") for i in range(5)]

        with patch("extensions.mastodon_api.requests.get", return_value=_response(statuses)):
            payload = MastodonAPI().get_news()

        assert _INSTANCE in payload
        for i in range(5):
            assert f"Ordinary post {i}" in payload

    def test_a_blacklisted_post_does_not_reach_the_payload(self):
        statuses = [_status(content=f"<p>Ordinary post {i}</p>") for i in range(8)]
        statuses.append(_status(content="<p>This one says badword aloud</p>"))

        with patch("extensions.mastodon_api.requests.get", return_value=_response(statuses)):
            payload = MastodonAPI().get_news()

        assert "badword" not in payload

    def test_another_language_is_dropped(self):
        statuses = [_status(content=f"<p>Ordinary post {i}</p>") for i in range(4)]
        statuses.append(_status(content="<p>Ein gewoehnlicher Beitrag</p>", language="de"))

        with patch("extensions.mastodon_api.requests.get", return_value=_response(statuses)):
            payload = MastodonAPI().get_news()

        assert "gewoehnlicher" not in payload

    def test_a_regional_language_code_still_matches(self):
        statuses = [_status(content=f"<p>Ordinary post {i}</p>", language="en-GB") for i in range(4)]

        with patch("extensions.mastodon_api.requests.get", return_value=_response(statuses)):
            payload = MastodonAPI().get_news()

        assert "Ordinary post 0" in payload

    def test_an_unset_language_is_kept(self):
        statuses = [_status(content=f"<p>Ordinary post {i}</p>", language=None) for i in range(4)]

        with patch("extensions.mastodon_api.requests.get", return_value=_response(statuses)):
            payload = MastodonAPI().get_news()

        assert "Ordinary post 0" in payload

    def test_too_few_survivors_aborts_the_topic(self):
        with patch("extensions.mastodon_api.requests.get", return_value=_response([_status()])):
            with pytest.raises(SocialSourceUnusable):
                MastodonAPI().get_news()

    def test_the_payload_is_ordered_by_engagement(self):
        statuses = [
            _status(content="<p>Quiet post</p>", reblogs=1, favourites=5),
            _status(content="<p>Loud post</p>", reblogs=500, favourites=500),
            _status(content="<p>Middling post</p>", reblogs=20, favourites=20),
        ]

        with patch("extensions.mastodon_api.requests.get", return_value=_response(statuses)):
            payload = MastodonAPI().get_news()

        assert payload.index("Loud post") < payload.index("Middling post") < payload.index("Quiet post")

    def test_the_total_caps_the_payload(self):
        statuses = [_status(content=f"<p>Ordinary post {i}</p>") for i in range(20)]

        with patch("extensions.mastodon_api.requests.get", return_value=_response(statuses)):
            payload = MastodonAPI().get_news(total=4)

        assert payload.count("Ordinary post") == 4
