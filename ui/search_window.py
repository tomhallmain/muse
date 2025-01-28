from enum import Enum

from tkinter import Toplevel, Frame, Label, StringVar, BooleanVar, Checkbutton, LEFT, W
from tkinter.ttk import Button, Entry

from lib.tk_scroll_demo import ScrollFrame
from library_data.library_data import LibraryData, LibraryDataSearch
from ui.app_style import AppStyle
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._



class SearchWindow:
    '''
    Window to search media library.
    '''
    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200

    def __init__(self, master, app_actions, dimensions="900x1200"):

        SearchWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        SearchWindow.top_level.geometry(dimensions)
        SearchWindow.set_title(_("Search Library"))
        self.master = SearchWindow.top_level
        self.master.resizable(True, True)
        self.app_actions = app_actions
        self.library_data = LibraryData()
        self.library_data_search = None
        self.has_closed = False

        self.outer_frame = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.outer_frame.columnconfigure(0, weight=1)
        self.outer_frame.columnconfigure(0, weight=1)
        self.outer_frame.grid(row=0, column=0)

        self.inner_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR)
        self.inner_frame.columnconfigure(0, weight=1)
        self.inner_frame.columnconfigure(1, weight=1)
        self.inner_frame.grid(row=0, column=0, sticky="nsew")

        self.results_frame = ScrollFrame(self.outer_frame, bg_color=AppStyle.BG_COLOR)
        self.results_frame.grid(row=0, column=1)

        self.title_list = []
        self.album_list = []
        self.artist_list = []
        self.composer_list = []
        self.open_details_btn_list = []

        self.search_btn = None
        self.add_btn("search_btn", _("Search"), self.do_search, row=0)

        self._all_label = Label(self.inner_frame)
        self.add_label(self._all_label, "Search all fields", row=1)
        self.all = StringVar(self.inner_frame)
        self.all_entry = Entry(self.inner_frame, textvariable=self.all)
        self.all_entry.grid(row=1, column=1)
        self.all_entry.bind("<Return>", self.do_search)

        self._title_label = Label(self.inner_frame)
        self.add_label(self._title_label, "Search Title", row=2)
        self.title = StringVar(self.inner_frame)
        self.title_entry = Entry(self.inner_frame, textvariable=self.title)
        self.title_entry.grid(row=2, column=1)
        self.title_entry.bind("<Return>", self.do_search)

        self._album_label = Label(self.inner_frame)
        self.add_label(self._album_label, "Search Album", row=3)
        self.album = StringVar(self.inner_frame)
        self.album_entry = Entry(self.inner_frame, textvariable=self.album)
        self.album_entry.grid(row=3, column=1)
        self.album_entry.bind("<Return>", self.do_search)

        self._artist_label = Label(self.inner_frame)
        self.add_label(self._artist_label, "Search Artist", row=4)
        self.artist = StringVar(self.inner_frame)
        self.artist_entry = Entry(self.inner_frame, textvariable=self.artist)
        self.artist_entry.grid(row=4, column=1)
        self.artist_entry.bind("<Return>", self.do_search)

        self._composer_label = Label(self.inner_frame)
        self.add_label(self._composer_label, "Search Composer", row=5)
        self.composer = StringVar(self.inner_frame)
        self.composer_entry = Entry(self.inner_frame, textvariable=self.composer)
        self.composer_entry.grid(row=5, column=1)
        self.composer_entry.bind("<Return>", self.do_search)

        self._genre_label = Label(self.inner_frame)
        self.add_label(self._genre_label, "Search Genre", row=6)
        self.genre = StringVar(self.inner_frame)
        self.genre_entry = Entry(self.inner_frame, textvariable=self.genre)
        self.genre_entry.grid(row=6, column=1)
        self.genre_entry.bind("<Return>", self.do_search)

        self._instrument_label = Label(self.inner_frame)
        self.add_label(self._instrument_label, "Search Instrument", row=6)
        self.instrument = StringVar(self.inner_frame)
        self.instrument_entry = Entry(self.inner_frame, textvariable=self.instrument)
        self.instrument_entry.grid(row=6, column=1)
        self.instrument_entry.bind("<Return>", self.do_search)

        self.overwrite_cache = BooleanVar(self.inner_frame)
        self._overwrite = Checkbutton(self.inner_frame, text="Overwrite Cache", variable=self.overwrite_cache)
        self._overwrite.grid(row=7, columnspan=2)

        # self.master.bind("<Key>", self.filter_targets)
        # self.master.bind("<Return>", self.do_action)
        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        Utils.start_thread(self.do_search, use_asyncio=False)

    def do_search(self, event=None):
        all = self.all.get().strip()
        title = self.title.get().strip()
        album = self.album.get().strip()
        artist = self.artist.get().strip()
        composer = self.composer.get().strip()
        genre = self.genre.get().strip()
        instrument = self.instrument.get().strip()
        overwrite = self.overwrite_cache.get()
        self.library_data_search = LibraryDataSearch(all, title, artist, composer, album, genre, instrument, SearchWindow.MAX_RESULTS)
        self.library_data.do_search(self.library_data_search, overwrite=overwrite)
        self._refresh_widgets()

    def add_widgets_for_results(self):
        results = self.library_data_search.get_results()
        for i in range(len(results)):
            row = i + 1
            track = results[i]

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, track.title, row=row, column=1)
            self.title_list.append(title_label)

            artist_label = Label(self.results_frame.viewPort)
            self.add_label(artist_label, track.artist, row=row, column=2)
            self.artist_list.append(artist_label)

            album_label = Label(self.results_frame.viewPort)
            self.add_label(album_label, track.album, row=row, column=3)
            self.album_list.append(album_label)
            
            composer_label = Label(self.results_frame.viewPort)
            self.add_label(composer_label, track.composer, row=row, column=4)
            self.composer_list.append(composer_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=5)
            def open_details_handler(event, self=self, audio_track=track):
                self.open_details(audio_track)
            open_details_btn.bind("<Button-1>", open_details_handler)

            open_details_btn = None
            self.add_btn("search_btn", _("Search"), self.do_search, row=0)

    def open_details(self, track):
        pass

    def _refresh_widgets(self):
        self.clear_widget_lists()
        self.add_widgets_for_results()
        self.master.update()

    def clear_widget_lists(self):
        for label in self.title_list:
            label.destroy()
        for label in self.artist_list:
            label.destroy()
        for label in self.album_list:
            label.destroy()
        for label in self.composer_list:
            label.destroy()
        for btn in self.open_details_btn_list:
            btn.destroy()
        self.title_list = []
        self.artist_list = []
        self.album_list = []
        self.composer_list = []
        self.open_details_btn_list = []

    @staticmethod
    def set_title(extra_text):
        SearchWindow.top_level.title(_("Search") + " - " + extra_text)

    def close_windows(self, event=None):
        self.master.destroy()
        self.has_closed = True

    def add_label(self, label_ref, text, row=0, column=0, wraplength=500):
        label_ref['text'] = text
        label_ref.grid(column=column, row=row, sticky=W)
        label_ref.config(wraplength=wraplength, justify=LEFT, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)

    def add_btn(self, button_ref_name, text, command, row=0, column=0):
        if getattr(self, button_ref_name) is None:
            button = Button(master=self.inner_frame, text=text, command=command)
            setattr(self, button_ref_name, button)
            button # for some reason this is necessary to maintain the reference?
            button.grid(row=row, column=column)

