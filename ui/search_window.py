from tkinter import Frame, Label, StringVar, BooleanVar, Checkbutton, LEFT, W
from tkinter.ttk import Button, Entry, Combobox

from lib.multi_display import SmartToplevel
from lib.tk_scroll_demo import ScrollFrame
from library_data.library_data import LibraryDataSearch
from ui.auth.password_utils import require_password
from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType, ProtectedActions
from utils.translations import I18N
from utils.utils import Utils
from utils.logging_setup import get_logger

# Get logger for this module
logger = get_logger(__name__)

_ = I18N._


## TODO create a playlist from the search results, instead of simply passing a PlaylistSortType
## TODO improve search with multi-level filtering on the same attribute - see C:\Scripts\search_music.py


class SearchWindow(BaseWindow):
    '''
    Window to search media library.
    '''
    COL_0_WIDTH = 300
    top_level = None
    INITIAL_MAX_RESULTS = config.max_search_results
    MAX_RECENT_SEARCHES = 200  # Maximum number of recent searches to persist
    recent_searches = []

    @staticmethod
    def load_recent_searches():
        # Clear existing searches to prevent duplicates if called multiple times
        SearchWindow.recent_searches.clear()
        
        recent_searches = app_info_cache.get("recent_searches", [])
        assert recent_searches is not None
        
        # Deduplicate by using a set to track seen searches
        seen_searches = set()
        skip_count = 0
        for search_json in recent_searches:
            library_data_search = LibraryDataSearch.from_json(search_json)
            if library_data_search.is_valid() and library_data_search.stored_results_count > 0:
                # Only add if we haven't seen this search before (using hash/eq)
                if library_data_search not in seen_searches:
                    SearchWindow.recent_searches.append(library_data_search)
                    seen_searches.add(library_data_search)
                else:
                    skip_count += 1
            else:
                logger.warning(f"Invalid search removed: {search_json}")
        
        if skip_count > 0:
            logger.warning(f"Skipped {skip_count} duplicate searches")

        # Limit to MAX_RECENT_SEARCHES to prevent excessive growth
        if len(SearchWindow.recent_searches) > SearchWindow.MAX_RECENT_SEARCHES:
            logger.warning(f"Limiting searches from {len(SearchWindow.recent_searches)} to {SearchWindow.MAX_RECENT_SEARCHES}")
            SearchWindow.recent_searches = SearchWindow.recent_searches[:SearchWindow.MAX_RECENT_SEARCHES]

    @staticmethod
    def store_recent_searches():
        # Deduplicate searches before storing
        seen_searches = set()
        unique_searches = []
        for library_data_search in SearchWindow.recent_searches:
            if library_data_search.is_valid() and library_data_search.stored_results_count > 0:
                # Only add if we haven't seen this search before
                if library_data_search not in seen_searches:
                    unique_searches.append(library_data_search)
                    seen_searches.add(library_data_search)
        
        # Limit to MAX_RECENT_SEARCHES
        if len(unique_searches) > SearchWindow.MAX_RECENT_SEARCHES:
            logger.warning(f"Limiting stored searches from {len(unique_searches)} to {SearchWindow.MAX_RECENT_SEARCHES}")
            unique_searches = unique_searches[:SearchWindow.MAX_RECENT_SEARCHES]
        
        json_searches = [search.to_json() for search in unique_searches]
        app_info_cache.set("recent_searches", json_searches)

    @staticmethod
    def find_track(library_data, library_data_search, save_to_recent=False, overwrite=False):
        """Search for a track and play it if found.
        
        Args:
            library_data: The LibraryData instance to use for searching
            library_data_search: The LibraryDataSearch object to use for searching
            save_to_recent: Whether to save this search to recent searches
            overwrite: Whether to overwrite the cache when searching
        """
        try:
            # First try to find by ID if provided
            if library_data_search.id:
                track = library_data.find_track_by_id(library_data_search.id, overwrite=overwrite)
                if track:
                    return track
                logger.info("No track found by ID, falling back to search")

            # NOTE: Overwrite should be False for next calls because cache would have been
            # overwritten by the above call

            # Perform search and get first result
            library_data.do_search(library_data_search, overwrite=False)
            results = library_data_search.get_results()
            
            if results:
                # Save to recent searches if requested
                if save_to_recent:
                    library_data_search.set_selected_track_path(results[0])
                    SearchWindow.update_recent_searches(library_data_search)
            elif library_data_search.title:
                # If no results and we have a title search with sufficient length, try fuzzy matching
                matches = library_data.find_track_by_fuzzy_title(
                    library_data_search.title, 
                    overwrite=False, 
                    max_results=1  # We only need one match for find_track
                )
                if matches:
                    results = matches
            
            if not results:
                raise ValueError(_("No matching tracks found"))
                
            # Get the first track
            track = results[0]
            return track
            
        except Exception as e:
            logger.error(f"Error in find_track: {str(e)}")
            raise

    def __init__(self, master, app_actions, library_data, dimensions="1550x700"):
        super().__init__()
        # Get parent window position to determine positioning
        parent_x = master.winfo_x()
        parent_y = master.winfo_y()
        
        # Extract window dimensions
        width, height = map(int, dimensions.split('x'))
        
        # Position at least 50 pixels away from the left side of the main window
        offset_x = 50
        new_x = parent_x + offset_x
        
        # Get screen width to check bounds
        screen_width = master.winfo_screenwidth()
        
        # If window would go off-screen to the right, adjust so right edge is within bounds
        if new_x + width > screen_width:
            # Position so right edge is at screen edge (with small margin)
            margin = 10
            new_x = screen_width - width - margin
            # Ensure we don't go negative (window too wide for screen)
            if new_x < 0:
                new_x = 0
        
        # Use default vertical offset
        offset_y = 30
        new_y = parent_y + offset_y
        
        # Create geometry string with custom positioning
        positioned_geometry = f"{dimensions}+{new_x}+{new_y}"
        
        SearchWindow.top_level = SmartToplevel(persistent_parent=master, geometry=positioned_geometry, auto_position=False)
        SearchWindow.set_title(_("Search Library"))
        self.master = SearchWindow.top_level
        self.master.resizable(True, True)
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        self.app_actions = app_actions
        self.library_data = library_data
        self.library_data_search = None
        self.has_closed = False

        self.outer_frame = Frame(self.master, bg=AppStyle.BG_COLOR, width=1500)
        self.outer_frame.grid_rowconfigure(0, weight=1)
        self.outer_frame.grid_rowconfigure(0, weight=7)
        self.outer_frame.grid(row=0, column=0, sticky="nsew")

        self.results_frame = ScrollFrame(self.outer_frame, bg_color=AppStyle.BG_COLOR, width=1500)
        self.results_frame.grid(row=0, column=0, sticky="nsew")

        # Pagination frame (fixed, not scrollable) - between results and search controls
        self.pagination_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR, width=1500)
        self.pagination_frame.grid_columnconfigure(0, weight=1)
        self.pagination_frame.grid(row=1, column=0, sticky="ew")

        self.inner_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR, width=1500)
        self.inner_frame.grid_columnconfigure(0, weight=1)
        self.inner_frame.grid_columnconfigure(1, weight=1)
        self.inner_frame.grid_columnconfigure(2, weight=1)
        self.inner_frame.grid(row=2, column=0, sticky="nsew")

        self.title_list = []
        self.album_list = []
        self.artist_list = []
        self.composer_list = []
        self.open_details_btn_list = []
        self.play_btn_list = []
        self.remove_btn_list = []
        
        # Load more state (for accumulating results)
        self.current_offset = 0
        self.pagination_warning_label = None
        self.pagination_next_btn = None  # "Find More" button
        
        # Filter state
        self.filter_text = StringVar(self.inner_frame)
        self.filter_entry = None

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
        self.sort_by_title_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("title"))
        self.sort_by_title_button.grid(row=2, column=2)

        self._album_label = Label(self.inner_frame)
        self.add_label(self._album_label, "Search Album", row=3)
        self.album = StringVar(self.inner_frame)
        self.album_entry = Entry(self.inner_frame, textvariable=self.album)
        self.album_entry.grid(row=3, column=1)
        self.album_entry.bind("<Return>", self.do_search)
        self.sort_by_album_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("album"))
        self.sort_by_album_button.grid(row=3, column=2)

        self._artist_label = Label(self.inner_frame)
        self.add_label(self._artist_label, "Search Artist", row=4)
        self.artist = StringVar(self.inner_frame)
        self.artist_entry = Entry(self.inner_frame, textvariable=self.artist)
        self.artist_entry.grid(row=4, column=1)
        self.artist_entry.bind("<Return>", self.do_search)
        self.sort_by_artist_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("artist"))
        self.sort_by_artist_button.grid(row=4, column=2)

        self._composer_label = Label(self.inner_frame)
        self.add_label(self._composer_label, "Search Composer", row=5)
        self.composer = StringVar(self.inner_frame)
        self.composer_entry = Entry(self.inner_frame, textvariable=self.composer)
        self.composer_entry.grid(row=5, column=1)
        self.composer_entry.bind("<Return>", self.do_search)
        self.sort_by_composer_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("composer"))
        self.sort_by_composer_button.grid(row=5, column=2)

        self._genre_label = Label(self.inner_frame)
        self.add_label(self._genre_label, "Search Genre", row=6)
        self.genre = StringVar(self.inner_frame)
        self.genre_entry = Entry(self.inner_frame, textvariable=self.genre)
        self.genre_entry.grid(row=6, column=1)
        self.genre_entry.bind("<Return>", self.do_search)
        self.sort_by_genre_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("genre"))
        self.sort_by_genre_button.grid(row=6, column=2)

        self._instrument_label = Label(self.inner_frame)
        self.add_label(self._instrument_label, "Search Instrument", row=7)
        self.instrument = StringVar(self.inner_frame)
        self.instrument_entry = Entry(self.inner_frame, textvariable=self.instrument)
        self.instrument_entry.grid(row=7, column=1)
        self.instrument_entry.bind("<Return>", self.do_search)
        self.sort_by_instrument_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("instrument"))
        self.sort_by_instrument_button.grid(row=7, column=2)

        self._form_label = Label(self.inner_frame)
        self.add_label(self._form_label, "Search Form", row=8)
        self.form = StringVar(self.inner_frame)
        self.form_entry = Entry(self.inner_frame, textvariable=self.form)
        self.form_entry.grid(row=8, column=1)
        self.form_entry.bind("<Return>", self.do_search)
        self.sort_by_form_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("form"))
        self.sort_by_form_button.grid(row=8, column=2)

        self.overwrite_cache = BooleanVar(self.inner_frame)
        self._overwrite = Checkbutton(self.inner_frame, text=_("Overwrite Cache"), variable=self.overwrite_cache)
        self._overwrite.grid(row=9, column=0, sticky=W)
        
        # Playlist sort type dropdown
        self._playlist_sort_label = Label(self.inner_frame)
        self.add_label(self._playlist_sort_label, _("Playlist Sort"), row=9, column=1)
        self.playlist_sort_type_var = StringVar(self.inner_frame)
        self.playlist_sort_combo = Combobox(
            self.inner_frame, 
            textvariable=self.playlist_sort_type_var,
            values=PlaylistSortType.get_translated_names(),
            state="readonly",
            width=20
        )
        self.playlist_sort_combo.grid(row=9, column=2, sticky=W)
        # Set initial value to RANDOM
        self.playlist_sort_type_var.set(PlaylistSortType.RANDOM.get_translation())
        # Update dropdown based on initial search fields
        self._update_playlist_sort_dropdown()
        
        # Filter field for filtering search results
        self._filter_label = Label(self.inner_frame)
        self.add_label(self._filter_label, _("Filter Results"), row=10)
        self.filter_entry = Entry(self.inner_frame, textvariable=self.filter_text)
        self.filter_entry.grid(row=10, column=1)
        self.filter_entry.bind("<KeyRelease>", self.apply_filter)
        self.filter_entry.grid_remove()  # Hidden by default, shown after search

        # self.master.bind("<Key>", self.filter_targets)
        # self.master.bind("<Return>", self.do_action)
        self.master.bind("<Escape>", self.on_closing)
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        Utils.start_thread(self.show_recent_searches, use_asyncio=False)

    def show_recent_searches(self):
        if len(SearchWindow.recent_searches) == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No recent searches found."), row=1, column=1)
            self.title_list.append(self.searching_label)
            self.master.update()
            return
        for i in range(len(SearchWindow.recent_searches)):
            row = i + 1
            search = SearchWindow.recent_searches[i]
            track = self.library_data.get_track(search.selected_track_path)
            if track is not None:
                title = track.title
                album = track.album
            else:
                title = _("(No track selected)")
                album = "--"

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, title, row=row, column=1, wraplength=200)
            self.title_list.append(title_label)

            album_label = Label(self.results_frame.viewPort)
            self.add_label(album_label, album, row=row, column=2, wraplength=200)
            self.album_list.append(album_label)

            search_label = Label(self.results_frame.viewPort)
            self.add_label(search_label, str(search), row=row, column=3, wraplength=200)
            self.artist_list.append(search_label)

            results_count_label = Label(self.results_frame.viewPort)
            self.add_label(results_count_label, search.get_readable_stored_results_count(), row=row, column=4, wraplength=200)
            self.composer_list.append(results_count_label)

            search_btn = Button(self.results_frame.viewPort, text=_("Search"))
            self.open_details_btn_list.append(search_btn)
            search_btn.grid(row=row, column=5)
            def search_handler(event, self=self, search=search):
                self.load_stored_search(library_data_search=search)
                self._do_search(event, overwrite=self.overwrite_cache.get())
            search_btn.bind("<Button-1>", search_handler)

            play_btn = Button(self.results_frame.viewPort, text=_("Play"))
            self.play_btn_list.append(play_btn)
            play_btn.grid(row=row, column=6)
            def play_handler(event, self=self, search=search, track=track):
                self.load_stored_search(library_data_search=search)
                self._do_search(event)  # Avoid overwrite cache here since we probably just did it
                if track is None:
                    logger.info("No specific track defined on search, using first available track.")
                    track = search.get_first_available_track()
                    if track is None:
                        raise Exception("No tracks available on search.")
                elif track.is_invalid():
                    raise Exception(f"Invalid track: {track}")
                self.run_play_callback(track)
            play_btn.bind("<Button-1>", play_handler)

            remove_btn = Button(self.results_frame.viewPort, text=_("Remove"))
            self.remove_btn_list.append(remove_btn)
            remove_btn.grid(row=row, column=7)
            def remove_handler(event, self=self, search=search):
                self.remove_search(search)
            remove_btn.bind("<Button-1>", remove_handler)
        self.master.update()

    @require_password(ProtectedActions.RUN_SEARCH)
    def do_search(self, event=None):
        all = self.all.get().strip()
        title = self.title.get().strip()
        album = self.album.get().strip()
        artist = self.artist.get().strip()
        composer = self.composer.get().strip()
        genre = self.genre.get().strip()
        instrument = self.instrument.get().strip()
        form = self.form.get().strip()
        overwrite = self.overwrite_cache.get()
        # Reset offset and filter when starting a new search
        self.current_offset = 0
        self.filter_text.set("")
        # Update playlist sort dropdown based on search fields
        self._update_playlist_sort_dropdown()
        self.library_data_search = LibraryDataSearch(all, title=title, album=album,
                                                     artist=artist, composer=composer,
                                                     genre=genre, instrument=instrument,
                                                     form=form, max_results=SearchWindow.INITIAL_MAX_RESULTS, offset=0)
        self._do_search(overwrite=overwrite)

    def load_stored_search(self, library_data_search):
        assert library_data_search is not None
        self.all.set(library_data_search.all)
        self.title.set(library_data_search.title)
        self.album.set(library_data_search.album)
        self.artist.set(library_data_search.artist)
        self.composer.set(library_data_search.composer)
        self.genre.set(library_data_search.genre)
        self.instrument.set(library_data_search.instrument)
        self.form.set(library_data_search.form)
        self.library_data_search = library_data_search
        # Update playlist sort dropdown based on loaded search fields
        self._update_playlist_sort_dropdown()

    @require_password(ProtectedActions.RUN_SEARCH)
    def _do_search(self, event=None, overwrite=False):
        assert self.library_data_search is not None
        # Set the offset on the search object for loading more results
        self.library_data_search.offset = self.current_offset
        # Preserve total_matches_count when loading more (only reset on new search)
        # Store the previous total before clearing results
        previous_total = getattr(self.library_data_search, 'total_matches_count', 0)
        # Store existing results if loading more (to preserve them for accumulation in LibraryDataSearch)
        existing_results = []
        if self.current_offset > 0 and not overwrite:
            existing_results = self.library_data_search.results.copy()
        
        # Only reset if this is a new search (offset is 0) or if overwriting
        if self.current_offset == 0 or overwrite:
            self.library_data_search.total_matches_count = 0
            self.library_data_search.results = []
        # When loading more, we need to continue counting from the offset
        # Initialize total_matches_count to offset so it continues counting correctly
        # Preserve existing results so new ones will be appended to them during search
        else:
            self.library_data_search.total_matches_count = self.current_offset
            self.library_data_search.results = existing_results
        self._refresh_widgets(add_results=False)
        self.searching_label = Label(self.results_frame.viewPort)
        searching_text = _("Please wait, overwriting cache and searching...") if overwrite else _("Searching...")
        self.add_label(self.searching_label, text=searching_text, row=1, column=1)
        self.title_list.append(self.searching_label)
        self.master.update()

        def search_complete(search_results):
            """Callback for when search completes."""
            # Results are already accumulated in library_data_search.results
            # (existing results were preserved, and new ones were appended during search)
            # Schedule UI update on main thread
            self.master.after(0, lambda: self._update_ui_after_search())

        def update_status(status_text):
            """Callback for updating search status."""
            # Schedule UI update on main thread
            self.master.after(0, lambda: self._update_search_status(status_text))

        def search_thread():
            try:
                self.library_data.do_search(
                    self.library_data_search, 
                    overwrite=overwrite, 
                    completion_callback=search_complete,
                    search_status_callback=update_status
                )
            except Exception as e:
                logger.error(f"Error in search thread: {e}")
                # Schedule UI update on main thread
                self.master.after(0, lambda: self._show_search_error(str(e)))

        # Start search in a separate thread
        Utils.start_thread(search_thread, use_asyncio=False)

    def _update_ui_after_search(self):
        """Update the UI after a search completes."""
        SearchWindow.update_recent_searches(self.library_data_search)
        # Show filter field after search completes
        if self.filter_entry is not None:
            self.filter_entry.grid()
        self._refresh_widgets()

    def _show_search_error(self, error_msg):
        """Show an error message in the search results."""
        self._refresh_widgets(add_results=False)
        error_label = Label(self.results_frame.viewPort)
        self.add_label(error_label, text=error_msg, row=1, column=1)
        self.title_list.append(error_label)
        self.master.update()

    def on_closing(self, event=None):
        """Handle window closing."""
        self.master.destroy()
        self.has_closed = True

    @staticmethod
    def update_recent_searches(library_data_search, remove_searches_with_no_selected_filepath=False):
        assert library_data_search is not None
        # Remove all instances of this search (handles duplicates)
        SearchWindow.recent_searches = [s for s in SearchWindow.recent_searches if s != library_data_search]
        
        if remove_searches_with_no_selected_filepath:
            # Remove all searches that match, without considering the selected track path
            SearchWindow.recent_searches = [
                s for s in SearchWindow.recent_searches 
                if not ((s.selected_track_path is None or s.selected_track_path.strip() == "") and 
                        s.matches_no_selected_track_path(library_data_search))
            ]
        
        SearchWindow.recent_searches.insert(0, library_data_search)
        if len(SearchWindow.recent_searches) > SearchWindow.MAX_RECENT_SEARCHES:
            del SearchWindow.recent_searches[-1]

    def sort_by(self, attr):
        assert self.library_data_search is not None
        self.library_data_search.sort_results_by(attr)
        self._refresh_widgets()

    def add_widgets_for_results(self):
        assert self.library_data_search is not None
        if len(self.library_data_search.results) == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No results found."), row=1, column=1)
            self.title_list.append(self.searching_label)
            
            # Add cache reminder
            cache_reminder = Label(self.results_frame.viewPort)
            self.add_label(cache_reminder, text=_("Tip: If you've recently added or moved files, try checking 'Overwrite Cache' in the search options below."), row=2, column=1)
            self.title_list.append(cache_reminder)
            
            self.master.update()
            return
        
        self.library_data_search.sort_results_by()
        results = self.library_data_search.get_results()
        total_results = len(results)
        stored_count = self.library_data_search.stored_results_count
        
        # Apply filter if filter text is provided
        filter_text = self.filter_text.get().strip().lower() if self.filter_text else ""
        if filter_text:
            # Filter results based on filter text matching any displayed field
            filtered_results = []
            for track in results:
                # Check if filter text appears in any of the displayed fields
                if (filter_text in (track.title or "").lower() or
                    filter_text in (track.artist or "").lower() or
                    filter_text in (track.album or "").lower() or
                    filter_text in (track.composer or "").lower()):
                    filtered_results.append(track)
            display_results = filtered_results
        else:
            # No filter, show all results
            display_results = results
        
        display_count = len(display_results)
        
        # Show message if filter returns no results
        if filter_text and display_count == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No results match the filter '{0}'.").format(self.filter_text.get()), row=1, column=1)
            self.title_list.append(self.searching_label)
            self.master.update()
            return
        
        # Check if there are more results available
        # For the first search, check if we got more than INITIAL_MAX_RESULTS
        # For loading more, check if stored_count indicates more than what we have
        if self.current_offset == 0:
            # First search - check if we got more than INITIAL_MAX_RESULTS
            has_more_detected = total_results > SearchWindow.INITIAL_MAX_RESULTS
        else:
            # Loading more - check if stored_count indicates there are more results available
            has_more_detected = stored_count > total_results
        
        # Calculate display range - results accumulate in LibraryDataSearch object
        total_displayed = total_results
        
        # Determine if we should show load more controls
        # Show warning if: 
        # - We detected more results (have max_results + 1)
        # - We know there are more total results than displayed
        # - We've loaded more results (current_offset > 0)
        has_more_total = stored_count > (self.current_offset + display_count)
        has_loaded_more = self.current_offset > 0
        
        # Add warning and load more controls in the fixed frame (not scrollable)
        if has_more_detected or has_more_total or has_loaded_more:
            # Create warning label if it doesn't exist
            if self.pagination_warning_label is None:
                self.pagination_warning_label = Label(self.pagination_frame)
                # Use light yellow/orange color for warning text
                self.pagination_warning_label.config(bg=AppStyle.BG_COLOR, fg="#FFB84D", wraplength=800, justify=LEFT)
            
            # Update warning text
            # Note: Results accumulate (showing all results loaded so far, not just current batch)
            # Show both values only if they are different
            filter_text = self.filter_text.get().strip().lower() if self.filter_text else ""
            if filter_text:
                # Show filtered count vs total count when filtering is active
                if stored_count != display_count:
                    warning_text = _("Found {0} total results. Showing {1} filtered results.").format(
                        stored_count, display_count
                    )
                else:
                    warning_text = _("Showing {0} filtered results.").format(display_count)
            elif stored_count != total_displayed:
                warning_text = _("Found {0} total results. Showing all results up to {1}.").format(
                    stored_count, total_displayed
                )
            else:
                warning_text = _("Showing all results up to {0}.").format(
                    total_displayed
                )
            
            self.pagination_warning_label.config(text=warning_text)
            self.pagination_warning_label.grid(row=0, column=0, columnspan=3, sticky=W, padx=5, pady=5)
            
            # Find More button - show if we detected more results or know there are more
            if has_more_detected or has_more_total:
                if self.pagination_next_btn is None:
                    self.pagination_next_btn = Button(self.pagination_frame, text=_("Find More"), command=self.load_more_results)
                self.pagination_next_btn.grid(row=0, column=1, padx=5, pady=5)
            elif self.pagination_next_btn is not None:
                self.pagination_next_btn.grid_remove()
        else:
            # Hide warning and load more widgets if not needed
            if self.pagination_warning_label is not None:
                self.pagination_warning_label.grid_remove()
            if self.pagination_next_btn is not None:
                self.pagination_next_btn.grid_remove()
        
        # Display results (only show first max_results, not the extra one used for detection)
        # Results start at row 1 (row 0 is for any header if needed)
        results_start_row = 1
        for i, track in enumerate(display_results):
            row = results_start_row + i

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, track.title, row=row, column=1, wraplength=200)
            self.title_list.append(title_label)

            artist_label = Label(self.results_frame.viewPort)
            self.add_label(artist_label, track.artist, row=row, column=2, wraplength=200)
            self.artist_list.append(artist_label)

            album_label = Label(self.results_frame.viewPort)
            self.add_label(album_label, track.album, row=row, column=3, wraplength=200)
            self.album_list.append(album_label)
            
            composer_label = Label(self.results_frame.viewPort)
            self.add_label(composer_label, track.composer, row=row, column=4, wraplength=200)
            self.composer_list.append(composer_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
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
        # the below argument ensures that stored recent searches will have a selected
        # filepath if the user selected to play from them.
        SearchWindow.update_recent_searches(library_data_search, remove_searches_with_no_selected_filepath=True)
        playlist_sort_type = self.get_playlist_sort_type()
        self.app_actions.start_play_callback(track=track, playlist_sort_type=playlist_sort_type, overwrite=self.overwrite_cache.get())

    def _update_playlist_sort_dropdown(self):
        """Update the playlist sort dropdown to reflect the largest scope in the search fields."""
        largest_scope = PlaylistSortType.get_largest_scope_from_search_fields(
            composer=self.composer.get(),
            artist=self.artist.get(),
            genre=self.genre.get(),
            instrument=self.instrument.get(),
            form=self.form.get(),
            album=self.album.get()
        )
        self.playlist_sort_type_var.set(largest_scope.get_translation())

    def get_playlist_sort_type(self):
        # TODO: In the future, send all scopes from the search to the playlist for multi-level sorting
        # Currently, only the selected sort type is used
        selected_translation = self.playlist_sort_type_var.get()
        return PlaylistSortType.get_from_translation(selected_translation)

    def remove_search(self, search):
        assert search is not None
        # Remove all instances of this search (handles duplicates)
        SearchWindow.recent_searches = [s for s in SearchWindow.recent_searches if s != search]
        self.store_recent_searches()
        self.clear_widget_lists()
        self.show_recent_searches()

    def _refresh_widgets(self, add_results=True):
        self.clear_widget_lists()
        if add_results:
            self.add_widgets_for_results()
        self.master.update()
    
    def apply_filter(self, event=None):
        """Apply filter to search results."""
        # Just refresh the widgets to re-display with filter applied
        self._refresh_widgets()

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
        for btn in self.play_btn_list:
            btn.destroy()
        for btn in self.remove_btn_list:
            btn.destroy()
        # Note: Pagination widgets are in pagination_frame (not scrollable), so they persist
        # They are managed in add_widgets_for_results() with grid_remove/grid
        self.title_list = []
        self.artist_list = []
        self.album_list = []
        self.composer_list = []
        self.open_details_btn_list = []
        self.play_btn_list = []
        self.remove_btn_list = []

    @staticmethod
    def set_title(extra_text):
        SearchWindow.top_level.title(_("Search") + " - " + extra_text)

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

    def _update_search_status(self, status_text):
        """Update the search status label with progress information."""
        if hasattr(self, 'searching_label') and self.searching_label.winfo_exists():
            self.searching_label.config(text=status_text)
            self.master.update()
    
    def load_more_results(self):
        """Load more results by re-running the search with an increased offset."""
        if self.library_data_search is None:
            return
        
        stored_count = self.library_data_search.stored_results_count
        page_size = SearchWindow.INITIAL_MAX_RESULTS
        current_end = self.current_offset + page_size
        current_results = len(self.library_data_search.results)
        
        # Check if there are more results to load
        # We know there are more if we got max_results + 1 results (has_more_detected)
        # OR if stored_count > current_end
        has_more_detected = current_results > SearchWindow.INITIAL_MAX_RESULTS
        has_more_known = stored_count > current_end
        
        if has_more_detected or has_more_known:
            self.current_offset += page_size
            # Re-run the search with the new offset to load more results
            # Either we just did a search and overwrote the cache, or we are loading more results
            # so we don't need to overwrite it again
            self._do_search(overwrite=False)
        else:
            logger.info("Reached end of results")

