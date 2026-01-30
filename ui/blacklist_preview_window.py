"""Blacklist preview window for testing text against the blacklist."""

from tkinter import Frame, Label, StringVar, WORD, scrolledtext
from tkinter.ttk import Button

from lib.multi_display import SmartToplevel
from library_data.blacklist import Blacklist
from ui.app_style import AppStyle
from utils.translations import I18N

_ = I18N._


class BlacklistPreviewWindow:
    """Window to test arbitrary text against the current blacklist."""

    top_level = None

    def __init__(self, master, app_actions, dimensions: str = "520x420"):
        if BlacklistPreviewWindow.top_level is not None:
            try:
                BlacklistPreviewWindow.top_level.destroy()
            except Exception:
                pass
            BlacklistPreviewWindow.top_level = None

        BlacklistPreviewWindow.top_level = SmartToplevel(
            persistent_parent=master,
            title=_("Blacklist Preview"),
            geometry=dimensions,
        )
        self.master = BlacklistPreviewWindow.top_level
        self.app_actions = app_actions

        self.master.config(bg=AppStyle.BG_COLOR)
        self.master.grid_rowconfigure(1, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

        # Input area
        input_label = Label(
            self.master,
            text=_("Enter text to test (tags can be comma- or dot-separated):"),
            bg=AppStyle.BG_COLOR,
            fg=AppStyle.FG_COLOR,
        )
        input_label.grid(row=0, column=0, sticky="w", padx=4, pady=(4, 2))

        self.input_text = scrolledtext.ScrolledText(
            self.master,
            wrap=WORD,
            height=8,
            width=60,
            bg=AppStyle.BG_COLOR,
            fg=AppStyle.FG_COLOR,
            insertbackground=AppStyle.FG_COLOR,
        )
        self.input_text.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)

        # Test button
        self.test_btn = Button(self.master, text=_("Test against blacklist"), command=self._run_test)
        self.test_btn.grid(row=2, column=0, pady=6)

        # Result area
        result_label = Label(
            self.master,
            text=_("Result:"),
            bg=AppStyle.BG_COLOR,
            fg=AppStyle.FG_COLOR,
        )
        result_label.grid(row=3, column=0, sticky="w", padx=4, pady=(4, 2))

        self.result_text = scrolledtext.ScrolledText(
            self.master,
            wrap=WORD,
            height=8,
            width=60,
            state="disabled",
            bg=AppStyle.BG_COLOR,
            fg=AppStyle.FG_COLOR,
        )
        self.result_text.grid(row=4, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.master.grid_rowconfigure(4, weight=1)

        self.master.protocol("WM_DELETE_WINDOW", self._on_close)

    def _run_test(self):
        text = self.input_text.get("1.0", "end").strip()
        if not text:
            self._set_result(_("Enter some text above, then click Test."))
            return

        filtered = Blacklist.find_blacklisted_items(text)
        if not filtered:
            self._set_result(_("No blacklist items matched."))
            return

        lines = [_("Matched {0} item(s):").format(len(filtered)), ""]
        for tag, rule in sorted(filtered.items(), key=lambda x: (x[1], x[0])):
            lines.append(_("  \"{0}\" → rule \"{1}\"").format(tag, rule))
        self._set_result("\n".join(lines))

    def _set_result(self, content: str):
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", content)
        self.result_text.config(state="disabled")

    def _on_close(self):
        self.master.destroy()
        BlacklistPreviewWindow.top_level = None
