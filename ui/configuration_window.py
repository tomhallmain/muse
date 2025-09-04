from tkinter import Toplevel, Frame, Label, Checkbutton, BooleanVar, StringVar, messagebox
from tkinter.ttk import Notebook, Button, Entry
from tkinter.constants import W, BOTH, YES

from ui.app_style import AppStyle
from ui.auth.password_utils import require_password
from ui.base_window import BaseWindow
from utils.config import config
from utils.globals import ProtectedActions
from utils.translations import I18N

_ = I18N._

class ConfigurationWindow(BaseWindow):
    top_level = None

    def __init__(self, master, app_actions):
        super().__init__()
        
        # Create and configure top level window
        ConfigurationWindow.top_level = Toplevel(master)
        ConfigurationWindow.top_level.title(_("Configuration Settings"))
        ConfigurationWindow.top_level.geometry("1000x800")
        ConfigurationWindow.top_level.protocol("WM_DELETE_WINDOW", self.confirm_close)
        
        self.master = ConfigurationWindow.top_level
        self.app_actions = app_actions
        
        # Create main frame
        self.main_frame = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.main_frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # Create notebook for tabbed interface
        self.notebook = Notebook(self.main_frame)
        self.notebook.pack(fill=BOTH, expand=YES)
        
        # Create tabs
        self.general_tab = Frame(self.notebook, bg=AppStyle.BG_COLOR)
        self.audio_tab = Frame(self.notebook, bg=AppStyle.BG_COLOR)
        self.api_tab = Frame(self.notebook, bg=AppStyle.BG_COLOR)
        self.tts_tab = Frame(self.notebook, bg=AppStyle.BG_COLOR)
        
        self.notebook.add(self.general_tab, text=_("General"))
        self.notebook.add(self.audio_tab, text=_("Audio"))
        self.notebook.add(self.api_tab, text=_("API Keys"))
        self.notebook.add(self.tts_tab, text=_("TTS Settings"))
        
        # Initialize variables
        self.config_vars = {}
        
        # Create UI elements
        self.create_general_tab()
        self.create_audio_tab()
        self.create_api_tab()
        self.create_tts_tab()
        
        # Add save button
        self.save_button = Button(self.main_frame, text=_("Save Configuration"), command=self.save_config)
        self.save_button.pack(pady=10)

    def create_general_tab(self):
        """Create general settings tab"""
        frame = Frame(self.general_tab, bg=AppStyle.BG_COLOR)
        frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # Add general settings
        self.add_config_entry(frame, "foreground_color", _("Foreground Color"), 0)
        self.add_config_entry(frame, "background_color", _("Background Color"), 1)
        self.add_config_entry(frame, "muse_language_learning_language", _("Language Learning Language"), 2)
        self.add_config_entry(frame, "muse_language_learning_language_level", _("Language Learning Level"), 3)
        self.add_config_checkbox(frame, "enable_dynamic_volume", _("Enable Dynamic Volume"), 4)
        self.add_config_checkbox(frame, "enable_library_extender", _("Enable Library Extender"), 5)
        self.add_config_checkbox(frame, "enable_long_track_splitting", _("Enable Long Track Splitting"), 6)
        self.add_config_entry(frame, "long_track_splitting_time_cutoff_minutes", _("Long Track Cutoff (minutes)"), 7)

    def create_audio_tab(self):
        """Create audio settings tab"""
        frame = Frame(self.audio_tab, bg=AppStyle.BG_COLOR)
        frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # Add audio settings
        self.add_config_checkbox(frame, "play_videos_in_separate_window", _("Play Videos in Separate Window"), 0)
        self.add_config_entry(frame, "playlist_recently_played_check_count", _("Recently Played Check Count"), 1)
        self.add_config_entry(frame, "max_search_results", _("Max Search Results"), 2)
        self.add_config_entry(frame, "max_recent_searches", _("Max Recent Searches"), 3)

    def create_api_tab(self):
        """Create API settings tab"""
        frame = Frame(self.api_tab, bg=AppStyle.BG_COLOR)
        frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # Add API settings
        self.add_config_entry(frame, "open_weather_api_key", _("OpenWeather API Key"), 0)
        self.add_config_entry(frame, "open_weather_city", _("OpenWeather City"), 1)
        self.add_config_entry(frame, "news_api_key", _("News API Key"), 2)

    def create_tts_tab(self):
        """Create TTS settings tab"""
        frame = Frame(self.tts_tab, bg=AppStyle.BG_COLOR)
        frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # Add TTS settings
        self.add_config_entry(frame, "coqui_tts_location", _("Coqui TTS Location"), 0)
        self.add_config_entry(frame, "llm_model_name", _("LLM Model Name"), 1)
        self.add_config_entry(frame, "max_chunk_tokens", _("Max Chunk Tokens"), 2)

    def add_config_entry(self, parent, key, label_text, row):
        """Add a configuration entry field"""
        label = Label(parent, text=label_text, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        label.grid(row=row, column=0, sticky=W, padx=5, pady=2)
        
        var = StringVar(value=str(config.get_config_value(key) or ""))
        self.config_vars[key] = var
        
        entry = Entry(parent, textvariable=var, width=40)
        entry.grid(row=row, column=1, sticky=W, padx=5, pady=2)

    def add_config_checkbox(self, parent, key, label_text, row):
        """Add a configuration checkbox"""
        var = BooleanVar(value=bool(config.get_config_value(key)))
        self.config_vars[key] = var
        
        checkbox = Checkbutton(parent, text=label_text, variable=var, 
                              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, 
                              selectcolor=AppStyle.BG_COLOR)
        checkbox.grid(row=row, column=0, columnspan=2, sticky=W, padx=5, pady=2)

    def confirm_close(self):
        """Handle window closing"""
        if config.has_changes():
            res = self.app_actions.alert(_("Close Configuration"), 
                _("Do you want to close the configuration window?\nAny unsaved changes will be lost."), 
                kind="askokcancel")
            if res == messagebox.OK or res == True:
                self.on_closing()
        else:
            self.on_closing()

    @require_password(ProtectedActions.EDIT_CONFIGURATION)
    def save_config(self):
        """Save configuration to file"""
        try:
            # Update config values
            for key, var in self.config_vars.items():
                if isinstance(var, BooleanVar):
                    config.set_config_value(key, var.get())
                else:
                    config.set_config_value(key, var.get())
            
            # Save to file
            if config.save_config():
                self.app_actions.toast(_("Configuration saved successfully"))
            else:
                self.app_actions.alert(_("Error"), _("Failed to save configuration"), kind="error")
            
        except Exception as e:
            self.app_actions.alert(_("Error"), str(e), kind="error")

    def on_closing(self):
        self.master.destroy()
        self.master = None
