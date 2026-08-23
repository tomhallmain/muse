"""Unit tests for scripts/ingest_composer_works.py's cell/filename parsing.

Not under tests/scripts/ or any directory named "scripts" -- pytest.ini's
norecursedirs excludes those from collection.
"""

import pytest

from scripts.ingest_composer_works import _composer_name_from_filename, _parse_cell


@pytest.mark.unit
class TestParseCell:
    def test_opus_dash_title_dash_pub_year(self):
        """IMSLP style, e.g. Abram Chasins's work list."""
        title, catalogue_number, date = _parse_cell("Op.3 - Etude Appassionato - Pub. 1925")

        assert title == "Etude Appassionato"
        assert catalogue_number == "Op.3"
        assert date == "1925"

    def test_opus_dash_title_semicolon_publisher_comma_year(self):
        """IMSLP style, e.g. Aleksandr Krein's work list."""
        title, catalogue_number, date = _parse_cell(
            "Op.1 - 2 Pieces for Violin and Piano; M.: W. Nekrassoff, 1910"
        )

        assert title == "2 Pieces for Violin and Piano"
        assert catalogue_number == "Op.1"
        assert date == "1910"

    def test_no_opus_number_with_trailing_year(self):
        """Some composers (e.g. Caleb Simper) are never catalogued by opus."""
        title, catalogue_number, date = _parse_cell("The Lord reigneth .. 1892")

        assert title == "The Lord reigneth"
        assert catalogue_number is None
        assert date == "1892"

    def test_comma_and_parenthesised_year(self):
        """Wikipedia-by-opus style, e.g. Chopin's compositions by opus number."""
        title, catalogue_number, date = _parse_cell("Op. 1, Rondo in C minor (1825)")

        assert title == "Rondo in C minor"
        assert catalogue_number == "Op. 1"
        assert date == "1825"

    def test_no_catalogue_number_is_not_guessed(self):
        title, catalogue_number, date = _parse_cell("Carmen Fantasy")

        assert title == "Carmen Fantasy"
        assert catalogue_number is None
        assert date is None

    @pytest.mark.parametrize("cell", [None, "", "   ", 123, "--", "1892", "()"])
    def test_degenerate_cells_are_skipped(self, cell):
        assert _parse_cell(cell) is None

    def test_boilerplate_placeholder_row_is_skipped(self):
        """IMSLP's 'Op.7 -' rows (no title filled in yet) shouldn't become a work."""
        assert _parse_cell("Op.7 -") is None


@pytest.mark.unit
class TestComposerNameFromFilename:
    def test_imslp_list_of_works(self):
        assert _composer_name_from_filename(
            "List of works by Abram Chasins (IMSLP).json"
        ) == "Abram Chasins"

    def test_imslp_capitalized_works(self):
        assert _composer_name_from_filename(
            "List of Works by Aleksandr Krein (IMSLP).json"
        ) == "Aleksandr Krein"

    def test_imslp_qualified_works_list(self):
        assert _composer_name_from_filename(
            "List of cello works by Jacques Offenbach (IMSLP).json"
        ) == "Jacques Offenbach"

    def test_wikipedia_list_of_compositions(self):
        assert _composer_name_from_filename(
            "List of compositions by Josef Bohuslav Foerster.json"
        ) == "Josef Bohuslav Foerster"

    def test_wikipedia_by_opus_number_suffix_is_stripped(self):
        assert _composer_name_from_filename(
            "List of compositions by Frédéric Chopin by opus number.json"
        ) == "Frédéric Chopin"

    def test_unrecognised_filename_falls_back_to_the_stem(self):
        assert _composer_name_from_filename("Some Other Page.json") == "Some Other Page"
