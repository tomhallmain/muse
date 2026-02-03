"""
Debounce helper for Tk: coalesce rapid calls into a single invocation after a quiet period.

Uses the given Tk widget's after() so the callback always runs on the main thread.
Trailing-edge: the last scheduled args/kwargs win when the timer fires.
"""

from typing import Any, Callable, Optional


class Debouncer:
    """
    Schedules a callback to run after a delay. Each schedule() cancels any
    pending run and resets the timer with the new arguments (trailing-edge).
    """

    def __init__(
        self,
        tk_widget: Any,
        delay_seconds: float,
        callback: Callable[..., None],
    ) -> None:
        """
        Args:
            tk_widget: A Tk widget (or any with .after()) used to schedule on the main thread.
            delay_seconds: Quiet period before the callback is invoked.
            callback: Called with the last scheduled (*args, **kwargs) when the timer fires.
        """
        self._widget = tk_widget
        self._delay_ms = int(delay_seconds * 1000)
        self._callback = callback
        self._after_id: Optional[str] = None
        self._pending_args: tuple = ()
        self._pending_kwargs: dict = {}

    def schedule(self, *args: Any, **kwargs: Any) -> None:
        """Schedule the callback to run after the delay with these args. Cancels any pending run."""
        self.cancel()
        self._pending_args = args
        self._pending_kwargs = kwargs
        self._after_id = self._widget.after(self._delay_ms, self._fire)

    def cancel(self) -> None:
        """Cancel any pending invocation."""
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _fire(self) -> None:
        self._after_id = None
        args = self._pending_args
        kwargs = self._pending_kwargs
        self._pending_args = ()
        self._pending_kwargs = {}
        if self._widget.winfo_exists():
            self._callback(*args, **kwargs)
