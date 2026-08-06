"""Unit tests for FormsData save/delete against the DB."""

import pytest

from library_data.form import Form, FormsData, FormsDataSearch


@pytest.mark.unit
class TestFormsDataPersistence:
    def test_search_finds_seeded_form(self):
        data = FormsData()
        search = FormsDataSearch(form="sonata")
        data.do_search(search)
        names = [f.name for f in search.get_results()]
        assert "sonata" in names

    def test_save_and_delete_form_roundtrip(self):
        data = FormsData()
        name = "__muse_test_form_xyzz__"
        existing = data._forms.get(name)
        if existing:
            data.delete_form(existing)

        form = Form(name=name, transliterations=[name, "xyzzform"], notes={"k": "v"})
        ok, err = data.save_form(form)
        assert ok, err
        assert name in data._forms
        assert data._forms[name].notes.get("k") == "v"

        renamed = Form(name=name + "_2", transliterations=[name + "_2"], notes={})
        ok, err = data.save_form(renamed, original_name=name)
        assert ok, err
        assert name not in data._forms
        assert name + "_2" in data._forms

        ok, err = data.delete_form(renamed)
        assert ok, err
        assert name + "_2" not in data._forms

        reloaded = FormsData()
        assert name not in reloaded._forms
        assert name + "_2" not in reloaded._forms
