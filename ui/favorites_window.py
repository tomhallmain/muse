from tkinter import Toplevel, Frame, Label, Checkbutton, BooleanVar, StringVar, LEFT, W
import tkinter.font as fnt
from tkinter.ttk import Button, Entry

from lib.tk_scroll_demo import ScrollFrame
from library_data.library_data import LibraryData
from ui.app_style import AppStyle
# from ui.base_window import BaseWindow
from utils.app_info_cache import app_info_cache
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._



class FavoritesWindow:
    '''
    Window to search favorites data.
    '''
    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200
    details_window = None
    recent_favorites = []

    @staticmethod
    def load_recent_favorites():
        json_favorites = app_info_cache.get("recent_favorites", [])
        assert isinstance(json_favorites, list)
        for path in json_favorites:
            FavoritesWindow.recent_favorites.append(path)

    @staticmethod
    def store_recent_favorites():
        json_favorites = []
        for search in FavoritesWindow.recent_favorites:
            if search.is_valid() and search.stored_results_count > 0:
                json_favorites.append(search.get_dict())
        app_info_cache.set("recent_favorites", json_favorites)

    @staticmethod
    def set_favorite(track, is_favorited=False):
        track_filepath = track.filepath
        if is_favorited:
            FavoritesWindow.recent_favorites.insert(0, track_filepath)
        else:
            for search in FavoritesWindow.recent_favorites[:]:
                FavoritesWindow.recent_favorites.remove(search)
        FavoritesWindow.store_recent_favorites()


    def __init__(self, master, app_actions, dimensions="600x600"):

        FavoritesWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        FavoritesWindow.top_level.geometry(dimensions)
        FavoritesWindow.set_title(_("Search Favorites"))
        self.master = FavoritesWindow.top_level
        self.master.resizable(True, True)
        self.app_actions = app_actions
        self.favorites_data = LibraryData()
        self.favorite_data_search = None
        self.has_closed = False

        self.outer_frame = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.outer_frame.rowconfigure(0, weight=1)
        self.outer_frame.rowconfigure(0, weight=8)
        self.outer_frame.grid(row=0, column=0)

        self.inner_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR)
        self.inner_frame.columnconfigure(0, weight=1)
        self.inner_frame.columnconfigure(1, weight=1)
        self.inner_frame.grid(row=0, column=0, sticky="nsew")

        self.results_frame = ScrollFrame(self.outer_frame, bg_color=AppStyle.BG_COLOR, width=600)
        self.results_frame.grid(row=1, column=0, sticky="nsew")

        self._favorite_label = Label(self.inner_frame)
        self.add_label(self._favorite_label, _("Search Favorites"), row=0)
        self.favorite = StringVar(self.inner_frame)
        self.favorite_entry = Entry(self.inner_frame, textvariable=self.favorite)
        self.favorite_entry.grid(row=0, column=1)
        self.favorite_entry.bind("<Return>", self.do_search)

        self._genre_label = Label(self.inner_frame)
        self.add_label(self._genre_label, _("Search Genre"), row=1)
        self.genre = StringVar(self.inner_frame)
        self.genre_entry = Entry(self.inner_frame, textvariable=self.genre)
        self.genre_entry.grid(row=1, column=1)
        self.genre_entry.bind("<Return>", self.do_search)

        self.favorite_list = []
        self.open_details_btn_list = []
        self.search_btn_list = []

        self.search_btn = None
        self.add_btn("search_btn", _("Search"), self.do_search, row=2)

        # self.master.bind("<Key>", self.filter_targets)
        # self.master.bind("<Return>", self.do_action)
        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        Utils.start_thread(self.show_recent_favorites, use_asyncio=False)


    def show_recent_favorites(self):
        if len(FavoritesWindow.recent_favorites) == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No favorites found."), row=1, column=1)
            self.favorite_list.append(self.searching_label)
            self.master.update()
            return
        for i in range(len(FavoritesWindow.recent_favorites)):
            row = i + 1
            search = FavoritesWindow.recent_favorites[i]
            if search is None:
                continue

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, search.favorite, row=row, column=1, wraplength=200)
            self.favorite_list.append(title_label)

            album_label = Label(self.results_frame.viewPort)
            self.add_label(album_label, search.genre, row=row, column=2, wraplength=200)
            self.open_details_btn_list.append(album_label)

            results_count_label = Label(self.results_frame.viewPort)
            self.add_label(results_count_label, search.get_readable_stored_results_count(), row=row, column=3, wraplength=200)
            self.favorite_list.append(results_count_label)

            search_btn = Button(self.results_frame.viewPort, text=_("Search"))
            self.search_btn_list.append(search_btn)
            search_btn.grid(row=row, column=4)
            def search_handler(event, self=self, search=search):
                self.load_stored_search(favorite_data_search=search)
                self._do_search(event)
            search_btn.bind("<Button-1>", search_handler)

            # play_btn = Button(self.results_frame.viewPort, text=_("Play"))
            # self.play_btn_list.append(play_btn)
            # play_btn.grid(row=row, column=6)
            # def play_handler(event, self=self, search=search, track=track):
            #     self.load_stored_search(library_data_search=search)
            #     self._do_search(event)
            #     if track is None:
            #         Utils.log("No specific track defined on search, using first available track.")
            #         track = search.get_first_available_track()
            #         if track is None:
            #             raise Exception("No tracks available on search.")
            #     elif track.is_invalid():
            #         raise Exception(f"Invalid track: {track}")
            #     self.run_play_callback(track)
            # play_btn.bind("<Button-1>", play_handler)
        self.master.update()

    def load_stored_search(self, favorite_data_search):
        assert favorite_data_search is not None
        self.favorite.set(favorite_data_search.favorite)
        self.genre.set(favorite_data_search.genre)
        self.favorite_data_search = favorite_data_search

    def do_search(self, event=None):
        favorite = self.favorite.get().strip()
        genre = self.genre.get().strip()
        self.favorite_data_search = favoritesDataSearch(favorite, genre, FavoritesWindow.MAX_RESULTS)
        self._do_search()

    def _do_search(self, event=None):
        assert self.favorite_data_search is not None
        self._refresh_widgets(add_results=False)
        self.favorites_data.do_search(self.favorite_data_search)
        if self.favorite_data_search in FavoritesWindow.recent_favorites:
            FavoritesWindow.recent_favorites.remove(self.favorite_data_search)
        FavoritesWindow.recent_favorites.insert(0, self.favorite_data_search)
        self._refresh_widgets()

    def add_widgets_for_results(self):
        assert self.favorite_data_search is not None
        results = self.favorite_data_search.get_results()
        Utils.log(f"Found {len(results)} results")
        for i in range(len(results)):
            row = i + 1
            favorite = results[i]

            favorite_label = Label(self.results_frame.viewPort)
            self.add_label(favorite_label, favorite.name, row=row, column=0)
            self.favorite_list.append(favorite_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=1)
            def open_detail_handler(event, self=self, favorite=favorite):
                self.open_details(favorite)
            open_details_btn.bind("<Button-1>", open_detail_handler)

            open_details_btn = None
            self.add_btn("search_btn", _("Search"), self.do_search, row=0)

    def open_details(self, favorite):
        if FavoritesWindow.details_window is not None:
            FavoritesWindow.details_window.master.destroy()
        FavoritesWindow.details_window = FavoriteWindow(FavoritesWindow.top_level, self.refresh, favorite)

    def refresh(self):
        pass

    def _refresh_widgets(self, add_results=True):
        self.clear_widget_lists()
        if add_results:
            self.add_widgets_for_results()
        self.master.update()

    def clear_widget_lists(self):
        for label in self.favorite_list:
            label.destroy()
        for btn in self.open_details_btn_list:
            btn.destroy()
        for btn in self.search_btn_list:
            btn.destroy()
        self.favorite_list = []
        self.open_details_btn_list = []
        self.search_btn_list = []

    @staticmethod
    def set_title(extra_text):
        FavoritesWindow.top_level.title(_("favorite Search") + " - " + extra_text)

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

