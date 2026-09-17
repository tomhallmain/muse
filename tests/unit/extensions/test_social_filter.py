"""Unit tests for extensions.social_filter -- the content gates every social
source runs its items through.

These gates are the enforcement point for social payloads rather than a first
line of defence, because generate_text exempts violations it finds in the
prompt from the check on its output and a fetched payload is part of the
prompt. Failures here reach the DJ's mouth.
"""

import pytest

from extensions.social_filter import (
    SocialSourceUnusable,
    assemble_payload,
    filter_items,
    source_is_blacklisted,
)
from library_data.blacklist import Blacklist, BlacklistItem
from utils.globals import BlacklistItemType

_GATES = dict(min_score=5, max_age_hours=24, min_surviving=3, max_rejection_ratio=0.4)


class _Item:
    def __init__(self, title="A perfectly ordinary post", source="example.social",
                 score=50, age_hours=1.0, sensitive=False, restricted=False,
                 filter_text=None):
        self.title = title
        self.source = source
        self.score = score
        self.age_hours = age_hours
        self.sensitive = sensitive
        self.restricted = restricted
        self.filter_text = title if filter_text is None else filter_text

    def __str__(self):
        return f"{self.title} (posted on {self.source})"


def _clean(count, **kwargs):
    return [_Item(title=f"Ordinary post number {i}", **kwargs) for i in range(count)]


@pytest.fixture(autouse=True)
def _isolated_blacklist():
    Blacklist.set_blacklist([BlacklistItem("badword")])
    yield
    Blacklist.clear()


@pytest.mark.unit
class TestMetadataGate:
    def test_a_clean_set_passes_untouched(self):
        items = _clean(5)
        assert filter_items(items, **_GATES) == items

    def test_sensitive_is_rejected(self):
        items = _clean(5) + [_Item(title="Flagged", sensitive=True)]
        assert len(filter_items(items, **_GATES)) == 5

    def test_non_public_is_rejected(self):
        items = _clean(5) + [_Item(title="Unlisted", restricted=True)]
        assert len(filter_items(items, **_GATES)) == 5

    def test_below_minimum_score_is_rejected(self):
        items = _clean(5) + [_Item(title="Ignored by everyone", score=4)]
        assert len(filter_items(items, **_GATES)) == 5

    def test_too_old_is_rejected(self):
        items = _clean(5) + [_Item(title="Last week", age_hours=200.0)]
        assert len(filter_items(items, **_GATES)) == 5

    def test_empty_text_is_rejected(self):
        items = _clean(5) + [_Item(title="   ")]
        assert len(filter_items(items, **_GATES)) == 5


@pytest.mark.unit
class TestBlacklistGate:
    def test_a_blacklisted_title_rejects_the_item(self):
        items = _clean(5) + [_Item(title="This one says badword out loud")]
        kept = filter_items(items, **_GATES)
        assert len(kept) == 5
        assert all("badword" not in item.title for item in kept)

    def test_a_violation_outside_the_title_still_rejects(self):
        """filter_text covers the content warning and hashtags, not just the
        text that would be spoken."""
        hidden = _Item(title="Innocuous text", filter_text="Innocuous text\n#badword")
        items = _clean(5) + [hidden]
        assert hidden not in filter_items(items, **_GATES)


@pytest.mark.unit
class TestQuorumAndAttrition:
    def test_too_few_survivors_raises(self):
        items = _clean(2)
        with pytest.raises(SocialSourceUnusable):
            filter_items(items, **_GATES)

    def test_an_empty_fetch_raises(self):
        with pytest.raises(SocialSourceUnusable):
            filter_items([], **_GATES)

    def test_heavy_attrition_raises_even_with_enough_survivors(self):
        """Six clean items would pass the quorum on their own; losing half the
        set to the blacklist means the survivors are a biased remnant."""
        items = _clean(6) + [_Item(title=f"badword {i}") for i in range(6)]

        with pytest.raises(SocialSourceUnusable) as excinfo:
            filter_items(items, **_GATES)

        assert "rejected" in str(excinfo.value)

    def test_attrition_inside_the_limit_passes(self):
        items = _clean(8) + [_Item(title="badword here")]
        assert len(filter_items(items, **_GATES)) == 8

    def test_unusable_is_not_a_web_connection_exception(self):
        """A WebConnectionException makes the DJ apologize for a network fault
        out loud, which would be untrue and would advertise the filtering."""
        from extensions.soup_utils import WebConnectionException

        assert not issubclass(SocialSourceUnusable, WebConnectionException)


@pytest.mark.unit
class TestSourceBlacklist:
    def test_a_blacklisted_source_name_is_caught_as_a_channel(self):
        Blacklist.set_blacklist([BlacklistItem("badplace", item_type=BlacklistItemType.CHANNEL)])

        assert source_is_blacklisted("badplace.social") is True
        assert source_is_blacklisted("example.social") is False

    def test_a_general_blacklist_item_also_applies(self):
        assert source_is_blacklisted("badword.social") is True

    def test_no_name_is_not_blacklisted(self):
        assert source_is_blacklisted("") is False


@pytest.mark.unit
class TestPayloadAssembly:
    def test_each_item_is_rendered_by_its_own_str(self):
        payload = assemble_payload("Header:", _clean(2))

        assert payload.startswith("Header:\n")
        assert "Ordinary post number 0 (posted on example.social)" in payload

    def test_the_total_caps_the_item_count(self):
        payload = assemble_payload("Header:", _clean(10), total=3)

        assert payload.count("Ordinary post number") == 3
