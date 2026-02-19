"""
Sort configuration dialog (PySide6).

Opens as a modal dialog from PlaylistModifyWindow (per-descriptor) or
MasterPlaylistWindow (master override).  Returns an updated SortConfig
on accept, or None on cancel.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QSpinBox,
    QLabel,
    QPushButton,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt

from muse.sort_config import SortConfig
from ui_qt.app_style import AppStyle
from utils.translations import I18N

_ = I18N._


class SortConfigWindow(QDialog):
    """Modal dialog for editing a :class:`SortConfig`."""

    def __init__(self, parent=None, sort_config=None, is_override=False):
        super().__init__(parent)
        self.setWindowTitle(
            _("Sort Config Override") if is_override else _("Sort Options")
        )
        self.setMinimumWidth(360)
        self.setStyleSheet(AppStyle.get_stylesheet())
        self._is_override = is_override
        self._source = sort_config or SortConfig()
        self._result = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        if self._is_override:
            hint = QLabel(
                _("Non-default values here override every playlist in the master config."),
                self,
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)

        self._skip_memory_check = QCheckBox(_("Skip memory reshuffle"), self)
        self._skip_memory_check.setToolTip(
            _("Disable recently-played memory reshuffling")
        )
        self._skip_memory_check.setChecked(self._source.skip_memory_shuffle)
        layout.addWidget(self._skip_memory_check)

        self._skip_random_start_check = QCheckBox(_("Skip random start"), self)
        self._skip_random_start_check.setToolTip(
            _("Use deterministic grouping order instead of random start-track seeding")
        )
        self._skip_random_start_check.setChecked(self._source.skip_random_start)
        layout.addWidget(self._skip_random_start_check)

        self._check_entire_check = QCheckBox(_("Thorough playlist memory check"), self)
        self._check_entire_check.setToolTip(
            _("Force the thorough scour-based memory check for all playlist sizes")
        )
        self._check_entire_check.setChecked(self._source.check_entire_playlist)
        layout.addWidget(self._check_entire_check)

        # Check count override
        cc_row = QHBoxLayout()
        self._cc_enabled_check = QCheckBox(_("Check count override:"), self)
        self._cc_enabled_check.setToolTip(
            _(
                "Override the adaptive recently-played check count "
                "with a fixed value"
            )
        )
        cc_row.addWidget(self._cc_enabled_check)

        self._cc_spin = QSpinBox(self)
        self._cc_spin.setRange(1, 100000)
        self._cc_spin.setValue(self._source.check_count_override or 100)
        self._cc_spin.setEnabled(self._source.check_count_override is not None)
        cc_row.addWidget(self._cc_spin)
        cc_row.addStretch()
        layout.addLayout(cc_row)

        self._cc_enabled_check.setChecked(self._source.check_count_override is not None)
        self._cc_enabled_check.toggled.connect(self._cc_spin.setEnabled)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def _on_accept(self):
        self._result = SortConfig(
            skip_memory_shuffle=self._skip_memory_check.isChecked(),
            skip_random_start=self._skip_random_start_check.isChecked(),
            check_count_override=(
                self._cc_spin.value() if self._cc_enabled_check.isChecked() else None
            ),
            check_entire_playlist=self._check_entire_check.isChecked(),
        )
        self.accept()

    def get_result(self):
        """Return the configured SortConfig, or None if the dialog was cancelled."""
        return self._result
