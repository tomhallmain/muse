from enum import Enum

from tkinter import Toplevel, Label, StringVar, LEFT, W
from tkinter.ttk import Button, Entry

from extensions.open_weather import OpenWeatherAPI
from lib.tk_scroll_demo import ScrollFrame
from ui.app_style import AppStyle
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class ExtensionStrategy(Enum):
    EXTEND_BY_COMPOSER = "extend by composer"
    EXTEND_BY_ARTIST = "extend by artist"
    EXTEND_BY_GENRE = "extend by genre"
    EXTEND_BY_PROMPT = "extend by prompt"
    EXTEND_BY_SPECIFIC_TAGS = "extend by specific tags"
    EXTEND_BY_LINK_TYPE_A = "extend by link type a" # i.e. provide a link to a forum post with scrapable media content




class ExtensionsWindow:
    '''
    Window to hold track, album, artist data.
    '''
    CURRENT_EXTENSION_TEXT = _("Extensions")
    COL_0_WIDTH = 150
    top_level = None

    def __init__(self, master, app_actions, dimensions="600x600"):

        # TODO next and previous buttons to navgiate through albums and other sequences
        # TODO update button to change specific track details
        # TODO update album to change track details for all tracks in shared album

        ExtensionsWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR)
        ExtensionsWindow.top_level.geometry(dimensions)
        ExtensionsWindow.set_title(_("Extensions"))
        self.master = ExtensionsWindow.top_level
        self.app_actions = app_actions
        self.open_weather_api = OpenWeatherAPI()

        self.has_closed = False
        self.frame = ScrollFrame(self.master, bg_color=AppStyle.BG_COLOR)
        self.frame.pack(side="top", fill="both", expand=True)

        self.update_btn = None
        self.add_btn("update_btn", _("Update"), self.update, row=0)

        self.title = StringVar(self.frame.viewPort)
        self.title_entry = Entry(self.frame.viewPort, textvariable=self.title)
        self.title_entry.grid(row=1)

        self.album = StringVar(self.frame.viewPort)
        self.album_entry = Entry(self.frame.viewPort, textvariable=self.album)
        self.album_entry.grid(row=2)

        self.artist = StringVar(self.frame.viewPort)
        self.artist_entry = Entry(self.frame.viewPort, textvariable=self.artist)
        self.artist_entry.grid(row=3)

        self.composer = StringVar(self.frame.viewPort)
        self.composer_entry = Entry(self.frame.viewPort, textvariable=self.composer)
        self.composer_entry.grid(row=4)

        # self._weather_label = Label(self.frame.viewPort)
        # self.add_label(self._weather_label, "Gathering weather data...", row=2)

        # self.master.bind("<Key>", self.filter_targets)
        # self.master.bind("<Return>", self.do_action)
        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.frame.after(1, lambda: self.frame.focus_force())
        # Utils.start_thread(self.get_track_data, use_asyncio=False)

    def update(self):
        pass

    @staticmethod
    def set_title(extra_text):
        ExtensionsWindow.top_level.title(_("Extensions") + " - " + extra_text)

    def close_windows(self, event=None):
        self.master.destroy()
        self.has_closed = True

    def add_label(self, label_ref, text, row=0, column=0, wraplength=500):
        label_ref['text'] = text
        label_ref.grid(column=column, row=row, sticky=W)
        label_ref.config(wraplength=wraplength, justify=LEFT, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)

    def add_btn(self, button_ref_name, text, command, row=0, column=0):
        if getattr(self, button_ref_name) is None:
            button = Button(master=self.frame.viewPort, text=text, command=command)
            setattr(self, button_ref_name, button)
            button # for some reason this is necessary to maintain the reference?
            button.grid(row=row, column=column)
