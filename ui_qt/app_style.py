"""
Qt (PySide6) application style for Muse.
Dark blue theme. Used by app_qt and ui_qt widgets.
Includes title bar styling for frameless windows.
"""


class AppStyle:
    """Application theme and colors for the Qt UI. Dark blue by default."""
    IS_DEFAULT_THEME = True   # True = dark blue theme
    LIGHT_THEME = "light"
    DARK_THEME = "dark"

    # Dark blue palette (dark theme)
    BG_COLOR = "#0a1628"
    FG_COLOR = "#e8ecf0"
    BG_SIDEBAR = "#0d1b2a"
    BG_BUTTON = "#1b2838"
    BG_BUTTON_HOVER = "#243447"
    BG_INPUT = "#162536"
    BORDER_COLOR = "#1b2838"
    PROGRESS_CHUNK = "#2d4a6f"
    MEDIA_BG = "#0d1b2a"
    
    # Light theme palette
    LIGHT_BG_COLOR = "#f0f4f8"
    LIGHT_FG_COLOR = "#1a1a2e"
    LIGHT_BG_SIDEBAR = "#e8ecf0"
    LIGHT_BG_BUTTON = "#d8dce0"
    LIGHT_BG_BUTTON_HOVER = "#c8ccd0"
    LIGHT_BG_INPUT = "#ffffff"
    LIGHT_BORDER_COLOR = "#c0c4c8"
    LIGHT_PROGRESS_CHUNK = "#4a90d9"
    LIGHT_MEDIA_BG = "#e8ecf0"
    
    # Title bar specific colors
    CLOSE_HOVER = "#e81123"
    CLOSE_PRESSED = "#f1707a"
    
    # Configuration
    _corner_radius = 10
    _is_dark = True

    @staticmethod
    def get_theme_name():
        return AppStyle.DARK_THEME if AppStyle.IS_DEFAULT_THEME else AppStyle.LIGHT_THEME
    
    @classmethod
    def set_corner_radius(cls, radius: int):
        """Set the corner radius for rounded window corners."""
        cls._corner_radius = radius
    
    @classmethod
    def get_corner_radius(cls) -> int:
        """Get the current corner radius."""
        return cls._corner_radius
    
    @classmethod
    def is_dark_theme(cls) -> bool:
        """Check if dark theme is active."""
        return cls.IS_DEFAULT_THEME
    
    @classmethod
    def get_colors(cls, is_dark: bool = None) -> dict:
        """Get color dictionary for the specified theme."""
        if is_dark is None:
            is_dark = cls.IS_DEFAULT_THEME
        
        if is_dark:
            return {
                'bg': cls.BG_COLOR,
                'fg': cls.FG_COLOR,
                'sidebar': cls.BG_SIDEBAR,
                'button': cls.BG_BUTTON,
                'hover': cls.BG_BUTTON_HOVER,
                'input': cls.BG_INPUT,
                'border': cls.BORDER_COLOR,
                'progress': cls.PROGRESS_CHUNK,
                'media': cls.MEDIA_BG,
            }
        else:
            return {
                'bg': cls.LIGHT_BG_COLOR,
                'fg': cls.LIGHT_FG_COLOR,
                'sidebar': cls.LIGHT_BG_SIDEBAR,
                'button': cls.LIGHT_BG_BUTTON,
                'hover': cls.LIGHT_BG_BUTTON_HOVER,
                'input': cls.LIGHT_BG_INPUT,
                'border': cls.LIGHT_BORDER_COLOR,
                'progress': cls.LIGHT_PROGRESS_CHUNK,
                'media': cls.LIGHT_MEDIA_BG,
            }

    @staticmethod
    def get_stylesheet():
        """Return a Qt stylesheet string for the application (dark blue theme).
        Applied once on the top-level window; all child widgets inherit.
        QComboBox is styled only at top level (no ::drop-down or ::down-arrow) so the
        platform draws the arrow; see BookmarkManager app_style for same approach."""
        return f"""
            QMainWindow, QDialog, QWidget, QFrame {{
                background-color: {AppStyle.BG_COLOR};
                color: {AppStyle.FG_COLOR};
            }}
            QLabel {{
                color: {AppStyle.FG_COLOR};
                padding: 2px 0;
            }}
            QLineEdit {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.FG_COLOR};
                border: 1px solid {AppStyle.BORDER_COLOR};
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QPlainTextEdit, QTextEdit {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.FG_COLOR};
                border: 1px solid {AppStyle.BORDER_COLOR};
                padding: 6px 8px;
                border-radius: 4px;
                selection-background-color: {AppStyle.BG_BUTTON_HOVER};
            }}
            QTableWidget {{
                background-color: {AppStyle.BG_COLOR};
                color: {AppStyle.FG_COLOR};
                gridline-color: {AppStyle.BORDER_COLOR};
            }}
            QTableWidget::item {{
                color: {AppStyle.FG_COLOR};
            }}
            QHeaderView::section {{
                background-color: {AppStyle.BG_BUTTON};
                color: {AppStyle.FG_COLOR};
                padding: 6px;
                border: 1px solid {AppStyle.BORDER_COLOR};
            }}
            QScrollArea {{
                background-color: {AppStyle.BG_COLOR};
                border: none;
            }}
            QPushButton {{
                background-color: {AppStyle.BG_BUTTON};
                color: {AppStyle.FG_COLOR};
                border: 1px solid {AppStyle.BORDER_COLOR};
                padding: 3px 10px;
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
                padding: 3px 8px;
                border-radius: 4px;
                min-height: 1.2em;
            }}
            QComboBox:hover {{
                border-color: {AppStyle.PROGRESS_CHUNK};
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
    
    @classmethod
    def get_frameless_stylesheet(cls, is_dark: bool = None) -> str:
        """Get additional stylesheet for frameless windows with rounded corners."""
        if is_dark is None:
            is_dark = cls.IS_DEFAULT_THEME
        
        colors = cls.get_colors(is_dark)
        radius = cls._corner_radius
        
        return f"""
            /* Base styling for frameless window */
            QMainWindow {{
                background-color: transparent;
            }}
            
            /* Transparent outer container for rounded corners */
            QWidget#transparentOuter {{
                background-color: transparent;
            }}
            
            /* Main frame with rounded corners - the visible window background */
            QFrame#mainFrame {{
                background-color: {colors['bg']};
                border: 1px solid {colors['border']};
                border-radius: {radius}px;
            }}
            
            /* Content area styling */
            QWidget#contentArea {{
                background-color: {colors['bg']};
                border-bottom-left-radius: {radius}px;
                border-bottom-right-radius: {radius}px;
            }}
            
            /* Title bar menu dropdown styling */
            QMenu {{
                background-color: {colors['sidebar']};
                color: {colors['fg']};
                border: 1px solid {colors['border']};
                padding: 4px 0;
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {colors['hover']};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {colors['border']};
                margin: 4px 8px;
            }}
        """
    
    @classmethod
    def get_title_bar_style(cls, is_dark: bool = None) -> str:
        """Get the stylesheet for the custom title bar."""
        if is_dark is None:
            is_dark = cls.IS_DEFAULT_THEME
        
        colors = cls.get_colors(is_dark)
        radius = cls._corner_radius
        
        return f"""
            CustomTitleBar {{
                background-color: {colors['bg']};
                border-bottom: 1px solid {colors['border']};
                border-top-left-radius: {radius}px;
                border-top-right-radius: {radius}px;
            }}
        """
    
    @classmethod
    def get_title_bar_button_style(cls, button_type: str, is_dark: bool = None) -> str:
        """
        Get the stylesheet for a title bar button.
        
        Args:
            button_type: One of 'minimize', 'maximize', 'close'
            is_dark: Whether dark theme is active
        """
        if is_dark is None:
            is_dark = cls.IS_DEFAULT_THEME
            
        colors = cls.get_colors(is_dark)
        
        # Common button properties
        base_style = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {colors['fg']};
                padding: 0px;
                margin: 0px;
            }}
        """
        
        if button_type == "close":
            return base_style + f"""
                QPushButton {{
                    font-size: 12px;
                    font-family: "Segoe MDL2 Assets", "Segoe UI Symbol", sans-serif;
                }}
                QPushButton:hover {{
                    background-color: {cls.CLOSE_HOVER};
                    color: white;
                }}
                QPushButton:pressed {{
                    background-color: {cls.CLOSE_PRESSED};
                    color: white;
                }}
            """
        else:
            return base_style + f"""
                QPushButton {{
                    font-size: 11px;
                    font-family: "Segoe MDL2 Assets", "Segoe UI Symbol", sans-serif;
                }}
                QPushButton:hover {{
                    background-color: {colors['hover']};
                }}
                QPushButton:pressed {{
                    background-color: {colors['hover']};
                }}
            """
    
    @classmethod
    def apply_to_title_bar(cls, title_bar, is_dark: bool = None):
        """
        Apply theme styling to a CustomTitleBar widget.
        
        Args:
            title_bar: CustomTitleBar instance
            is_dark: Whether dark theme is active
        """
        if is_dark is None:
            is_dark = cls.IS_DEFAULT_THEME
            
        colors = cls.get_colors(is_dark)
        
        # Apply title bar container style
        title_bar.setStyleSheet(cls.get_title_bar_style(is_dark))
        
        # Apply title label style
        title_bar.title_label.setStyleSheet(
            f"color: {colors['fg']}; font-size: 12px; background: transparent;"
        )
        
        # Apply button styles
        title_bar.minimize_btn.setStyleSheet(cls.get_title_bar_button_style('minimize', is_dark))
        title_bar.maximize_btn.setStyleSheet(cls.get_title_bar_button_style('maximize', is_dark))
        title_bar.close_btn.setStyleSheet(cls.get_title_bar_button_style('close', is_dark))
