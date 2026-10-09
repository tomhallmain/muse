"""Plain-Python stand-ins for numba's compiling decorators in a compiled build.

``numba.stencil``, ``numba.vectorize`` and ``numba.guvectorize`` compile the
decorated function as soon as they decorate: they read its bytecode, which
functions Nuitka compiled do not have, and ``cache=True`` needs the source
file, which the build does not ship. The build's ``numba-disable-jit`` covers
``jit``/``njit`` only. librosa uses all three at import, and Coqui's audio
utilities import librosa. The stand-ins evaluate the functions in Python with
the same calling conventions, so they are correct but slow on large arrays.
"""

import re

import numpy as np


class _OutsideArray(Exception):
    """A stencil kernel read a cell beyond the array's edge."""


class _RelativeView:
    """The array as a stencil kernel sees it: indexed relative to one cell."""

    def __init__(self, array: np.ndarray, center: tuple):
        self._array = array
        self._center = center

    def __getitem__(self, offset):
        offsets = offset if isinstance(offset, tuple) else (offset,)
        index = tuple(c + o for c, o in zip(self._center, offsets))
        if any(i < 0 or i >= n for i, n in zip(index, self._array.shape)):
            raise _OutsideArray(index)
        return self._array[index]


class PythonStencil:
    """Applies a stencil kernel cell by cell, as numba's default options do:
    every array argument is indexed relative to the current cell, and cells
    whose neighbourhood leaves the array get ``cval`` (0)."""

    def __init__(self, kernel, options: dict):
        unsupported = set(options) - {"cval"}
        if unsupported:
            raise NotImplementedError(f"stencil options not supported in this build: {sorted(unsupported)}")
        self.kernel = kernel
        self.cval = options.get("cval", 0)

    def __call__(self, *args, out=None):
        shape = next(a.shape for a in args if isinstance(a, np.ndarray))
        values = {}
        for cell in np.ndindex(shape):
            views = [_RelativeView(a, cell) if isinstance(a, np.ndarray) else a for a in args]
            try:
                values[cell] = self.kernel(*views)
            except _OutsideArray:
                pass  # a border cell
        dtype = np.asarray(next(iter(values.values()))).dtype if values else np.asarray(self.cval).dtype
        result = out if out is not None else np.empty(shape, dtype=dtype)
        result[...] = self.cval
        for cell, value in values.items():
            result[cell] = value
        return result


def stencil(func_or_mode="constant", **options):
    """Same call forms as ``numba.stencil``: bare decorator, or with options."""
    if callable(func_or_mode):
        return PythonStencil(func_or_mode, options)
    return lambda func: PythonStencil(func, options)


class PythonVectorized:
    """An elementwise function applied over broadcast arrays (``numba.vectorize``)."""

    def __init__(self, func):
        self.func = func
        self._vectorized = np.vectorize(func)

    def __call__(self, *args, out=None):
        result = self._vectorized(*args)
        if out is None:
            return result
        out[...] = result
        return out


def vectorize(ftylist_or_function=(), **kwargs):
    """Same call forms as ``numba.vectorize``; signatures and options are ignored."""
    if callable(ftylist_or_function):
        return PythonVectorized(ftylist_or_function)
    return PythonVectorized


class PythonGufunc:
    """A generalized ufunc kernel looped over the non-core dimensions
    (``numba.guvectorize``). The kernel writes its results into the output
    arrays, which the caller must pass as arguments; numba's gufuncs also
    accept that form, and allocate missing outputs, which this does not."""

    def __init__(self, func, layout: str):
        inputs, outputs = layout.replace(" ", "").split("->")
        self.func = func
        # Number of core dimensions of each argument, e.g. "(n),()" -> [1, 0].
        self.core_ndims = [len([d for d in group.split(",") if d])
                           for group in re.findall(r"\(([^)]*)\)", inputs + outputs)]
        self.n_outputs = len(re.findall(r"\(", outputs))

    def __call__(self, *args, **kwargs):
        if kwargs or len(args) != len(self.core_ndims):
            raise NotImplementedError(
                f"{self.func.__name__}: this build's gufunc stand-in needs every output "
                "passed as an argument and no keyword arguments"
            )
        arrays = [np.asarray(a) for a in args]
        loop_shapes = [a.shape[:a.ndim - n] for a, n in zip(arrays, self.core_ndims)]
        loop_shape = np.broadcast_shapes(*loop_shapes)
        n_inputs = len(args) - self.n_outputs
        for index in np.ndindex(loop_shape):
            call_args = []
            for position, (array, loop, core) in enumerate(zip(arrays, loop_shapes, self.core_ndims)):
                # Align the loop index to this argument's loop dims (broadcasting).
                own = tuple(0 if size == 1 else i
                            for i, size in zip(index[len(index) - len(loop):], loop))
                cell = array[own + (Ellipsis,)]
                # Scalar inputs as numpy scalars; outputs and core dims as
                # views, so the kernel's writes land in the caller's arrays.
                call_args.append(cell[()] if core == 0 and position < n_inputs else cell)
            self.func(*call_args)
        outputs = args[len(args) - self.n_outputs:]
        return outputs[0] if self.n_outputs == 1 else tuple(outputs)


def guvectorize(*args, **kwargs):
    """Same call forms as ``numba.guvectorize``: ``(ftylist, layout)`` or ``(layout)``."""
    layout = args[-1] if args and isinstance(args[-1], str) else kwargs.get("signature")
    if not isinstance(layout, str):
        raise NotImplementedError("guvectorize without a layout string is not supported in this build")
    return lambda func: PythonGufunc(func, layout)


def install() -> None:
    """Replace numba's compiling decorators before librosa imports them."""
    try:
        import numba
        import numba.np.ufunc as ufunc
        import numba.stencils.stencil as stencil_module
    except ImportError:
        return
    numba.stencil = stencil_module.stencil = stencil
    numba.vectorize = ufunc.vectorize = vectorize
    numba.guvectorize = ufunc.guvectorize = guvectorize
