class AppStyle:
    IS_DEFAULT_THEME = False
    LIGHT_THEME = "light"
    DARK_THEME = "dark"
    BG_COLOR = ""
    FG_COLOR = ""

    @staticmethod
    def get_theme_name():
        return AppStyle.DARK_THEME if AppStyle.IS_DEFAULT_THEME else AppStyle.LIGHT_THEME
        
    @staticmethod
    def configure_ttk_styles(style):
        """Configure all ttk styles for the application.
        
        Args:
            style: The ttk Style object to configure
        """
        # Configure basic styles
        style.configure("TLabel", background=AppStyle.BG_COLOR, foreground=AppStyle.FG_COLOR)
        style.configure("TFrame", background=AppStyle.BG_COLOR)
        style.configure("TLabelframe", background=AppStyle.BG_COLOR, foreground=AppStyle.FG_COLOR)
        style.configure("TLabelframe.Label", background=AppStyle.BG_COLOR, foreground=AppStyle.FG_COLOR)
        style.configure("TButton", background=AppStyle.BG_COLOR, foreground=AppStyle.FG_COLOR)
        style.configure("TCheckbutton", background=AppStyle.BG_COLOR, foreground=AppStyle.FG_COLOR)
        
        # Configure combo box styles
        style.configure("TCombobox", 
                       fieldbackground=AppStyle.BG_COLOR,
                       background=AppStyle.BG_COLOR,
                       foreground=AppStyle.FG_COLOR,
                       arrowcolor=AppStyle.FG_COLOR)
        style.map("TCombobox",
                 fieldbackground=[("readonly", AppStyle.BG_COLOR)],
                 selectbackground=[("readonly", AppStyle.BG_COLOR)],
                 selectforeground=[("readonly", AppStyle.FG_COLOR)])