"""Unit tests for extensions.reddit_api. No network: every fetch is a stubbed
requests.get or a stubbed praw module.

The gates themselves are covered in test_social_filter.py; what is tested here
is the listing parsing, the two fetch paths, and the source allowlist -- which
is the only thing standing between the DJ and an unfiltered firehose.
"""

import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest

from extensions.reddit_api import RedditAPI, RedditItem
from extensions.social_filter import SocialSourceUnusable
from extensions.soup_utils import WebConnectionException
from library_data.blacklist import Blacklist, BlacklistItem
from utils.config import config

_SUBS = ["cooking", "woodworking"]


def _submission(title="A perfectly ordinary post about bread", subreddit="cooking",
                score=200, num_comments=30, age_hours=1.0, over_18=False, spoiler=False,
                stickied=False, pinned=False, flair="", selftext="",
                subreddit_type="public", quarantine=False):
    return {
        "title": title,
        "subreddit": subreddit,
        "score": score,
        "num_comments": num_comments,
        "created_utc": time.time() - age_hours * 3600.0,
        "over_18": over_18,
        "spoiler": spoiler,
        "stickied": stickied,
        "pinned": pinned,
        "link_flair_text": flair,
        "selftext": selftext,
        "subreddit_type": subreddit_type,
        "quarantine": quarantine,
        # Present in the real listing and deliberately never read:
        "author": "some_user",
        "url": "https://reddit.com/r/cooking/comments/abc123/",
        "permalink": "/r/cooking/comments/abc123/",
    }


def _listing(submissions):
    return {"data": {"children": [{"data": s} for s in submissions]}}


@pytest.fixture(autouse=True)
def _reddit_config(monkeypatch):
    monkeypatch.setattr(config, "reddit_client_id", None)
    monkeypatch.setattr(config, "reddit_client_secret", None)
    monkeypatch.setattr(config, "reddit_subreddits", list(_SUBS))
    monkeypatch.setattr(config, "reddit_min_score", 50)
    monkeypatch.setattr(config, "reddit_max_age_hours", 24)
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
class TestRedditItem:
    def test_the_source_is_the_subreddit(self):
        assert RedditItem(_submission(subreddit="woodworking")).source == "r/woodworking"

    def test_missing_counts_read_as_zero(self):
        data = _submission()
        data["score"] = None
        del data["num_comments"]

        item = RedditItem(data)

        assert item.score == 0
        assert item.comments == 0

    def test_nsfw_is_sensitive(self):
        assert RedditItem(_submission(over_18=True)).sensitive is True

    def test_a_spoiler_is_sensitive(self):
        assert RedditItem(_submission(spoiler=True)).sensitive is True

    def test_a_quarantined_subreddit_is_restricted(self):
        assert RedditItem(_submission(quarantine=True)).restricted is True

    def test_a_non_public_subreddit_is_restricted(self):
        assert RedditItem(_submission(subreddit_type="private")).restricted is True
        assert RedditItem(_submission(subreddit_type="public")).restricted is False

    def test_a_pinned_post_is_an_announcement_not_a_rejection(self):
        """Every subreddit carries a couple of these, so they are dropped
        before the shared filter rather than spending its attrition budget."""
        assert RedditItem(_submission(stickied=True)).announcement is True
        assert RedditItem(_submission(pinned=True)).announcement is True
        assert RedditItem(_submission()).announcement is False
        assert RedditItem(_submission(stickied=True)).sensitive is False

    def test_age_is_read_from_the_timestamp(self):
        assert 4.9 < RedditItem(_submission(age_hours=5.0)).age_hours < 5.2

    def test_an_unreadable_timestamp_reads_as_ancient(self):
        data = _submission()
        data["created_utc"] = "not a date"

        assert RedditItem(data).age_hours == float("inf")

    def test_filter_text_covers_the_flair_body_and_subreddit(self):
        item = RedditItem(_submission(flair="badword", selftext="a long body"))

        assert "badword" in item.filter_text
        assert "a long body" in item.filter_text
        assert "cooking" in item.filter_text

    def test_only_the_head_of_a_long_body_is_filtered(self):
        """The whole body can run to thousands of words; the part that sets the
        subject is at the top."""
        item = RedditItem(_submission(selftext="x" * 600 + " badword"))

        assert "badword" not in item.filter_text

    def test_the_rendered_item_exposes_no_author_or_url(self):
        rendered = str(RedditItem(_submission()))

        assert "some_user" not in rendered
        assert "http" not in rendered
        assert "permalink" not in rendered
        assert "r/cooking" in rendered


@pytest.mark.unit
class TestSourceAllowlist:
    def test_a_blacklisted_subreddit_is_never_fetched(self, monkeypatch):
        monkeypatch.setattr(config, "reddit_subreddits", ["badword", "cooking"])

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing([_submission()] * 5))) as get:
            RedditAPI().get_items()

        fetched = [call.args[0] for call in get.call_args_list]
        assert not any("badword" in url for url in fetched)
        assert any("cooking" in url for url in fetched)

    def test_every_subreddit_blacklisted_is_unusable(self, monkeypatch):
        monkeypatch.setattr(config, "reddit_subreddits", ["badword"])

        with pytest.raises(SocialSourceUnusable):
            RedditAPI().get_items()

    def test_no_configured_subreddits_is_unusable(self, monkeypatch):
        monkeypatch.setattr(config, "reddit_subreddits", [])

        with pytest.raises(SocialSourceUnusable):
            RedditAPI().get_items()

    def test_a_prefixed_or_padded_name_is_normalised(self):
        assert RedditAPI(subreddits=[" r/Cooking ", "/woodworking"]).subreddits == [
            "Cooking", "woodworking"
        ]

    def test_the_fetch_is_capped_regardless_of_how_many_are_configured(self, monkeypatch):
        """The unauthenticated listing allows roughly ten requests a minute."""
        monkeypatch.setattr(config, "reddit_subreddits", [f"sub{i}" for i in range(20)])

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing([_submission()] * 5))) as get:
            RedditAPI().get_items()

        assert get.call_count <= 5


@pytest.mark.unit
class TestJsonFetch:
    def test_submissions_become_items(self):
        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing([_submission()] * 3))):
            items = RedditAPI().get_items()

        # Two configured subreddits, three submissions each.
        assert len(items) == 6
        assert all(isinstance(item, RedditItem) for item in items)

    def test_a_refusal_names_the_credential_setting(self):
        with patch("extensions.reddit_api.requests.get", return_value=_response({}, 429)):
            with pytest.raises(SocialSourceUnusable) as excinfo:
                RedditAPI().get_items()

        assert "reddit_client_id" in str(excinfo.value)

    def test_one_failing_subreddit_does_not_lose_the_others(self):
        good = _response(_listing([_submission()] * 4))

        with patch("extensions.reddit_api.requests.get",
                   side_effect=[_response({}, 503), good]):
            items = RedditAPI().get_items()

        assert len(items) == 4

    def test_every_subreddit_failing_is_unusable(self):
        with patch("extensions.reddit_api.requests.get", return_value=_response({}, 503)):
            with pytest.raises(SocialSourceUnusable):
                RedditAPI().get_items()

    def test_an_unreachable_host_is_survivable(self):
        import requests as requests_mod

        good = _response(_listing([_submission()] * 4))
        with patch("extensions.reddit_api.requests.get",
                   side_effect=[requests_mod.ConnectionError("no route"), good]):
            assert len(RedditAPI().get_items()) == 4

    def test_a_payload_with_no_listing_is_skipped(self):
        with patch("extensions.reddit_api.requests.get",
                   return_value=_response({"error": "nope"})):
            with pytest.raises(SocialSourceUnusable):
                RedditAPI().get_items()


@pytest.mark.unit
class TestPrawFetch:
    @pytest.fixture
    def fake_praw(self, monkeypatch):
        """A praw stand-in whose submissions carry the same fields the real
        library exposes."""
        submissions = [types.SimpleNamespace(
            title=f"Ordinary post number {i}", score=200, num_comments=30,
            created_utc=time.time() - 3600, over_18=False, spoiler=False,
            stickied=False, pinned=False, link_flair_text="", selftext="",
        ) for i in range(4)]
        subreddit = MagicMock()
        subreddit.subreddit_type = "public"
        subreddit.quarantine = False
        subreddit.top.return_value = submissions
        reddit = MagicMock()
        reddit.subreddit.return_value = subreddit
        module = types.ModuleType("praw")
        module.Reddit = MagicMock(return_value=reddit)
        monkeypatch.setitem(sys.modules, "praw", module)
        monkeypatch.setattr(config, "reddit_client_id", "id")
        monkeypatch.setattr(config, "reddit_client_secret", "secret")
        return module

    def test_credentials_select_the_api_path(self, fake_praw):
        with patch("extensions.reddit_api.requests.get") as get:
            items = RedditAPI().get_items()

        get.assert_not_called()
        assert len(items) == 8
        assert items[0].source == "r/cooking"

    def test_only_the_app_credentials_are_passed(self, fake_praw):
        """The app-only grant carries no user scopes, so no account password
        should ever be handed to praw."""
        with patch("extensions.reddit_api.requests.get") as get:
            RedditAPI().get_items()

        get.assert_not_called()
        kwargs = fake_praw.Reddit.call_args.kwargs
        assert set(kwargs) == {"client_id", "client_secret", "user_agent"}

    def test_the_client_is_built_once_for_the_whole_fetch(self, fake_praw):
        """Each construction would fetch its own access token."""
        with patch("extensions.reddit_api.requests.get"):
            RedditAPI().get_items()

        assert fake_praw.Reddit.call_count == 1

    def test_the_subreddit_flags_are_read_once_per_subreddit(self, fake_praw):
        """Reading them off each submission would lazy-load the same object
        once per post."""
        with patch("extensions.reddit_api.requests.get"):
            RedditAPI().get_items()

        reddit = fake_praw.Reddit.return_value
        assert reddit.subreddit.call_count == len(_SUBS)

    def test_a_praw_side_failure_falls_back_to_the_listing(self, fake_praw):
        """Bad credentials should not lose the topic while the public listing
        still answers."""
        fake_praw.Reddit.side_effect = RuntimeError("401 invalid_grant")

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing([_submission()] * 3))) as get:
            items = RedditAPI().get_items()

        assert get.call_count == len(_SUBS)
        assert len(items) == 6

    def test_a_missing_praw_falls_back_to_the_listing(self, monkeypatch):
        monkeypatch.setattr(config, "reddit_client_id", "id")
        monkeypatch.setattr(config, "reddit_client_secret", "secret")
        monkeypatch.setitem(sys.modules, "praw", None)  # import praw -> ImportError

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing([_submission()] * 3))) as get:
            items = RedditAPI().get_items()

        assert get.call_count == len(_SUBS)
        assert len(items) == 6


@pytest.mark.unit
class TestGetNews:
    def test_the_payload_holds_the_surviving_posts(self):
        submissions = [_submission(title=f"Ordinary post {i}") for i in range(5)]

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing(submissions))):
            payload = RedditAPI().get_news()

        assert "r/cooking" in payload
        assert "Ordinary post 0" in payload

    def test_a_blacklisted_post_does_not_reach_the_payload(self):
        submissions = [_submission(title=f"Ordinary post {i}") for i in range(8)]
        submissions.append(_submission(title="This one says badword aloud"))

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing(submissions))):
            payload = RedditAPI().get_news()

        assert "badword" not in payload

    def test_announcements_do_not_reach_the_payload(self):
        submissions = [_submission(title=f"Ordinary post {i}") for i in range(4)]
        submissions.append(_submission(title="Monthly rules thread", stickied=True))

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing(submissions))):
            payload = RedditAPI().get_news()

        assert "Monthly rules thread" not in payload

    def test_announcements_do_not_spend_the_attrition_budget(self):
        """Four clean posts and four stickied ones would read as 50% rejected
        if the announcements went through the shared filter."""
        submissions = [_submission(title=f"Ordinary post {i}") for i in range(4)]
        submissions += [_submission(title=f"Rules thread {i}", stickied=True) for i in range(4)]

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing(submissions))):
            payload = RedditAPI().get_news()

        assert "Ordinary post 0" in payload

    def test_the_header_names_the_communities_it_drew_from(self):
        submissions = [_submission(title=f"Ordinary post {i}", subreddit="woodworking")
                       for i in range(5)]

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing(submissions))):
            payload = RedditAPI().get_news()

        assert payload.splitlines()[0].startswith("Posts people are discussing today on r/woodworking")

    def test_too_few_survivors_aborts_the_topic(self):
        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing([_submission()]))):
            with pytest.raises(SocialSourceUnusable):
                RedditAPI().get_news()

    def test_the_payload_is_ordered_by_score(self):
        submissions = [
            _submission(title="Quiet post", score=60),
            _submission(title="Loud post", score=9000),
            _submission(title="Middling post", score=500),
        ]

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing(submissions))):
            payload = RedditAPI().get_news()

        assert payload.index("Loud post") < payload.index("Middling post") < payload.index("Quiet post")

    def test_the_total_caps_the_payload(self):
        submissions = [_submission(title=f"Ordinary post {i}") for i in range(20)]

        with patch("extensions.reddit_api.requests.get",
                   return_value=_response(_listing(submissions))):
            payload = RedditAPI().get_news(total=4)

        assert payload.count("Ordinary post") == 4
