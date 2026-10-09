"""Tests for tts/providers/numba_fallback.py, the plain-Python stand-ins a
compiled build uses for numba's stencil, vectorize and guvectorize.

Real numba compiles in a checkout, so the stand-ins are compared against it
directly, and librosa's functions that use them are compared run with and
without the stand-ins installed (in subprocesses, so the patched numba never
reaches this test process).
"""

import json
import subprocess
import sys

import numpy as np
import pytest

from tts.providers import numba_fallback


def _neighbour_sum(a):
    return a[-1] + a[1]


def _diagonal(a):
    return a[0, 1] + a[1, 0] - a[-1, -1]


def _scaled_difference(a, b, scale):
    return (a[1] - b[0]) * scale


def _mixed_return(a):
    # An int in one branch and a float in the other, like librosa's
    # parabolic interpolation stencil.
    if a[0] > 0:
        return 0
    return a[1] / 2.0


def _add(x, y):
    return x + y


def _add_scalar(x, y, out):
    for i in range(x.shape[0]):
        out[i] = x[i] + y


def _sum_into_scalar(x, out):
    out[0] = x.sum()


@pytest.fixture
def numba():
    return pytest.importorskip("numba")


@pytest.mark.unit
class TestStencil:
    def test_1d_matches_numba(self, numba):
        x = np.arange(10, dtype=np.float64) ** 2
        np.testing.assert_array_equal(numba_fallback.stencil(_neighbour_sum)(x), numba.stencil(_neighbour_sum)(x))

    def test_2d_matches_numba(self, numba):
        x = np.random.default_rng(0).standard_normal((5, 6))
        np.testing.assert_allclose(numba_fallback.stencil(_diagonal)(x), numba.stencil(_diagonal)(x))

    def test_several_arrays_and_a_scalar_match_numba(self, numba):
        rng = np.random.default_rng(1)
        a, b = rng.standard_normal(8), rng.standard_normal(8)
        np.testing.assert_allclose(
            numba_fallback.stencil(_scaled_difference)(a, b, 3.0),
            numba.stencil(_scaled_difference)(a, b, 3.0),
        )

    def test_cval_matches_numba(self, numba):
        x = np.arange(6, dtype=np.float64)
        np.testing.assert_array_equal(
            numba_fallback.stencil(cval=-1.0)(_neighbour_sum)(x),
            numba.stencil(cval=-1.0)(_neighbour_sum)(x),
        )

    def test_mixed_int_and_float_returns_keep_the_floats(self, numba):
        x = np.array([1.0, -1.0, 3.0, -2.0, 5.0, -7.0])
        result = numba_fallback.stencil(_mixed_return)(x)
        assert result.dtype.kind == "f"
        np.testing.assert_allclose(result, numba.stencil(_mixed_return)(x))

    def test_out_argument(self):
        x = np.arange(5, dtype=np.float64)
        out = np.full(5, 99.0)
        returned = numba_fallback.stencil(_neighbour_sum)(x, out=out)
        assert returned is out
        np.testing.assert_array_equal(out, [0.0, 2.0, 4.0, 6.0, 0.0])

    def test_border_cells_get_cval(self):
        result = numba_fallback.stencil(_neighbour_sum)(np.ones(4))
        np.testing.assert_array_equal(result, [0.0, 2.0, 2.0, 0.0])

    def test_unsupported_option_raises(self):
        with pytest.raises(NotImplementedError, match="neighborhood"):
            numba_fallback.stencil(neighborhood=((-1, 1),))(_neighbour_sum)


@pytest.mark.unit
class TestVectorize:
    def test_with_signatures_matches_numba(self, numba):
        x = np.arange(3, dtype=np.float64).reshape(3, 1)
        y = np.arange(4, dtype=np.float64)
        expected = numba.vectorize(["float64(float64, float64)"])(_add)(x, y)
        np.testing.assert_array_equal(numba_fallback.vectorize(["float64(float64, float64)"])(_add)(x, y), expected)

    def test_bare_decorator(self):
        np.testing.assert_array_equal(numba_fallback.vectorize(_add)(np.arange(3), 1), [1, 2, 3])

    def test_out_argument(self):
        out = np.zeros(3)
        returned = numba_fallback.vectorize(_add)(np.arange(3), 1, out=out)
        assert returned is out
        np.testing.assert_array_equal(out, [1.0, 2.0, 3.0])


@pytest.mark.unit
class TestGuvectorize:
    def test_scalar_input_with_broadcast_loop_matches_numba(self, numba):
        x = np.arange(6, dtype=np.float64).reshape(2, 3)
        y = np.array([10.0, 20.0])
        expected = np.zeros_like(x)
        numba.guvectorize(["void(float64[:], float64, float64[:])"], "(n),()->(n)")(_add_scalar)(x, y, expected)
        out = np.zeros_like(x)
        returned = numba_fallback.guvectorize(["void(float64[:], float64, float64[:])"], "(n),()->(n)")(_add_scalar)(
            x, y, out
        )
        assert returned is out
        np.testing.assert_array_equal(out, expected)

    def test_scalar_output_matches_numba(self, numba):
        x = np.arange(6, dtype=np.float64).reshape(2, 3)
        expected = np.zeros(2)
        numba.guvectorize(["void(float64[:], float64[:])"], "(n)->()")(_sum_into_scalar)(x, expected)
        out = np.zeros(2)
        numba_fallback.guvectorize("(n)->()")(_sum_into_scalar)(x, out)
        np.testing.assert_array_equal(out, expected)

    def test_layout_as_keyword(self):
        out = np.zeros(3)
        numba_fallback.guvectorize(signature="(n),()->(n)")(_add_scalar)(np.arange(3.0), 1.0, out)
        np.testing.assert_array_equal(out, [1.0, 2.0, 3.0])

    def test_missing_output_raises(self):
        gufunc = numba_fallback.guvectorize("(n),()->(n)")(_add_scalar)
        with pytest.raises(NotImplementedError, match="_add_scalar"):
            gufunc(np.arange(3.0), 1.0)

    def test_keyword_arguments_raise(self):
        gufunc = numba_fallback.guvectorize("(n),()->(n)")(_add_scalar)
        with pytest.raises(NotImplementedError):
            gufunc(np.arange(3.0), 1.0, out=np.zeros(3))

    def test_no_layout_raises(self):
        with pytest.raises(NotImplementedError):
            numba_fallback.guvectorize(["void(float64[:], float64[:])"])


@pytest.mark.unit
class TestInstall:
    def test_replaces_numbas_decorators(self, numba, monkeypatch):
        import numba.np.ufunc as ufunc
        import numba.stencils.stencil as stencil_module

        # Registered with their current values so monkeypatch restores them.
        for module, name in (
            (numba, "stencil"), (stencil_module, "stencil"),
            (numba, "vectorize"), (ufunc, "vectorize"),
            (numba, "guvectorize"), (ufunc, "guvectorize"),
        ):
            monkeypatch.setattr(module, name, getattr(module, name))
        numba_fallback.install()
        assert numba.stencil is stencil_module.stencil is numba_fallback.stencil
        assert numba.vectorize is ufunc.vectorize is numba_fallback.vectorize
        assert numba.guvectorize is ufunc.guvectorize is numba_fallback.guvectorize


# Runs librosa's functions that use the stencil/vectorize/guvectorize
# decorators; argv[1] == "fallback" installs the stand-ins from the file in
# argv[2] first. Prints one
# JSON object: function name -> result as a list, or the exception type name.
_LIBROSA_SCRIPT = r"""
import json
import sys

import numpy as np

if sys.argv[1] == "fallback":
    # Loaded by path: importing the tts package would load the app's config
    # and caches, outside the test process's isolation.
    import importlib.util
    spec = importlib.util.spec_from_file_location("numba_fallback", sys.argv[2])
    numba_fallback = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(numba_fallback)
    numba_fallback.install()

import librosa
from librosa.core.pitch import _parabolic_interpolation

rng = np.random.default_rng(0)
y = rng.standard_normal(512).astype(np.float32)
x2 = rng.standard_normal((3, 64))
z = (rng.standard_normal(64) + 1j * rng.standard_normal(64)).astype(np.complex64)
onset = np.abs(rng.standard_normal(400)).astype(np.float32)

calls = {
    "zero_crossings": lambda: librosa.zero_crossings(y),
    "zero_crossings_threshold": lambda: librosa.zero_crossings(y, threshold=0.5, zero_pos=False),
    "localmax": lambda: librosa.util.localmax(x2, axis=-1),
    "localmin": lambda: librosa.util.localmin(x2, axis=-1),
    "abs2": lambda: librosa.util.abs2(z),
    "peak_pick": lambda: librosa.util.peak_pick(
        onset, pre_max=3, post_max=3, pre_avg=3, post_avg=5, delta=0.5, wait=10),
    "parabolic_interpolation": lambda: _parabolic_interpolation(x2, axis=-1),
    "beat_track": lambda: librosa.beat.beat_track(onset_envelope=onset, sr=22050)[1],
}
results = {}
for name, call in calls.items():
    try:
        results[name] = np.asarray(call()).tolist()
    except Exception as e:
        results[name] = type(e).__name__
json.dump(results, sys.stdout)
"""


def _run_librosa(mode):
    result = subprocess.run(
        [sys.executable, "-c", _LIBROSA_SCRIPT, mode, numba_fallback.__file__],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stderr
    # Anything librosa or numba prints goes before the JSON line.
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def librosa_results():
    pytest.importorskip("numba")
    pytest.importorskip("librosa")
    return _run_librosa("numba"), _run_librosa("fallback")


@pytest.mark.unit
@pytest.mark.slow
class TestLibrosaWithStandIns:
    @pytest.mark.parametrize("name", [
        "zero_crossings", "zero_crossings_threshold", "localmax", "localmin",
        "abs2", "peak_pick", "parabolic_interpolation",
    ])
    def test_matches_numba(self, librosa_results, name):
        with_numba, with_stand_ins = librosa_results
        assert not isinstance(with_numba[name], str), with_numba[name]
        assert not isinstance(with_stand_ins[name], str), with_stand_ins[name]
        np.testing.assert_allclose(
            np.asarray(with_stand_ins[name], dtype=float), np.asarray(with_numba[name], dtype=float), rtol=1e-6
        )

    def test_beat_tracking_is_not_supported(self, librosa_results):
        """librosa's beat tracker calls gufuncs without their outputs, which
        the stand-in does not allocate. Muse does not use beat tracking."""
        with_numba, with_stand_ins = librosa_results
        assert not isinstance(with_numba["beat_track"], str)
        assert with_stand_ins["beat_track"] == "NotImplementedError"
