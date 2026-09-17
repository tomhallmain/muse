"""Unit tests for the Topic helpers that drive rotation and prompt safety.

Each is read from more than one place in muse.py, so a wrong membership here is
a silent behaviour change rather than a failure.
"""

import pytest

from utils.globals import Topic


@pytest.mark.unit
class TestCurrentEvents:
    def test_every_outward_looking_topic_is_included(self):
        assert set(Topic.current_events()) == {
            Topic.WEATHER, Topic.NEWS, Topic.HACKERNEWS,
            Topic.REDDIT, Topic.BLUESKY, Topic.MASTODON,
        }

    def test_excluding_drops_only_that_topic(self):
        others = Topic.current_events(excluding=Topic.MASTODON)

        assert Topic.MASTODON not in others
        assert set(others) == set(Topic.current_events()) - {Topic.MASTODON}

    def test_excluding_an_unrelated_topic_changes_nothing(self):
        assert Topic.current_events(excluding=Topic.JOKE) == Topic.current_events()

    def test_excluding_nothing_returns_the_whole_set(self):
        assert Topic.current_events(excluding=None) == Topic.current_events()


@pytest.mark.unit
class TestFetchedSources:
    def test_the_fetched_sources_are_the_current_events_bar_weather(self):
        """Weather is a forecast for a configured city, so it has no result set
        that a repeat inside the minimum window would re-read."""
        assert set(Topic.fetched_sources()) == set(Topic.current_events()) - {Topic.WEATHER}

    def test_every_fetched_source_is_a_current_events_topic(self):
        assert set(Topic.fetched_sources()) <= set(Topic.current_events())


@pytest.mark.unit
class TestSocialSources:
    def test_the_social_sources_are_the_three_networks(self):
        assert set(Topic.social_sources()) == {Topic.REDDIT, Topic.BLUESKY, Topic.MASTODON}

    def test_every_social_source_is_a_fetched_source(self):
        assert set(Topic.social_sources()) <= set(Topic.fetched_sources())


@pytest.mark.unit
class TestExemptsPromptViolations:
    def test_no_social_payload_is_exempted(self):
        for topic in Topic.social_sources():
            assert topic.exempts_prompt_violations() is False

    def test_a_topic_with_no_fetched_text_is_exempted(self):
        assert Topic.JOKE.exempts_prompt_violations() is True
        assert Topic.WEATHER.exempts_prompt_violations() is True

    def test_every_topic_answers(self):
        """The method feeds a keyword argument, so a None would read as false
        and silently drop the exemption for that topic."""
        for topic in Topic:
            assert isinstance(topic.exempts_prompt_violations(), bool)
