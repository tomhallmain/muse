"""
Blacklist preview window (PySide6).
Port of ui/blacklist_preview_window.py; logic preserved, UI uses Qt.
"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from library_data.blacklist import Blacklist
from ui_qt.app_style import AppStyle
from utils.translations import I18N

_ = I18N._


class BlacklistPreviewWindow(SmartWindow):
    """Window to test arbitrary text against the current blacklist."""

    top_level = None

    def __init__(self, master, app_actions, dimensions: str = "520x420"):
        if BlacklistPreviewWindow.top_level is not None:
            try:
                BlacklistPreviewWindow.top_level.close()
                BlacklistPreviewWindow.top_level.deleteLater()
            except Exception:
                pass
            BlacklistPreviewWindow.top_level = None

        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Blacklist Preview"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        BlacklistPreviewWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.setMinimumSize(400, 300)

        self.setStyleSheet(AppStyle.get_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        input_label = QLabel(
            _("Enter text to test (tags can be comma- or dot-separated):")
        )
        layout.addWidget(input_label)

        self.input_text = QPlainTextEdit(self)
        self.input_text.setPlaceholderText("")
        self.input_text.setMinimumHeight(120)
        self.input_text.setMaximumHeight(180)
        self.input_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.input_text)

        self.test_btn = QPushButton(_("Test against blacklist"), self)
        self.test_btn.clicked.connect(self._run_test)
        layout.addWidget(self.test_btn)

        result_label = QLabel(_("Result:"))
        layout.addWidget(result_label)

        self.result_text = QPlainTextEdit(self)
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(120)
        self.result_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.result_text, 1)

        self.show()

    def _run_test(self):
        text = self.input_text.toPlainText().strip()
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
        self.result_text.setPlainText(content)

    def _on_close(self):
        if BlacklistPreviewWindow.top_level is self:
            BlacklistPreviewWindow.top_level = None
        self.close()

    def closeEvent(self, event):
        self._on_close()
        event.accept()
