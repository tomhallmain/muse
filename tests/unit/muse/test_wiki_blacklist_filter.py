"""Tests for the wiki article blacklist paragraph-skip and single-paragraph rejection."""

import pytest
from unittest.mock import MagicMock

from extensions.wiki_opensearch_api import RandomWikiResponse
from library_data.blacklist import Blacklist, BlacklistItem
from muse.muse import Muse


def _make_response(title: str, paragraphs: list) -> RandomWikiResponse:
    extract = "\n".join(paragraphs)
    return RandomWikiResponse(
        {"query": {"pages": {"1": {"title": title, "extract": extract}}}}
    )


def _make_muse(*responses) -> MagicMock:
    muse = MagicMock()
    muse.wiki_search = MagicMock()
    muse.wiki_search.random_wiki.side_effect = list(responses)
    muse.get_prompt.return_value = "{ARTICLE}"
    muse.generate_text.return_value = "summary"
    return muse


@pytest.fixture(autouse=True)
def _isolated_blacklist():
    Blacklist.set_blacklist([BlacklistItem("badword")])
    yield
    Blacklist.clear()


@pytest.mark.unit
class TestWikiBlacklistFilter:
    def test_single_violation_in_multi_paragraph_skips_paragraph_and_notifies(self):
        """One violated paragraph is dropped and the LLM prompt flags the omission."""
        response = _make_response(
            "Clean Title",
            ["Safe paragraph.", "This contains badword here.", "Another safe paragraph."],
        )
        muse = _make_muse(response)

        Muse.talk_about_random_wiki_article(muse, MagicMock())

        prompt = muse.generate_text.call_args.args[0]
        assert "badword" not in prompt
        assert "omitted" in prompt.lower()

    def test_single_paragraph_with_violation_retries_next_article(self):
        """A one-paragraph violated article is rejected; the next clean article is used."""
        bad = _make_response("Clean Title", ["Only paragraph but badword here."])
        good = _make_response("Clean Title", ["Safe para one.", "Safe para two."])
        muse = _make_muse(bad, good)

        Muse.talk_about_random_wiki_article(muse, MagicMock())

        assert muse.wiki_search.random_wiki.call_count == 2
        prompt = muse.generate_text.call_args.args[0]
        assert "badword" not in prompt
        assert "omitted" not in prompt.lower()
