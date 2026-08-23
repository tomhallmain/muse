import pytest

from extensions.library_extender import (
    fpl, q4, q8, q13, q14, q16, q18, q19, q21, q23, q29, q36, q37,
)


def _request(response):
    return type("_R", (), {q16: lambda self: response})()


def _resource(response, captured):
    resource = type("_S", (), {})()

    def _list(**kwargs):
        captured.update(kwargs)
        return _request(response)

    setattr(resource, q8, _list)
    return resource


def _client(response, captured):
    client = type("_C", (), {})()
    setattr(client, q36, lambda: _resource(response, captured))
    return client


def _failing_client(error):
    client = type("_C", (), {})()

    def _raise():
        raise error

    setattr(client, q36, _raise)
    return client


class _Option:
    def __init__(self, unresolved=True, ident="PL_source"):
        self.y = unresolved
        self.w = ident
        self.n = "Source Name"
        self.d = "Source Detail"


def _response(target="t_first", name="Target Name", detail="Target Detail"):
    return {q18: [{q4: {q19: name, q21: detail, q37: {q23: target}}}]}


@pytest.mark.unit
class TestFpl:
    def test_first_entry_replaces_the_source(self):
        option = _Option()

        assert fpl(_client(_response(), {}), option) is True

        assert option.w == "t_first"
        assert option.y is False

    def test_target_supplies_the_text_the_filters_read(self):
        option = _Option()

        fpl(_client(_response(name="Real Name", detail="Real Detail"), {}), option)

        assert option.n == "Real Name"
        assert option.d == "Real Detail"

    def test_only_one_entry_is_requested(self):
        captured = {}

        fpl(_client(_response(), captured), _Option(ident="PL_abc"))

        assert captured == {q14: q4, q29: "PL_abc", q13: 1}

    def test_an_already_resolved_option_is_left_alone(self):
        captured = {}
        option = _Option(unresolved=False, ident="t_already")

        assert fpl(_client(_response(), captured), option) is True

        assert option.w == "t_already"
        assert captured == {}

    def test_an_empty_result_stays_unresolved(self):
        option = _Option()

        assert fpl(_client({q18: []}, {}), option) is False

        assert option.y is True
        assert option.w == "PL_source"

    def test_a_missing_result_key_stays_unresolved(self):
        option = _Option()

        assert fpl(_client({}, {}), option) is False

        assert option.y is True

    def test_a_request_failure_stays_unresolved(self):
        option = _Option()

        assert fpl(_failing_client(RuntimeError("quota")), option) is False

        assert option.y is True

    def test_a_malformed_entry_stays_unresolved(self):
        option = _Option()

        assert fpl(_client({q18: [{q4: {q19: "x"}}]}, {}), option) is False

        assert option.y is True

    def test_a_blank_target_stays_unresolved(self):
        option = _Option()

        assert fpl(_client(_response(target="   "), {}), option) is False

        assert option.y is True
        assert option.w == "PL_source"

    def test_text_falls_back_to_the_source_when_absent(self):
        option = _Option()
        response = {q18: [{q4: {q37: {q23: "t_first"}}}]}

        assert fpl(_client(response, {}), option) is True

        assert option.w == "t_first"
        assert option.n == "Source Name"
        assert option.d == "Source Detail"
