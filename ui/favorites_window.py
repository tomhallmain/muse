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


class FavoritesDataSearch:
    def __init__(self, favorite="", genre="", max_results=200):
        self.favorite = favorite
        self.genre = genre
        self.max_results = max_results
        self.results = []

    def is_valid(self):
        return len(self.favorite.strip()) > 0 or len(self.genre.strip()) > 0

    def get_readable_results_count(self):
        count = len(self.results)
        if count > self.max_results:
            results_str = f"{self.max_results}+"
        else:
            results_str = str(count)
        return _("({0} results)").format(results_str)

    def get_results(self):
        return self.results


class FavoritesWindow:
    '''
    Window to search favorites data.
    '''
    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200
    details_window = None
    recent_favorites = []  # List of favorited tracks, most recent first

    @staticmethod
    def load_favorites():
        json_favorites = app_info_cache.get("favorites", [])
        assert isinstance(json_favorites, list)
        FavoritesWindow.favorites = []
        for fav_dict in json_favorites:
            track = MediaTrack(fav_dict["filepath"])
            FavoritesWindow.favorites.append(track)

    @staticmethod
    def store_favorites():
        json_favorites = []
        for track in FavoritesWindow.favorites:
            json_favorites.append({"filepath": track.filepath})
        app_info_cache.set("favorites", json_favorites)

    @staticmethod
    def set_favorite(track, is_favorited=False):
        if is_favorited:
            # Remove if already exists to update recency
            for existing_track in FavoritesWindow.favorites[:]:
                if existing_track.filepath == track.filepath:
                    FavoritesWindow.favorites.remove(existing_track)
                    break
            FavoritesWindow.favorites.insert(0, track)  # Add to front (most recent)
        else:
            for existing_track in FavoritesWindow.favorites[:]:
                if existing_track.filepath == track.filepath:
                    FavoritesWindow.favorites.remove(existing_track)
                    break
        FavoritesWindow.store_favorites()

    def __init__(self, master, app_actions, dimensions="600x600"):
        FavoritesWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        FavoritesWindow.top_level.geometry(dimensions)
        FavoritesWindow.set_title(_("Favorites"))
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

        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        Utils.start_thread(self.show_recent_favorites, use_asyncio=False)


    def show_recent_favorites(self):
        if len(FavoritesWindow.favorites) == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No favorites found."), row=1, column=1)
            self.favorite_list.append(self.searching_label)
            self.master.update()
            return
        for i in range(len(FavoritesWindow.favorites)):
            row = i + 1
            track = FavoritesWindow.favorites[i]
            if track is None:
                continue

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, track.title or track.filepath, row=row, column=1, wraplength=200)
            self.favorite_list.append(title_label)

            genre_label = Label(self.results_frame.viewPort)
            self.add_label(genre_label, track.genre or "", row=row, column=2, wraplength=200)
            self.open_details_btn_list.append(genre_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=3)
            def open_detail_handler(event, self=self, track=track):
                self.open_details(track)
            open_details_btn.bind("<Button-1>", open_detail_handler)

        self.master.update()

    def do_search(self, event=None):
        favorite = self.favorite.get().strip()
        genre = self.genre.get().strip()
        self.favorite_data_search = FavoritesDataSearch(favorite, genre, FavoritesWindow.MAX_RESULTS)
        self._do_search()

    def _do_search(self, event=None):
        assert self.favorite_data_search is not None
        self._refresh_widgets(add_results=False)
        
        # Filter favorites based on search criteria
        results = []
        for track in FavoritesWindow.favorites:
            if (not self.favorite_data_search.favorite or 
                self.favorite_data_search.favorite.lower() in (track.title or "").lower()) and \
               (not self.favorite_data_search.genre or 
                self.favorite_data_search.genre.lower() in (track.genre or "").lower()):
                results.append(track)
        
        self.favorite_data_search.results = results

        self._refresh_widgets()

    def add_widgets_for_results(self):
        assert self.favorite_data_search is not None
        results = self.favorite_data_search.get_results()
        Utils.log(f"Found {len(results)} results")
        for i in range(len(results)):
            row = i + 1
            track = results[i]

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, track.title or track.filepath, row=row, column=0)
            self.favorite_list.append(title_label)

            genre_label = Label(self.results_frame.viewPort)
            self.add_label(genre_label, track.genre or "", row=row, column=1)
            self.open_details_btn_list.append(genre_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=2)
            def open_detail_handler(event, self=self, track=track):
                self.open_details(track)
            open_details_btn.bind("<Button-1>", open_detail_handler)

    def open_details(self, track):
        if FavoritesWindow.details_window is not None:
            FavoritesWindow.details_window.master.destroy()
        FavoritesWindow.details_window = FavoriteWindow(FavoritesWindow.top_level, self.refresh, track)

    def refresh(self):
        pass

    def _refresh_widgets(self, add_results=True):
        self.clear_widget_lists()
        if add_results:
            if self.favorite_data_search is not None and (self.favorite_data_search.favorite or self.favorite_data_search.genre):
                self.add_widgets_for_results()
            else:
                self.show_favorites()
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
        FavoritesWindow.top_level.title(_("Favorites") + " - " + extra_text)

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

