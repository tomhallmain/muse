"""Tests for muse.radio_novelty: the gates, signals and scoring behind radio suggestions."""

import importlib
from types import SimpleNamespace

import pytest

from muse import radio_novelty
from muse.radio_novelty import (
    SIGNAL_ARTIST,
    SIGNAL_COMPOSER,
    SIGNAL_STATION,
    SIGNAL_TITLE,
    LibraryIndex,
    NoveltyEvaluator,
    StationInfo,
)

STATION = StationInfo(uuid="st-1", name="Radio Example", tags="pop,rock")
CLASSICAL_STATION = StationInfo(uuid="st-2", name="Klassik Radio", tags="classical,orchestral")


def _track(title, artist=None, composer=None, albumartist=None):
    return SimpleNamespace(title=title, tracktitle=title, artist=artist, composer=composer,
                           albumartist=albumartist)


LIBRARY_TRACKS = [
    _track("Cello Suite No. 1", artist="Yo-Yo Ma", composer="Johann Sebastian Bach"),
    _track("Bohemian Rhapsody", artist="Queen"),
    _track("Symphony No. 5", artist="Berliner Philharmoniker", composer="Ludwig van Beethoven"),
]
KNOWN_COMPOSERS = {"bach": "Johann Sebastian Bach", "beethoven": "Ludwig van Beethoven",
                   "lajtha": "László Lajtha"}


def _infer(artist, title):
    text = f"{artist} {title}".lower()
    return [name for word, name in KNOWN_COMPOSERS.items() if word in text]


class _Cache(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value):
        self[key] = value


class _Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def _entry(classical="no", **novelty):
    return SimpleNamespace(classical=classical, novelty=novelty)


@pytest.fixture
def cfg(monkeypatch):
    config = importlib.import_module("utils.config").config
    for key, value in {
        "radio_novelty_warmup_minutes": 60,
        "radio_novelty_suggestion_cooldown_minutes": 0,
        "radio_watchlist_cooldown_minutes": 30,
        "radio_novelty_seen_titles_per_station": 100,
        "radio_novelty_non_track_patterns": ["werbung", "news", "http"],
        "radio_novelty_classical_tags": ["classical", "klassik"],
    }.items():
        monkeypatch.setattr(config, key, value, raising=False)
    from library_data.blacklist import Blacklist
    monkeypatch.setattr(Blacklist, "get_violation_item", staticmethod(lambda text, item_type=None: None))
    return config


@pytest.fixture
def make(cfg):
    def build(heard=(), tracks=None, cache=None, clock=None):
        library = LibraryIndex(lambda: tracks if tracks is not None else LIBRARY_TRACKS, _infer)
        heard_keys = set(heard)
        evaluator = NoveltyEvaluator(
            library, lambda artist, title: (artist, title) in heard_keys,
            cache=cache if cache is not None else _Cache(), clock=clock or _Clock(),
        )
        return evaluator
    return build


@pytest.mark.unit
class TestNonTrackFilter:
    @pytest.mark.parametrize("artist,title", [
        ("", "Werbung"),
        ("Radio Example", "News at noon"),
        ("", "Radio Example"),
        ("", "ab"),
        ("Visit", "http www radio example de"),
    ])
    def test_non_tracks_are_filtered(self, make, artist, title):
        assert make().is_non_track(artist, title, STATION.name)

    def test_a_pattern_inside_a_word_does_not_filter(self, make):
        assert not make().is_non_track("Newsboys", "Shine", STATION.name)

    def test_blacklisted_text_is_filtered(self, make, monkeypatch):
        from library_data.blacklist import Blacklist
        monkeypatch.setattr(Blacklist, "get_violation_item",
                            staticmethod(lambda text, item_type=None: object() if "Bad" in text else None))
        assert make().is_non_track("Bad Band", "Song", STATION.name)


@pytest.mark.unit
class TestGates:
    def test_a_heard_title_is_not_suggested(self, make):
        evaluator = make(heard={("New Band", "New Song")})
        assert evaluator.evaluate(_entry(), STATION, "New Band", "New Song") is None

    def test_a_library_title_is_not_suggested(self, make):
        assert make().evaluate(_entry(), STATION, "Queen", "Bohemian Rhapsody") is None

    def test_a_library_title_by_another_artist_is_not_that_title(self, make):
        suggestion = make().evaluate(_entry(), STATION, "Panic Band", "Bohemian Rhapsody")
        assert suggestion is not None and SIGNAL_TITLE in suggestion.signals

    def test_without_a_title_the_gates_pass_and_signals_decide(self, make):
        suggestion = make().evaluate(_entry(), STATION, "Totally New Artist", "")
        assert suggestion is not None
        assert suggestion.signals == [SIGNAL_ARTIST]


@pytest.mark.unit
class TestSignals:
    def test_a_new_title_alone_reaches_the_threshold(self, make):
        suggestion = make().evaluate(_entry(), STATION, "Queen", "A Song Not In The Library")
        assert suggestion.signals == [SIGNAL_TITLE]
        assert suggestion.score == pytest.approx(1.0)

    def test_a_new_composer_is_a_signal(self, make):
        suggestion = make().evaluate(_entry(classical="no"), STATION, "Unknown Quartet", "Lajtha Concerto")
        assert SIGNAL_COMPOSER in suggestion.signals

    def test_an_artist_naming_the_inferred_composer_is_not_also_a_new_artist(self, make):
        suggestion = make().evaluate(_entry(classical="no"), STATION, "Lajtha", "")
        assert suggestion.signals == [SIGNAL_COMPOSER]

    def test_a_known_composer_as_artist_is_not_a_new_artist(self, make):
        assert make().evaluate(_entry(), STATION, "Bach", "") is None

    def test_a_known_artist_by_part_of_the_name_is_not_new(self, make):
        assert make().evaluate(_entry(), STATION, "Berliner Philharmoniker & Someone Else", "") is None

    def test_new_to_station_only_after_warm_up(self, make):
        clock = _Clock()
        evaluator = make(clock=clock)
        entry = _entry(**{"weights": {SIGNAL_ARTIST: 0.0}, "threshold": 0.3})
        # Before warm-up: the station signal is withheld.
        assert evaluator.evaluate(entry, STATION, "Queen", "") is None
        clock.now += 61 * 60
        suggestion = evaluator.evaluate(entry, STATION, "Queen", "Another Take")
        assert suggestion is not None and SIGNAL_STATION in suggestion.signals

    def test_a_title_seen_before_on_the_station_is_not_new_to_it(self, make):
        clock = _Clock()
        evaluator = make(clock=clock)
        entry = _entry(**{"weights": {SIGNAL_TITLE: 0.0}, "threshold": 0.3})
        evaluator.evaluate(entry, STATION, "Queen", "Repeated Song")
        clock.now += 61 * 60
        assert evaluator.evaluate(entry, STATION, "Queen", "Repeated Song") is None


@pytest.mark.unit
class TestClassicalWeighting:
    def test_a_new_performer_alone_is_weak_on_a_classical_station(self, make):
        assert make().evaluate(_entry(classical="yes"), CLASSICAL_STATION, "Unknown Quartet", "") is None

    def test_the_same_performer_is_enough_elsewhere(self, make):
        suggestion = make().evaluate(_entry(classical="no"), STATION, "Unknown Quartet", "")
        assert suggestion is not None and suggestion.signals == [SIGNAL_ARTIST]

    def test_performer_plus_new_to_station_is_still_under_the_threshold(self, make):
        clock = _Clock()
        evaluator = make(clock=clock)
        evaluator.evaluate(_entry(classical="yes"), CLASSICAL_STATION, "Warm Up", "")
        clock.now += 61 * 60
        assert evaluator.evaluate(_entry(classical="yes"), CLASSICAL_STATION, "Unknown Quartet", "") is None

    def test_a_new_composer_is_enough_on_a_classical_station(self, make):
        suggestion = make().evaluate(_entry(classical="yes"), CLASSICAL_STATION, "Lajtha", "")
        assert suggestion is not None and suggestion.signals == [SIGNAL_COMPOSER]
        assert suggestion.score == pytest.approx(1.0)


@pytest.mark.unit
class TestClassicalDetection:
    def test_the_entry_setting_wins(self, make):
        evaluator = make()
        assert evaluator.is_classical(_entry(classical="yes"), STATION)
        assert not evaluator.is_classical(_entry(classical="no"), CLASSICAL_STATION)

    def test_auto_uses_station_tags(self, make):
        evaluator = make()
        assert evaluator.is_classical(_entry(classical="auto"), CLASSICAL_STATION)
        assert not evaluator.is_classical(_entry(classical="auto"), STATION)

    def test_auto_falls_back_to_observed_titles(self, make):
        evaluator = make()
        untagged = StationInfo(uuid="st-3", name="Untagged", tags="")
        for i in range(6):
            evaluator.evaluate(_entry(classical="no"), untagged, "Performer", f"Bach Partita {i}")
        assert evaluator.is_classical(_entry(classical="auto"), untagged)


@pytest.mark.unit
class TestCooldownsAndPersistence:
    def test_the_same_title_is_not_suggested_twice_within_the_cooldown(self, make):
        clock = _Clock()
        evaluator = make(clock=clock)
        assert evaluator.evaluate(_entry(), STATION, "New Band", "Hit") is not None
        clock.now += 60
        assert evaluator.evaluate(_entry(), STATION, "New Band", "Hit") is None
        clock.now += 31 * 60
        assert evaluator.evaluate(_entry(), STATION, "New Band", "Hit") is not None

    def test_the_global_gap_applies_across_stations(self, make, cfg, monkeypatch):
        monkeypatch.setattr(cfg, "radio_novelty_suggestion_cooldown_minutes", 10, raising=False)
        clock = _Clock()
        evaluator = make(clock=clock)
        assert evaluator.evaluate(_entry(), STATION, "New Band", "Hit") is not None
        assert evaluator.evaluate(_entry(), CLASSICAL_STATION, "Other Band", "Other Hit") is None
        clock.now += 11 * 60
        assert evaluator.evaluate(_entry(), CLASSICAL_STATION, "Other Band", "Other Hit") is not None

    def test_seen_titles_survive_a_new_evaluator(self, make):
        cache, clock = _Cache(), _Clock()
        entry = _entry(**{"weights": {SIGNAL_TITLE: 0.0}, "threshold": 0.3})
        make(cache=cache, clock=clock).evaluate(entry, STATION, "Queen", "Old Song")
        clock.now += 61 * 60
        restarted = make(cache=cache, clock=clock)
        assert restarted.evaluate(entry, STATION, "Queen", "Old Song") is None
        assert restarted.evaluate(entry, STATION, "Queen", "Fresh Song") is not None

    def test_nothing_is_suggested_before_the_library_has_loaded(self, make):
        assert make(tracks=[]).evaluate(_entry(), STATION, "New Band", "Hit") is None

    def test_evaluate_never_raises(self, make):
        evaluator = make()
        evaluator._heard = lambda artist, title: (_ for _ in ()).throw(RuntimeError("db"))
        assert evaluator.evaluate(_entry(), STATION, "New Band", "Hit") is None


@pytest.mark.unit
class TestLibraryIndex:
    def test_a_surname_matches_the_full_name(self):
        index = LibraryIndex(lambda: LIBRARY_TRACKS, _infer)
        assert index.has_title("Bach", "Cello Suite No. 1")

    def test_case_accents_and_punctuation_are_ignored(self):
        index = LibraryIndex(lambda: [_track("Élégie, Op. 24", artist="Fauré")], _infer)
        assert index.has_title("faure", "elegie op 24")

    def test_the_index_follows_a_changed_track_list(self):
        tracks = [_track("First", artist="A")]
        index = LibraryIndex(lambda: tracks, _infer)
        assert not index.has_title("B", "Second")
        tracks = tracks + [_track("Second", artist="B")]
        index._tracks_source = lambda: tracks
        assert index.has_title("B", "Second")

    def test_split_artists(self):
        assert radio_novelty.split_artists("Beyoncé ft. Jay-Z & Someone") == ["beyonce", "jay z", "someone"]
        assert radio_novelty.split_artists("Featherstonehaugh") == ["featherstonehaugh"]
