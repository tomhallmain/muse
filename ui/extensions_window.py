from enum import Enum

from tkinter import Toplevel, Label, StringVar, LEFT, W
from tkinter.ttk import Button, Entry

from extensions.extension_manager import ExtensionManager
from extensions.open_weather import OpenWeatherAPI
from lib.tk_scroll_demo import ScrollFrame
from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from utils.config import config
from utils.globals import ExtensionStrategy
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._





class ExtensionsWindow(BaseWindow):
    '''
    Window to hold track, album, artist data.
    '''
    CURRENT_EXTENSION_TEXT = _("Extensions")
    COL_0_WIDTH = 150
    top_level = None

    def __init__(self, master, runner_app_config):
        super().init()
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.runner_app_config = runner_app_config

        self.main = Frame(self.master)
        self.main.columnconfigure(0, weight=1)
        self.main.columnconfigure(1, weight=1)
        self.main.grid(column=0, row=0)

        # Sidebar
        self.sidebar = Sidebar(self.main)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.columnconfigure(1, weight=1)
        self.row_counter0 = 0
        self.row_counter1 = 0
        self.sidebar.grid(column=0, row=self.row_counter0)

        self.label_title = Label(self.sidebar)
        self.add_label(self.label_title, _("Playlist Config"), sticky=None, columnspan=2)

        self.label_saved_playlist = Label(self.sidebar)
        self.add_label(self.label_saved_playlist, _("Saved Playlists"), increment_row_counter=False)
        self.named_playlist_config = StringVar()
        self.named_playlist_choice = OptionMenu(self.sidebar, self.named_playlist_config, *list(PlaylistWindow.named_playlist_configs.keys()), command=self.set_playlist_config)
        self.apply_to_grid(self.named_playlist_choice, interior_column=1, sticky=W)

        self.label_workflows = Label(self.sidebar)
        self.add_label(self.label_workflows, _("Playlist Sort"), increment_row_counter=False)
        self.workflow = StringVar(master)
        self.workflows_choice = OptionMenu(self.sidebar, self.workflow, self.runner_app_config.workflow_type,
                                           *PlaylistSortType.__members__.keys(), command=self.set_workflow_type)
        self.apply_to_grid(self.workflows_choice, interior_column=2, sticky=W)

        self.label_directory = Label(self.sidebar)
        self.add_label(self.label_directory, _("Directory"), increment_row_counter=False)
        self.directory = StringVar(master)
        directory_options = ["ALL"]
        directory_options.extend(list(config.get_subdirectories().values()))
        self.directory_choice = OptionMenu(self.sidebar, self.directory, str(self.runner_app_config.directory),
                                           *directory_options, command=self.set_directory)
        self.apply_to_grid(self.directory_choice, interior_column=1, sticky=W)

        self.master.update()

    def on_closing(self):
        self.master.destroy()
        self.has_closed = True

    def update(self):
        pass

    @staticmethod
    def set_title(extra_text):
        ExtensionsWindow.top_level.title(_("Extensions") + " - " + extra_text)

