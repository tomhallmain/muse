"""
Qt (PySide6) application style for Muse.
Dark blue theme. Used by app_qt and ui_qt widgets.
"""


class AppStyle:
    """Application theme and colors for the Qt UI. Dark blue by default."""
    IS_DEFAULT_THEME = True   # True = dark blue theme
    LIGHT_THEME = "light"
    DARK_THEME = "dark"

    # Dark blue palette
    BG_COLOR = "#0a1628"
    FG_COLOR = "#e8ecf0"
    BG_SIDEBAR = "#0d1b2a"
    BG_BUTTON = "#1b2838"
    BG_BUTTON_HOVER = "#243447"
    BG_INPUT = "#162536"
    BORDER_COLOR = "#1b2838"
    PROGRESS_CHUNK = "#2d4a6f"
    MEDIA_BG = "#0d1b2a"

    @staticmethod
    def get_theme_name():
        return AppStyle.DARK_THEME if AppStyle.IS_DEFAULT_THEME else AppStyle.LIGHT_THEME

    @staticmethod
    def get_stylesheet():
        """Return a Qt stylesheet string for the application (dark blue theme)."""
        return f"""
            QMainWindow, QWidget {{
                background-color: {AppStyle.BG_COLOR};
                color: {AppStyle.FG_COLOR};
            }}
            QLabel {{
                color: {AppStyle.FG_COLOR};
            }}
            QPushButton {{
                background-color: {AppStyle.BG_BUTTON};
                color: {AppStyle.FG_COLOR};
                border: 1px solid {AppStyle.BORDER_COLOR};
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {AppStyle.BG_BUTTON_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {AppStyle.BG_INPUT};
            }}
            QComboBox {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.FG_COLOR};
                border: 1px solid {AppStyle.BORDER_COLOR};
                padding: 4px 8px;
                border-radius: 4px;
                min-height: 1.2em;
            }}
            QComboBox:hover {{
                border-color: {AppStyle.PROGRESS_CHUNK};
            }}
            QComboBox::drop-down {{
                border: none;
                background: transparent;
            }}
            QComboBox QAbstractItemView {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.FG_COLOR};
                selection-background-color: {AppStyle.BG_BUTTON_HOVER};
            }}
            QSlider::groove:horizontal {{
                border: 1px solid {AppStyle.BORDER_COLOR};
                height: 6px;
                background: {AppStyle.BG_INPUT};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {AppStyle.PROGRESS_CHUNK};
                border: 1px solid {AppStyle.BORDER_COLOR};
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {AppStyle.BG_BUTTON_HOVER};
            }}
            QCheckBox {{
                color: {AppStyle.FG_COLOR};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {AppStyle.BORDER_COLOR};
                border-radius: 3px;
                background: {AppStyle.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background: {AppStyle.PROGRESS_CHUNK};
            }}
            QProgressBar {{
                border: 1px solid {AppStyle.BORDER_COLOR};
                border-radius: 4px;
                text-align: center;
                background: {AppStyle.BG_INPUT};
            }}
            QProgressBar::chunk {{
                background-color: {AppStyle.PROGRESS_CHUNK};
                border-radius: 3px;
            }}
            QMenuBar {{
                background-color: {AppStyle.BG_SIDEBAR};
                color: {AppStyle.FG_COLOR};
            }}
            QMenuBar::item:selected {{
                background-color: {AppStyle.BG_BUTTON_HOVER};
            }}
            QMenu {{
                background-color: {AppStyle.BG_SIDEBAR};
                color: {AppStyle.FG_COLOR};
            }}
            QMenu::item:selected {{
                background-color: {AppStyle.BG_BUTTON_HOVER};
            }}
        """
