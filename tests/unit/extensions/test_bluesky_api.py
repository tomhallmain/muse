"""Unit tests for extensions.bluesky_api. No network: every call is a stubbed
requests.get or requests.post.

The gates themselves are covered in test_social_filter.py. What is tested here
is the post parsing, the two access paths, and visible_text -- which on Bluesky
is load-bearing in a way it is not elsewhere, because post text carries URLs
and handles as literal characters rather than as markup.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from extensions.bluesky_api import BlueskyAPI, BlueskyItem, feed_name, visible_text
from extensions.social_filter import SocialSourceUnusable
from extensions.soup_utils import WebConnectionException
from library_data.blacklist import Blacklist, BlacklistItem
from utils.config import config

_FEED = "at://did:plc:example/app.bsky.feed.generator/whats-hot"
_OTHER_FEED = "at://did:plc:example/app.bsky.feed.generator/science"


def _post(text="A perfectly ordinary post about bread", likes=200, reposts=100,
          replies=5, age_hours=1.0, langs=("en",), labels=(), author_labels=()):
    indexed = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=age_hours)
    return {
        "record": {
            "text": text,
            "createdAt": indexed.isoformat().replace("+00:00", "Z"),
            "langs": list(langs),
        },
        "likeCount": likes,
        "repostCount": reposts,
        "replyCount": replies,
        "indexedAt": indexed.isoformat().replace("+00:00", "Z"),
        "labels": [{"val": v} for v in labels],
        # Present in the real view and deliberately never rendered:
        "author": {
            "did": "did:plc:someone",
            "handle": "someone.bsky.social",
            "displayName": "Someone",
            "labels": [{"val": v} for v in author_labels],
        },
        "uri": "at://did:plc:someone/app.bsky.feed.post/abc123",
        "cid": "bafyabc123",
    }


def _feed_response(posts, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json.return_value = {"feed": [{"post": p} for p in posts]}
    return response


def _error_response(status_code):
    response = MagicMock()
    response.status_code = status_code
    response.ok = False
    response.json.return_value = {"error": "nope"}
    return response


@pytest.fixture(autouse=True)
def _bluesky_config(monkeypatch):
    monkeypatch.setattr(config, "bluesky_feeds", [_FEED])
    monkeypatch.setattr(config, "bluesky_handle", None)
    monkeypatch.setattr(config, "bluesky_app_password", None)
    monkeypatch.setattr(config, "bluesky_languages", ["en"])
    monkeypatch.setattr(config, "bluesky_min_score", 100)
    monkeypatch.setattr(config, "bluesky_max_age_hours", 24)
    monkeypatch.setattr(config, "social_min_surviving_items", 3)
    monkeypatch.setattr(config, "social_max_rejection_ratio", 0.4)
    Blacklist.set_blacklist([BlacklistItem("badword")])
    yield
    Blacklist.clear()


@pytest.mark.unit
class TestVisibleText:
    def test_a_link_is_removed(self):
        text = visible_text("Look at this https://example.com/some/path it is good")

        assert "http" not in text
        assert "example.com" not in text
        assert "Look at this" in text and "it is good" in text

    def test_a_bare_domain_is_removed(self):
        assert "example.com" not in visible_text("see www.example.com/page for more")

    def test_a_handle_is_removed(self):
        text = visible_text("thanks @someone.bsky.social for the tip")

        assert "someone" not in text
        assert "@" not in text
        assert "thanks" in text and "for the tip" in text

    def test_a_hashtag_is_kept(self):
        assert "#baking" in visible_text("a loaf today #baking")

    def test_whitespace_is_collapsed(self):
        assert visible_text("one\n\ntwo   three") == "one two three"

    def test_empty_text_is_empty(self):
        assert visible_text("") == ""
        assert visible_text(None) == ""


@pytest.mark.unit
class TestFeedName:
    def test_the_record_key_is_the_readable_part(self):
        assert feed_name(_FEED) == "whats-hot"

    def test_a_trailing_slash_is_tolerated(self):
        assert feed_name(_FEED + "/") == "whats-hot"

    def test_no_uri_is_no_name(self):
        assert feed_name("") == ""
        assert feed_name(None) == ""


@pytest.mark.unit
class TestBlueskyItem:
    def test_score_is_likes_plus_reposts(self):
        assert BlueskyItem(_post(likes=3, reposts=4), "whats-hot").score == 7

    def test_missing_counts_read_as_zero(self):
        post = _post()
        post["likeCount"] = None
        del post["repostCount"]

        assert BlueskyItem(post, "whats-hot").score == 0

    def test_any_label_counts_as_sensitive(self):
        """The label set grows, so the presence of a label is the signal rather
        than its particular value."""
        assert BlueskyItem(_post(labels=("porn",)), "whats-hot").sensitive is True
        assert BlueskyItem(_post(labels=("some-future-label",)), "whats-hot").sensitive is True
        assert BlueskyItem(_post(), "whats-hot").sensitive is False

    def test_an_author_label_also_counts(self):
        assert BlueskyItem(_post(author_labels=("spam",)), "whats-hot").sensitive is True

    def test_a_hide_label_is_restricted(self):
        assert BlueskyItem(_post(labels=("!hide",)), "whats-hot").restricted is True
        assert BlueskyItem(_post(labels=("porn",)), "whats-hot").restricted is False

    def test_age_is_read_from_the_index_time(self):
        assert 4.9 < BlueskyItem(_post(age_hours=5.0), "whats-hot").age_hours < 5.2

    def test_an_unreadable_timestamp_reads_as_ancient(self):
        post = _post()
        post["indexedAt"] = "not a date"
        post["record"]["createdAt"] = "not a date"

        assert BlueskyItem(post, "whats-hot").age_hours == float("inf")

    def test_the_language_is_the_first_declared_one(self):
        assert BlueskyItem(_post(langs=("en", "de")), "whats-hot").language == "en"
        assert BlueskyItem(_post(langs=()), "whats-hot").language == ""

    def test_filter_text_covers_the_labels_and_the_feed(self):
        item = BlueskyItem(_post(labels=("badword",)), "whats-hot")

        assert "badword" in item.filter_text
        assert "whats-hot" in item.filter_text

    def test_the_rendered_item_exposes_no_author_or_url(self):
        rendered = str(BlueskyItem(
            _post(text="thanks @someone.bsky.social see https://example.com/x"), "whats-hot"))

        assert "someone" not in rendered
        assert "http" not in rendered
        assert "@" not in rendered
        assert "Bluesky" in rendered


@pytest.mark.unit
class TestSourceAllowlist:
    def test_a_blacklisted_feed_is_never_fetched(self, monkeypatch):
        bad = "at://did:plc:example/app.bsky.feed.generator/badword"
        monkeypatch.setattr(config, "bluesky_feeds", [bad, _FEED])

        with patch("extensions.bluesky_api.requests.get",
                   return_value=_feed_response([_post()] * 5)) as get:
            BlueskyAPI().get_items()

        requested = [call.kwargs["params"]["feed"] for call in get.call_args_list]
        assert bad not in requested
        assert _FEED in requested

    def test_no_configured_feeds_names_the_setting(self):
        with pytest.raises(SocialSourceUnusable) as excinfo:
            BlueskyAPI(feeds=[]).get_items()

        assert "bluesky_feeds" in str(excinfo.value)

    def test_every_feed_blacklisted_is_unusable(self, monkeypatch):
        monkeypatch.setattr(config, "bluesky_feeds",
                            ["at://did:plc:example/app.bsky.feed.generator/badword"])

        with pytest.raises(SocialSourceUnusable):
            BlueskyAPI().get_items()

    def test_the_fetch_is_capped_regardless_of_how_many_are_configured(self, monkeypatch):
        monkeypatch.setattr(config, "bluesky_feeds", [
            f"at://did:plc:example/app.bsky.feed.generator/feed{i}" for i in range(12)])

        with patch("extensions.bluesky_api.requests.get",
                   return_value=_feed_response([_post()] * 5)) as get:
            BlueskyAPI().get_items()

        assert get.call_count <= 3


@pytest.mark.unit
class TestAnonymousPath:
    def test_the_appview_is_read_without_credentials(self):
        with patch("extensions.bluesky_api.requests.get",
                   return_value=_feed_response([_post()] * 3)) as get:
            items = BlueskyAPI().get_items()

        assert len(items) == 3
        url = get.call_args.args[0]
        assert "public.api.bsky.app" in url
        assert "Authorization" not in get.call_args.kwargs["headers"]

    def test_a_refusal_names_the_credential_settings(self):
        with patch("extensions.bluesky_api.requests.get", return_value=_error_response(403)):
            with pytest.raises(SocialSourceUnusable) as excinfo:
                BlueskyAPI().get_items()

        assert "bluesky_handle" in str(excinfo.value)

    def test_an_unknown_feed_names_the_feed_setting(self):
        with patch("extensions.bluesky_api.requests.get", return_value=_error_response(400)):
            with pytest.raises(SocialSourceUnusable) as excinfo:
                BlueskyAPI().get_items()

        assert "bluesky_feeds" in str(excinfo.value)

    def test_one_failing_feed_does_not_lose_the_others(self, monkeypatch):
        monkeypatch.setattr(config, "bluesky_feeds", [_FEED, _OTHER_FEED])

        with patch("extensions.bluesky_api.requests.get",
                   side_effect=[_error_response(503), _feed_response([_post()] * 4)]):
            assert len(BlueskyAPI().get_items()) == 4

    def test_a_server_error_on_every_feed_is_unusable(self):
        with patch("extensions.bluesky_api.requests.get", return_value=_error_response(503)):
            with pytest.raises(SocialSourceUnusable):
                BlueskyAPI().get_items()

    def test_a_payload_with_no_feed_is_skipped(self):
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {"cursor": "x"}

        with patch("extensions.bluesky_api.requests.get", return_value=response):
            with pytest.raises(SocialSourceUnusable):
                BlueskyAPI().get_items()


@pytest.mark.unit
class TestAppPasswordPath:
    @pytest.fixture
    def credentialed(self, monkeypatch):
        monkeypatch.setattr(config, "bluesky_handle", "dj.bsky.social")
        monkeypatch.setattr(config, "bluesky_app_password", "abcd-efgh-ijkl-mnop")
        session = MagicMock()
        session.status_code = 200
        session.ok = True
        session.json.return_value = {"accessJwt": "a-token"}
        return session

    def test_the_token_is_sent_as_a_bearer_header(self, credentialed):
        with patch("extensions.bluesky_api.requests.post", return_value=credentialed):
            with patch("extensions.bluesky_api.requests.get",
                       return_value=_feed_response([_post()] * 3)) as get:
                BlueskyAPI().get_items()

        headers = get.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer a-token"
        assert "bsky.social" in get.call_args.args[0]

    def test_the_session_is_created_once_for_the_whole_fetch(self, credentialed, monkeypatch):
        monkeypatch.setattr(config, "bluesky_feeds", [_FEED, _OTHER_FEED])

        with patch("extensions.bluesky_api.requests.post", return_value=credentialed) as post:
            with patch("extensions.bluesky_api.requests.get",
                       return_value=_feed_response([_post()] * 3)):
                BlueskyAPI().get_items()

        assert post.call_count == 1

    def test_a_rejected_app_password_names_the_setting(self, credentialed):
        with patch("extensions.bluesky_api.requests.post", return_value=_error_response(401)):
            with patch("extensions.bluesky_api.requests.get"):
                with pytest.raises(SocialSourceUnusable) as excinfo:
                    BlueskyAPI().get_items()

        assert "bluesky_app_password" in str(excinfo.value)

    def test_a_rejected_login_is_not_retried_per_feed(self, credentialed, monkeypatch):
        """Authentication happens before the feed loop: no feed will answer
        without it, and repeating a rejected login invites a lockout."""
        monkeypatch.setattr(config, "bluesky_feeds", [_FEED, _OTHER_FEED])

        with patch("extensions.bluesky_api.requests.post",
                   return_value=_error_response(401)) as post:
            with patch("extensions.bluesky_api.requests.get") as get:
                with pytest.raises(SocialSourceUnusable):
                    BlueskyAPI().get_items()

        assert post.call_count == 1
        get.assert_not_called()

    def test_a_credential_failure_is_not_reported_as_an_empty_feed(self, credentialed):
        """Raised as itself rather than swallowed by the per-feed skip, so the
        cause names the setting to fix instead of reading as no posts found."""
        session = MagicMock()
        session.status_code = 200
        session.ok = True
        session.json.return_value = {}

        with patch("extensions.bluesky_api.requests.post", return_value=session):
            with patch("extensions.bluesky_api.requests.get"):
                with pytest.raises(WebConnectionException):
                    BlueskyAPI().get_items()

    def test_a_session_without_a_token_is_a_connection_error(self, monkeypatch):
        monkeypatch.setattr(config, "bluesky_handle", "dj.bsky.social")
        monkeypatch.setattr(config, "bluesky_app_password", "pw")
        session = MagicMock()
        session.status_code = 200
        session.ok = True
        session.json.return_value = {}

        with patch("extensions.bluesky_api.requests.post", return_value=session):
            with patch("extensions.bluesky_api.requests.get"):
                with pytest.raises(WebConnectionException):
                    BlueskyAPI().get_items()


@pytest.mark.unit
class TestGetNews:
    def test_the_payload_holds_the_surviving_posts(self):
        posts = [_post(text=f"Ordinary post {i}") for i in range(5)]

        with patch("extensions.bluesky_api.requests.get", return_value=_feed_response(posts)):
            payload = BlueskyAPI().get_news()

        assert "Bluesky" in payload
        assert "whats-hot" in payload
        assert "Ordinary post 0" in payload

    def test_a_blacklisted_post_does_not_reach_the_payload(self):
        posts = [_post(text=f"Ordinary post {i}") for i in range(8)]
        posts.append(_post(text="This one says badword aloud"))

        with patch("extensions.bluesky_api.requests.get", return_value=_feed_response(posts)):
            payload = BlueskyAPI().get_news()

        assert "badword" not in payload

    def test_a_labelled_post_does_not_reach_the_payload(self):
        posts = [_post(text=f"Ordinary post {i}") for i in range(8)]
        posts.append(_post(text="A labelled post", labels=("graphic-media",)))

        with patch("extensions.bluesky_api.requests.get", return_value=_feed_response(posts)):
            payload = BlueskyAPI().get_news()

        assert "A labelled post" not in payload

    def test_another_language_is_dropped(self):
        posts = [_post(text=f"Ordinary post {i}") for i in range(4)]
        posts.append(_post(text="Ein gewoehnlicher Beitrag", langs=("de",)))

        with patch("extensions.bluesky_api.requests.get", return_value=_feed_response(posts)):
            payload = BlueskyAPI().get_news()

        assert "gewoehnlicher" not in payload

    def test_the_same_post_in_two_feeds_appears_once(self, monkeypatch):
        """Deduplicated before the shared filter, so a repeat does not spend
        the attrition budget."""
        monkeypatch.setattr(config, "bluesky_feeds", [_FEED, _OTHER_FEED])
        posts = [_post(text=f"Ordinary post {i}") for i in range(4)]

        with patch("extensions.bluesky_api.requests.get", return_value=_feed_response(posts)):
            payload = BlueskyAPI().get_news()

        assert payload.count("Ordinary post 0") == 1

    def test_too_few_survivors_aborts_the_topic(self):
        with patch("extensions.bluesky_api.requests.get",
                   return_value=_feed_response([_post()])):
            with pytest.raises(SocialSourceUnusable):
                BlueskyAPI().get_news()

    def test_the_payload_is_ordered_by_engagement(self):
        posts = [
            _post(text="Quiet post", likes=100, reposts=5),
            _post(text="Loud post", likes=9000, reposts=4000),
            _post(text="Middling post", likes=500, reposts=100),
        ]

        with patch("extensions.bluesky_api.requests.get", return_value=_feed_response(posts)):
            payload = BlueskyAPI().get_news()

        assert payload.index("Loud post") < payload.index("Middling post") < payload.index("Quiet post")

    def test_the_total_caps_the_payload(self):
        posts = [_post(text=f"Ordinary post {i}") for i in range(20)]

        with patch("extensions.bluesky_api.requests.get", return_value=_feed_response(posts)):
            payload = BlueskyAPI().get_news(total=4)

        assert payload.count("Ordinary post") == 4
