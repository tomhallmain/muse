"""
Media controls overlay (PySide6): translucent bar with seek slider,
play/pause button, and elapsed/total time labels.  Sits at the bottom
of MediaFrame and auto-hides after a period of mouse inactivity.

Implemented as a top-level Tool window with WA_TranslucentBackground so it
has its own native handle and renders above VLC's DirectX/OpenGL surface.
"""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSlider,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QPainter, QColor

from ui_qt.app_style import AppStyle
from utils.translations import I18N

_ = I18N._


SLIDER_MAX = 1000
VOLUME_MAX = 100
AUTOHIDE_MS = 3000
FADE_IN_MS = 200
FADE_OUT_MS = 500
OVERLAY_HEIGHT = 44
MUTE_ICON = "🔇"
UNMUTE_ICON = "🔊"


def _fmt_time(ms: int) -> str:
    """Format milliseconds as m:ss or h:mm:ss."""
    if ms < 0:
        ms = 0
    total_secs = ms // 1000
    h = total_secs // 3600
    m = (total_secs % 3600) // 60
    s = total_secs % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class MediaControlsOverlay(QWidget):
    """Translucent controls bar rendered over the bottom of the media frame.

    A top-level Tool window so it floats above VLC's native video surface
    and disappears with the parent window on alt-tab / minimize.
    """

    seek_requested = Signal(int)
    play_pause_requested = Signal()
    volume_changed = Signal(int)
    mute_toggled = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setWindowOpacity(0.0)

        self._is_paused = False
        self._user_is_seeking = False
        self._duration_ms = 0
        self._current_ms = 0
        self._has_track = False
        self._volume = 100
        self._is_muted = False
        self._effective_volume = None

        self._bg_color = QColor(10, 22, 40, 180)
        c = AppStyle.get_colors()
        self._border_color = QColor(c["border"])

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._autohide_timer = QTimer(self)
        self._autohide_timer.setSingleShot(True)
        self._autohide_timer.timeout.connect(self._fade_out)

        self._build_ui()
        self._apply_child_styles()

    # ------------------------------------------------------------------
    # Paint the semi-transparent background ourselves
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg_color)
        p.setPen(self._border_color)
        p.drawLine(0, 0, self.width(), 0)
        p.end()

    # ------------------------------------------------------------------
    # Build child widgets
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self._play_pause_btn = QPushButton("\u25B6", self)
        self._play_pause_btn.setFixedSize(32, 32)
        self._play_pause_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._play_pause_btn.clicked.connect(self._on_play_pause)
        layout.addWidget(self._play_pause_btn)

        self._elapsed_label = QLabel("0:00", self)
        self._elapsed_label.setFixedWidth(52)
        self._elapsed_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._elapsed_label)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._seek_slider.setRange(0, SLIDER_MAX)
        self._seek_slider.setValue(0)
        self._seek_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._seek_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self._seek_slider.sliderReleased.connect(self._on_slider_released)
        self._seek_slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self._seek_slider)

        self._total_label = QLabel("0:00", self)
        self._total_label.setFixedWidth(52)
        self._total_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._total_label)

        self._mute_btn = QPushButton(MUTE_ICON, self)
        self._mute_btn.setFixedSize(32, 32)
        self._mute_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._mute_btn.clicked.connect(self._on_mute_toggle)
        self._mute_btn.setToolTip(_("Mute"))
        layout.addWidget(self._mute_btn)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._volume_slider.setRange(0, VOLUME_MAX)
        self._volume_slider.setValue(self._volume)
        self._volume_slider.setFixedWidth(90)
        self._volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self._volume_slider)

        self._effective_label = QLabel("", self)
        self._effective_label.setFixedWidth(64)
        self._effective_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self._effective_label.setToolTip(
            _("Effective output volume after track normalization. Sidebar/overlay slider sets base volume.")
        )
        layout.addWidget(self._effective_label)

    def _apply_child_styles(self):
        c = AppStyle.get_colors()
        btn_style = (
            f"QPushButton {{"
            f"  background: transparent; color: {c['fg']};"
            f"  border: 1px solid {c['border']}; border-radius: 4px;"
            f"  font-size: 14px;"
            f"}}"
            f"QPushButton:hover {{ background: {c['hover']}; }}"
        )
        self._play_pause_btn.setStyleSheet(btn_style)
        self._mute_btn.setStyleSheet(btn_style)

        label_style = f"color: {c['fg']}; font-size: 11px; background: transparent; border: none;"
        self._elapsed_label.setStyleSheet(label_style)
        self._total_label.setStyleSheet(label_style)
        self._effective_label.setStyleSheet(label_style)

        slider_style = (
            f"QSlider::groove:horizontal {{"
            f"  border: 1px solid {c['border']}; height: 4px;"
            f"  background: {c['input']}; border-radius: 2px;"
            f"}}"
            f"QSlider::handle:horizontal {{"
            f"  background: {c['progress']}; border: 1px solid {c['border']};"
            f"  width: 12px; margin: -4px 0; border-radius: 6px;"
            f"}}"
            f"QSlider::handle:horizontal:hover {{"
            f"  background: {c['hover']};"
            f"}}"
            f"QSlider::sub-page:horizontal {{"
            f"  background: {c['progress']}; border-radius: 2px;"
            f"}}"
        )
        self._seek_slider.setStyleSheet(slider_style)
        self._volume_slider.setStyleSheet(slider_style)
        self._refresh_mute_button()
        self._refresh_effective_label()

    # ------------------------------------------------------------------
    # Public API (called by MediaFrame / app_qt)
    # ------------------------------------------------------------------

    def update_progress(self, current_ms: int, duration_ms: int):
        """Called on every progress tick from the backend."""
        self._current_ms = current_ms
        self._duration_ms = duration_ms
        self._has_track = duration_ms > 0

        if not self._user_is_seeking:
            pos = int((current_ms / duration_ms) * SLIDER_MAX) if duration_ms > 0 else 0
            self._seek_slider.setValue(pos)

        self._elapsed_label.setText(_fmt_time(current_ms))
        self._total_label.setText(_fmt_time(duration_ms))

    def set_paused(self, paused: bool):
        self._is_paused = paused
        self._play_pause_btn.setText("\u25B6" if paused else "\u275A\u275A")

    def on_track_changed(self):
        """Reset state when a new track starts."""
        self._seek_slider.setValue(0)
        self._elapsed_label.setText("0:00")
        self._total_label.setText("0:00")
        self._is_paused = False
        self._play_pause_btn.setText("\u275A\u275A")
        self._has_track = True

    def on_playback_stopped(self):
        """Reset state when nothing is playing."""
        self._has_track = False
        self._is_paused = False
        self._play_pause_btn.setText("\u25B6")
        self._seek_slider.setValue(0)
        self._elapsed_label.setText("0:00")
        self._total_label.setText("0:00")
        self.dismiss()

    def set_volume_state(self, volume: int, muted: bool, effective_volume: int | None = None):
        bounded = max(0, min(int(volume), VOLUME_MAX))
        self._volume = bounded
        self._is_muted = bool(muted)
        self._effective_volume =  None if effective_volume is None else max(0, min(int(effective_volume), VOLUME_MAX))
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(bounded)
        self._volume_slider.blockSignals(False)
        self._refresh_mute_button()
        self._refresh_effective_label()

    # ------------------------------------------------------------------
    # Visibility / auto-hide
    # ------------------------------------------------------------------

    def show_overlay(self):
        if not self._has_track:
            return
        self.show()
        self._fade_in()
        self._restart_autohide()

    def hide_overlay(self):
        self._autohide_timer.stop()
        self._fade_out()

    def dismiss(self):
        """Immediately hide without animation (e.g. parent hidden)."""
        self._autohide_timer.stop()
        self._fade_anim.stop()
        self.setWindowOpacity(0.0)
        self.hide()

    def _fade_in(self):
        self._fade_anim.stop()
        self._fade_anim.setDuration(FADE_IN_MS)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def _fade_out(self):
        if self._user_is_seeking:
            return
        self._fade_anim.stop()
        self._fade_anim.setDuration(FADE_OUT_MS)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_fade_finished(self):
        if self.windowOpacity() < 0.01:
            self.hide()

    def _restart_autohide(self):
        self._autohide_timer.stop()
        self._autohide_timer.start(AUTOHIDE_MS)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_play_pause(self):
        self._restart_autohide()
        self.play_pause_requested.emit()

    def _on_slider_pressed(self):
        self._user_is_seeking = True
        self._autohide_timer.stop()

    def _on_slider_released(self):
        self._user_is_seeking = False
        self._restart_autohide()
        if self._duration_ms > 0:
            ratio = self._seek_slider.value() / SLIDER_MAX
            target_ms = int(ratio * self._duration_ms)
            self.seek_requested.emit(target_ms)

    def _on_slider_moved(self, value: int):
        """Live preview of elapsed time while dragging; also seek-while-paused."""
        if self._duration_ms > 0:
            preview_ms = int((value / SLIDER_MAX) * self._duration_ms)
            self._elapsed_label.setText(_fmt_time(preview_ms))
            if self._is_paused:
                self.seek_requested.emit(preview_ms)

    def _on_volume_changed(self, value: int):
        self._restart_autohide()
        self.volume_changed.emit(int(value))

    def _on_mute_toggle(self):
        self._restart_autohide()
        self.mute_toggled.emit()

    def _refresh_mute_button(self):
        self._mute_btn.setText(UNMUTE_ICON if self._is_muted else MUTE_ICON)
        self._mute_btn.setToolTip(_("Unmute") if self._is_muted else _("Mute"))

    def _refresh_effective_label(self):
        resolved = self._volume if self._effective_volume is None else self._effective_volume
        self._effective_label.setText(str(resolved))

    # ------------------------------------------------------------------
    # Mouse events (keep overlay visible while interacting)
    # ------------------------------------------------------------------

    def enterEvent(self, event):
        super().enterEvent(event)
        self._autohide_timer.stop()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not self._user_is_seeking:
            self._restart_autohide()
