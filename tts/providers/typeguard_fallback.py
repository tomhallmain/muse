"""A pass-through ``typeguard.typechecked`` for a compiled build.

``@typechecked`` rewrites the decorated function from its module's source
(``inspect.getsource``), which the build does not ship, so it raises
``OSError: could not get source code``. inflect, which Coqui's English text
normalizers import, uses it at import. It only adds runtime type checks, so
leaving functions undecorated changes no results.
"""


def typechecked(target=None, **_options):
    """Same call forms as ``typeguard.typechecked``: bare decorator, or with options."""
    if target is None:
        return lambda func: func
    return target


def install() -> None:
    """Replace ``typechecked`` before inflect imports it."""
    try:
        import typeguard
        import typeguard._decorators as decorators
    except ImportError:
        return
    typeguard.typechecked = decorators.typechecked = typechecked
