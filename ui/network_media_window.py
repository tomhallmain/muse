from tkinter import Toplevel, Frame, Label, StringVar, BooleanVar, Checkbutton, LEFT, W
from tkinter.ttk import Button, Entry

from lib.tk_scroll_demo import ScrollFrame
from library_data.library_data import LibraryData, LibraryDataSearch
from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType
from utils.logging_setup import get_logger
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._
logger = get_logger(__name__)

class NetworkMediaURL():
    '''A URLwith media on it.'''
    def __init__(self, url="", title=None):
        self.url = url
        self.title = title

    def is_valid(self):
        return self.url is not None and self.url.strip() != "" and self.url.startswith("http")

    def get_json(self):
        return {
            "url": self.url,
            "title": self.title
        }

    @staticmethod
    def from_json(json):
        return NetworkMediaURL(**json)

    def __str__(self):
        return self.url
    
    def __eq__(self, value: object) -> bool:
        return self.__dict__ == value.__dict__

    def __hash__(self) -> int:
        return hash(self.__dict__)



class NetworkMediaWindow(BaseWindow):
    '''
    Window to start playlists from a URL.
    '''
    COL_0_WIDTH = 300
    top_level = None
    MAX_RESULTS = config.max_search_results
    MAX_RECENT_SEARCHES = 200
    recent_media_urls = []

    @staticmethod
    def load_recent_media_urls():
        recent_media_urls = app_info_cache.get("recent_media_urls", [])
        assert recent_media_urls is not None
        for json in recent_media_urls:
            media_url = NetworkMediaURL(**json)
            NetworkMediaWindow.recent_media_urls.append(media_url)

    @staticmethod
    def store_recent_media_urls():
        json_urls = []
        for media_urls in NetworkMediaWindow.recent_media_urls:
            if media_urls.is_valid() and media_urls.stored_results_count > 0:
                json_urls.append(media_urls.to_json())
        app_info_cache.set("recent_media_urls", json_urls)

    def __init__(self, master, app_actions, dimensions="1550x700"):
        super().init()
        NetworkMediaWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        NetworkMediaWindow.top_level.geometry(dimensions)
        NetworkMediaWindow.set_title(_("Search Library"))
        self.master = NetworkMediaWindow.top_level
        self.master.resizable(True, True)
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        self.app_actions = app_actions
        self.library_data = LibraryData()
        self.library_data_search = None
        self.has_closed = False

        self.outer_frame = Frame(self.master, bg=AppStyle.BG_COLOR, width=1500)
        self.outer_frame.grid_rowconfigure(0, weight=1)
        self.outer_frame.grid_rowconfigure(0, weight=7)
        self.outer_frame.grid(row=0, column=0, sticky="nsew")

        self.results_frame = ScrollFrame(self.outer_frame, bg_color=AppStyle.BG_COLOR, width=1500)
        self.results_frame.grid(row=0, column=0, sticky="nsew")

        self.inner_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR, width=1500)
        self.inner_frame.grid_columnconfigure(0, weight=1)
        self.inner_frame.grid_columnconfigure(1, weight=1)
        self.inner_frame.grid_columnconfigure(2, weight=1)
        self.inner_frame.grid(row=1, column=0, sticky="nsew")

        self.link_list = []
        self.page_title_list = []
        self.check_btn_list = []
        self.play_btn_list = []

        self.search_btn = None
        self.add_btn("search_btn", _("Search"), self.do_search, row=0)

        self._link_label = Label(self.inner_frame)
        self.add_label(self._link_label, "URL", row=1)
        self.link = StringVar(self.inner_frame)
        self.link_entry = Entry(self.inner_frame, textvariable=self.link)
        self.link_entry.grid(row=2, column=1)
        self.link_entry.bind("<Return>", self.do_search)
        self.link_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("title"))
        self.link_button.grid(row=2, column=2)

        # self.master.bind("<Key>", self.filter_targets)
        # self.master.bind("<Return>", self.do_action)
        self.master.bind("<Escape>", self.on_closing)
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        Utils.start_thread(self.show_recent_media_urls, use_asyncio=False)

    def show_recent_media_urls(self):
        if len(NetworkMediaWindow.recent_media_urls) == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No recent urls found."), row=1, column=1)
            self.link_list.append(self.searching_label)
            self.master.update()
            return
        for i in range(len(NetworkMediaWindow.recent_media_urls)):
            row = i + 1
            search = NetworkMediaWindow.recent_media_urls[i]
            track = self.library_data.get_track(search.selected_track_path)
            if track is not None:
                title = track.title
                album = track.album
            else:
                title = _("(No track selected)")
                album = "--"

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, title, row=row, column=1, wraplength=200)
            self.link_list.append(title_label)

            album_label = Label(self.results_frame.viewPort)
            self.add_label(album_label, album, row=row, column=2, wraplength=200)
            self.page_title_list.append(album_label)

            search_label = Label(self.results_frame.viewPort)
            self.add_label(search_label, str(search), row=row, column=3, wraplength=200)
            self.artist_list.append(search_label)

            results_count_label = Label(self.results_frame.viewPort)
            self.add_label(results_count_label, search.get_readable_stored_results_count(), row=row, column=4, wraplength=200)
            self.composer_list.append(results_count_label)

            search_btn = Button(self.results_frame.viewPort, text=_("Search"))
            self.check_btn_list.append(search_btn)
            search_btn.grid(row=row, column=5)
            def search_handler(event, self=self, search=search):
                self.load_stored_search(library_data_search=search)
                self._do_search(event)
            search_btn.bind("<Button-1>", search_handler)

            play_btn = Button(self.results_frame.viewPort, text=_("Play"))
            self.play_btn_list.append(play_btn)
            play_btn.grid(row=row, column=6)
            def play_handler(event, self=self, search=search, track=track):
                self.load_stored_search(library_data_search=search)
                self._do_search(event)
                if track is None:
                    logger.info("No specific track defined on search, using first available track.")
                    track = search.get_first_available_track()
                    if track is None:
                        raise Exception("No tracks available on search.")
                elif track.is_invalid():
                    raise Exception(f"Invalid track: {track}")
                self.run_play_callback(track)
            play_btn.bind("<Button-1>", play_handler)
        self.master.update()

    def do_search(self, event=None):
        title = self.link.get().strip()
        self.library_data_search = LibraryDataSearch(all, title=title, album=album,
                                                     artist=artist, composer=composer,
                                                     genre=genre, instrument=instrument,
                                                     form=form, max_results=NetworkMediaWindow.MAX_RESULTS)
        self._do_search(overwrite=overwrite)

    def load_stored_search(self, library_data_search):
        assert library_data_search is not None
        self.link.set(library_data_search.title)
        self.library_data_search = library_data_search

    def _do_search(self, event=None, overwrite=False):
        assert self.library_data_search is not None
        self._refresh_widgets(add_results=False)
        self.searching_label = Label(self.results_frame.viewPort)
        searching_text = _("Please wait, overwriting cache and searching...") if overwrite else _("Searching...")
        self.add_label(self.searching_label, text=searching_text, row=1, column=1)
        self.link_list.append(self.searching_label)
        self.master.update()
        self.library_data.do_search(self.library_data_search, overwrite=overwrite)
        self.update_recent_media_urls()
        self._refresh_widgets()

    def update_recent_media_urls(self, remove_urls_with_no_selected_filepath=False):
        assert self.library_data_search is not None
        if self.library_data_search in NetworkMediaWindow.recent_media_urls:
            NetworkMediaWindow.recent_media_urls.remove(self.library_data_search)
        if remove_urls_with_no_selected_filepath:
            urls_to_remove = []
            for search in NetworkMediaWindow.recent_media_urls:
                if (search.selected_track_path == None or search.selected_track_path.strip() == "") and \
                        search.matches_no_selected_track_path(self.library_data_search):
                    NetworkMediaWindow.recent_media_urls.remove(search)
            for search in urls_to_remove:
                NetworkMediaWindow.recent_media_urls.remove(search)
        NetworkMediaWindow.recent_media_urls.insert(0, self.library_data_search)
        if len(NetworkMediaWindow.recent_media_urls) > NetworkMediaWindow.MAX_RECENT_SEARCHES:
            del NetworkMediaWindow.recent_media_urls[-1]

    def sort_by(self, attr):
        assert self.library_data_search is not None
        self.library_data_search.sort_results_by(attr)
        self._refresh_widgets()

    def add_widgets_for_results(self):
        assert self.library_data_search is not None
        if len(self.library_data_search.results) == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No recent urls found."), row=1, column=1)
            self.link_list.append(self.searching_label)
            self.master.update()
            return
        self.library_data_search.sort_results_by()
        results = self.library_data_search.get_results()
        for i in range(len(results)):
            row = i + 1
            track = results[i]

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, track.title, row=row, column=1, wraplength=200)
            self.link_list.append(title_label)

            artist_label = Label(self.results_frame.viewPort)
            self.add_label(artist_label, track.artist, row=row, column=2, wraplength=200)
            self.artist_list.append(artist_label)

            album_label = Label(self.results_frame.viewPort)
            self.add_label(album_label, track.album, row=row, column=3, wraplength=200)
            self.page_title_list.append(album_label)
            
            composer_label = Label(self.results_frame.viewPort)
            self.add_label(composer_label, track.composer, row=row, column=4, wraplength=200)
            self.composer_list.append(composer_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.check_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=5)
            def open_details_handler(event, self=self, audio_track=track):
                self.open_details(audio_track)
            open_details_btn.bind("<Button-1>", open_details_handler)

            play_btn = Button(self.results_frame.viewPort, text=_("Play"))
            self.play_btn_list.append(play_btn)
            play_btn.grid(row=row, column=6)
            def play_handler(event, self=self, audio_track=track):
                logger.info(f"User selected audio track: {audio_track}")
                self.run_play_callback(audio_track)
            play_btn.bind("<Button-1>", play_handler)

            # TODO add to playlist buttons

    def open_details(self, track):
        pass

    def run_play_callback(self, track, library_data_search=None):
        if track is None or track.is_invalid():
            raise Exception(f"Invalid track: {track}")

        if library_data_search is None:
            library_data_search = self.library_data_search
        assert library_data_search is not None
        library_data_search.set_selected_track_path(track)
        # the below argument ensures that stored recent urls will have a selected
        # filepath if the user selected to play from them.
        self.update_recent_media_urls(remove_urls_with_no_selected_filepath=True)
        playlist_sort_type = self.get_playlist_sort_type()
        self.app_actions.start_play_callback(track=track, playlist_sort_type=playlist_sort_type, overwrite=self.overwrite_cache.get())

    def get_playlist_sort_type(self):
        if len(self.composer.get()) > 0:
            return PlaylistSortType.COMPOSER_SHUFFLE
        elif len(self.artist.get()) > 0:
            return PlaylistSortType.ARTIST_SHUFFLE
        elif len(self.genre.get()) > 0:
            return PlaylistSortType.GENRE_SHUFFLE
        elif len(self.instrument.get()) > 0:
            return PlaylistSortType.INSTRUMENT_SHUFFLE
        elif len(self.form.get()) > 0:
            return PlaylistSortType.FORM_SHUFFLE
        elif len(self.album.get()) > 0:
            return PlaylistSortType.ALBUM_SHUFFLE
        return PlaylistSortType.RANDOM

    def _refresh_widgets(self, add_results=True):
        self.clear_widget_lists()
        if add_results:
            self.add_widgets_for_results()
        self.master.update()

    def clear_widget_lists(self):
        for label in self.link_list:
            label.destroy()
        for label in self.artist_list:
            label.destroy()
        for label in self.page_title_list:
            label.destroy()
        for label in self.composer_list:
            label.destroy()
        for btn in self.check_btn_list:
            btn.destroy()
        for btn in self.play_btn_list:
            btn.destroy()
        self.link_list = []
        self.artist_list = []
        self.page_title_list = []
        self.composer_list = []
        self.check_btn_list = []
        self.play_btn_list = []

    @staticmethod
    def set_title(extra_text):
        NetworkMediaWindow.top_level.title(_("Search") + " - " + extra_text)

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

