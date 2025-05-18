from tkinter import Toplevel, Frame, Label, Checkbutton, BooleanVar, StringVar, LEFT, W
import tkinter.font as fnt
from tkinter.ttk import Button, Entry, OptionMenu

from lib.tk_scroll_demo import ScrollFrame
from library_data.favorite import Favorite
from ui.app_style import AppStyle
# from ui.base_window import BaseWindow
from utils.app_info_cache import app_info_cache
from utils.translations import I18N
from utils.utils import Utils
from utils.globals import TrackAttribute

_ = I18N._


class FavoritesDataSearch:
    def __init__(self, favorite="", max_results=200):
        self.favorite = favorite.lower()
        self.max_results = max_results
        self.results = []

    def is_valid(self):
        return len(self.favorite.strip()) > 0

    def get_readable_results_count(self):
        count = len(self.results)
        if count > self.max_results:
            results_str = f"{self.max_results}+"
        else:
            results_str = str(count)
        return _("({0} results)").format(results_str)

    def get_results(self):
        return self.results

    def _get_match_priority(self, search_text: str) -> int:
        """Get the priority level of a match.
        
        Returns:
            int: 0 for no match, 1 for contains match, 2 for word boundary match, 3 for start match
        """
        if not self.favorite:
            return 0
            
        search_text = search_text.lower()
        
        # Tier 1: Match at start of string
        if search_text.startswith(self.favorite):
            return 3
            
        # Tier 2: Match at start of word
        words = search_text.split()
        for word in words:
            if word.startswith(self.favorite):
                return 2
                
        # Tier 3: Contains match
        if self.favorite in search_text:
            return 1
            
        return 0

    def add_result(self, favorite, search_text: str):
        """Add a result with its priority level."""
        priority = self._get_match_priority(search_text)
        if priority > 0:
            self.results.append((priority, favorite))

    def sort_results(self):
        """Sort results by priority (highest first) and limit to max_results."""
        # Sort by priority (descending) and then by the favorite value
        self.results.sort(key=lambda x: (-x[0], x[1].value))
        # Extract just the favorites, maintaining the sorted order
        self.results = [favorite for _, favorite in self.results[:self.max_results]]


class FavoritesWindow:
    '''
    Window to search favorites data.
    '''
    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200
    details_window = None
    recent_favorites = []  # List of Favorite objects, most recent first

    @staticmethod
    def load_favorites():
        json_favorites = app_info_cache.get("favorites", [])
        assert isinstance(json_favorites, list)
        FavoritesWindow.recent_favorites = []
        for fav_dict in json_favorites:
            FavoritesWindow.recent_favorites.append(Favorite.from_dict(fav_dict))
        # Sort by timestamp (most recent first)
        FavoritesWindow.recent_favorites.sort(key=lambda x: x.timestamp, reverse=True)

    @staticmethod
    def store_favorites():
        json_favorites = []
        for favorite in FavoritesWindow.recent_favorites:
            json_favorites.append(favorite.to_dict())
        app_info_cache.set("favorites", json_favorites)

    @staticmethod
    def set_favorite(track, is_favorited=False):
        if is_favorited:
            # Remove if already exists to update recency
            for existing_fav in FavoritesWindow.recent_favorites[:]:
                if existing_fav.attribute == TrackAttribute.TITLE and existing_fav.value == track.title:
                    FavoritesWindow.recent_favorites.remove(existing_fav)
                    break
            FavoritesWindow.recent_favorites.insert(0, Favorite.from_track(track))
        else:
            for existing_fav in FavoritesWindow.recent_favorites[:]:
                if existing_fav.attribute == TrackAttribute.TITLE and existing_fav.value == track.title:
                    FavoritesWindow.recent_favorites.remove(existing_fav)
                    break
        FavoritesWindow.store_favorites()

    @staticmethod
    def set_attribute_favorite(attribute: TrackAttribute, value: str, is_favorited: bool):
        if is_favorited:
            # Remove if already exists to update recency
            for existing_fav in FavoritesWindow.recent_favorites[:]:
                if existing_fav.attribute == attribute and existing_fav.value == value:
                    FavoritesWindow.recent_favorites.remove(existing_fav)
                    break
            FavoritesWindow.recent_favorites.insert(0, Favorite.from_attribute(attribute, value))
        else:
            for existing_fav in FavoritesWindow.recent_favorites[:]:
                if existing_fav.attribute == attribute and existing_fav.value == value:
                    FavoritesWindow.recent_favorites.remove(existing_fav)
                    break
        FavoritesWindow.store_favorites()

    @staticmethod
    def remove_favorite(favorite):
        if favorite in FavoritesWindow.recent_favorites:
            FavoritesWindow.recent_favorites.remove(favorite)
            FavoritesWindow.store_favorites()
            return True
        return False

    @staticmethod
    def is_track_favorited(track):
        """
        Check if a track matches any existing favorites.
        Returns True if the track's title matches a TITLE favorite,
        or if any of its attributes match an attribute favorite.
        """
        if not track:
            return False
            
        for favorite in FavoritesWindow.recent_favorites:
            if favorite.attribute == TrackAttribute.TITLE:
                if track.searchable_title and favorite.value_lower in track.searchable_title:
                    return True
            elif favorite.attribute == TrackAttribute.ARTIST:
                if track.searchable_artist and favorite.value_lower in track.searchable_artist:
                    return True
            elif favorite.attribute == TrackAttribute.ALBUM:
                if track.searchable_album and favorite.value_lower in track.searchable_album:
                    return True
            elif favorite.attribute == TrackAttribute.COMPOSER:
                if track.searchable_composer and favorite.value_lower in track.searchable_composer:
                    return True
            elif favorite.attribute == TrackAttribute.GENRE:
                if track.searchable_genre and favorite.value_lower in track.searchable_genre:
                    return True
            elif favorite.attribute == TrackAttribute.INSTRUMENT:
                if track.get_instrument() and favorite.value_lower in track.get_instrument().lower():
                    return True
            elif favorite.attribute == TrackAttribute.FORM:
                if track.get_form() and favorite.value_lower in track.get_form().lower():
                    return True
        return False

    @staticmethod
    def add_favorite(favorite, is_new=False, app_actions=None, from_favorite_window=True):
        """Static method to add a favorite to the list.
        
        Args:
            favorite: The Favorite object to add
            is_new: Whether this is a new favorite
            app_actions: AppActions instance for showing alerts/toasts
            
        Returns:
            bool: True if the favorite was added successfully or was unchanged, False otherwise
        """
        assert app_actions is not None
        if is_new:
            # Check if favorite already exists
            for existing_fav in FavoritesWindow.recent_favorites:
                if existing_fav.attribute == favorite.attribute and existing_fav.value == favorite.value:
                    app_actions.alert(_("Favorite Exists"), 
                                    _("This favorite already exists."))
                    return False
        else:
            # For existing favorites, only check for duplicates if the value has changed
            for existing_fav in FavoritesWindow.recent_favorites:
                if existing_fav.attribute == favorite.attribute and existing_fav.value == favorite.value:
                    if id(existing_fav) != id(favorite):
                        # Only throw an error if the favorite details have changed but run into a collision
                        app_actions.alert(_("Favorite Exists"), 
                                        _("This favorite already exists."))
                        return False
                    if not from_favorite_window:
                        app_actions.alert(_("Favorite Exists"), 
                                        _("This favorite already exists."))
                    return True # Nothing to do, same favorite object
            try:
                FavoritesWindow.recent_favorites.remove(favorite)
            except ValueError:
                pass

        # Add the new favorite or re-insert at the top
        FavoritesWindow.recent_favorites.insert(0, favorite)
        FavoritesWindow.store_favorites()
        app_actions.toast(_("Favorite updated successfully."))
        return True

    def __init__(self, master, app_actions, library_data, dimensions="600x600"):
        FavoritesWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        FavoritesWindow.top_level.geometry(dimensions)
        FavoritesWindow.set_title(_("Favorites"))
        self.master = FavoritesWindow.top_level
        self.master.resizable(True, True)
        self.app_actions = app_actions
        self.library_data = library_data
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

        # Add attribute selection for creating new favorites
        self._attribute_label = Label(self.inner_frame)
        self.add_label(self._attribute_label, _("Create Favorite From Current Track"), row=0)
        
        self.attribute_var = StringVar(self.inner_frame)
        self.attribute_var.set(TrackAttribute.TITLE.value)  # Default to TITLE
        self.attribute_menu = OptionMenu(self.inner_frame, self.attribute_var, 
                                       *[attr.value for attr in TrackAttribute])
        self.attribute_menu.grid(row=0, column=1)
        
        self.create_favorite_btn = Button(self.inner_frame, text=_("Create Favorite"),
                                        command=self.create_favorite_from_current)
        self.create_favorite_btn.grid(row=0, column=2)

        self._favorite_label = Label(self.inner_frame)
        self.add_label(self._favorite_label, _("Search Favorites"), row=1)
        self.favorite = StringVar(self.inner_frame)
        self.favorite_entry = Entry(self.inner_frame, textvariable=self.favorite)
        self.favorite_entry.grid(row=1, column=1)
        self.favorite_entry.bind("<Return>", self.do_search)

        self.favorite_list = []
        self.open_details_btn_list = []
        self.search_btn_list = []

        self.search_btn = None
        self.add_btn("search_btn", _("Search"), self.do_search, row=2)

        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        Utils.start_thread(self.show_recent_favorites, use_asyncio=False)

    def create_favorite_from_current(self):
        """Open FavoriteWindow to create a new favorite from the current track's selected attribute"""
        current_track = self.app_actions.get_current_track()
        if not current_track:
            return

        selected_attribute = TrackAttribute(self.attribute_var.get())
        value = None

        # Get the value based on the selected attribute
        if selected_attribute == TrackAttribute.TITLE:
            value = current_track.title or current_track.filepath
        elif selected_attribute == TrackAttribute.ARTIST:
            value = current_track.artist
        elif selected_attribute == TrackAttribute.ALBUM:
            value = current_track.album
        elif selected_attribute == TrackAttribute.COMPOSER:
            value = current_track.composer
        elif selected_attribute == TrackAttribute.GENRE:
            value = current_track.genre
        elif selected_attribute == TrackAttribute.INSTRUMENT:
            value = current_track.get_instrument()
        elif selected_attribute == TrackAttribute.FORM:
            value = current_track.get_form()

        # Open FavoriteWindow with the attribute and value
        if FavoritesWindow.details_window is not None:
            FavoritesWindow.details_window.master.destroy()
        FavoritesWindow.details_window = FavoriteWindow(
            FavoritesWindow.top_level, 
            self, 
            Favorite.from_attribute(selected_attribute, value),
            self.library_data,
            is_new=True
        )

    def create_favorite(self, favorite, is_new=False):
        """Create a new favorite or update an existing one"""
        if FavoritesWindow.add_favorite(favorite, is_new, self.app_actions):
            self._refresh_widgets()
            return True
        return False

    def show_recent_favorites(self):
        if len(FavoritesWindow.recent_favorites) == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No favorites found."), row=1, column=1)
            self.favorite_list.append(self.searching_label)
            self.master.update()
            return

        for i in range(len(FavoritesWindow.recent_favorites)):
            row = i + 1
            favorite = FavoritesWindow.recent_favorites[i]
            if favorite is None:
                continue

            # Get display text based on favorite type
            if favorite.attribute == TrackAttribute.TITLE:
                # Try to find the track using our safe wrapper
                # This wrapper handles both filepath and metadata-based lookups,
                # and updates the favorite's filepath if found by metadata
                track = self._get_track_for_favorite(favorite)
                if not track:
                    # Track not found - show as stranded
                    display_text = f"{favorite.value} ({_('File not found')})"
                else:
                    # Handle empty/whitespace values
                    title = track.title.strip() if track.title else ""
                    filepath = track.filepath.strip() if track.filepath else ""
                    # Utils.log(f"Track display values - title: '{title}', filepath: '{filepath}'")
                    display_text = title or filepath or _("No title or filepath available")
            else:
                display_text = f"{favorite.attribute.value}: {favorite.value}"

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, display_text, row=row, column=1, wraplength=200)
            self.favorite_list.append(title_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=2)
            def open_detail_handler(event, self=self, favorite=favorite):
                self.open_details(favorite)
            open_details_btn.bind("<Button-1>", open_detail_handler)

            remove_btn = Button(self.results_frame.viewPort, text=_("Remove"))
            self.open_details_btn_list.append(remove_btn)
            remove_btn.grid(row=row, column=3)
            def remove_handler(event, self=self, favorite=favorite):
                if FavoritesWindow.remove_favorite(favorite):
                    self._refresh_widgets()
            remove_btn.bind("<Button-1>", remove_handler)

        self.master.update()

    def _find_track_by_metadata(self, favorite: Favorite):
        """
        Try to find a track by matching its metadata with the favorite's metadata.
        Returns the first matching track found, or None if no match is found.
        """
        if favorite.attribute != TrackAttribute.TITLE:
            return None

        # Get all tracks from the library
        tracks = self.library_data.get_all_tracks()
        
        # Try to find a track with matching metadata
        for track in tracks:
            if (favorite.value == (track.title or track.filepath) and
                (not favorite.artist or favorite.artist == track.artist) and
                (not favorite.album or favorite.album == track.album) and
                (not favorite.composer or favorite.composer == track.composer)):
                return track
        return None

    def _get_track_for_favorite(self, favorite: Favorite):
        """
        Safely get a track for a favorite, handling both filepath and title-based lookups.
        Returns the track if found, None if not found.
        """
        if not favorite.filepath:
            # If no filepath, try to find by metadata
            track = self._find_track_by_metadata(favorite)
            if track:
                # Update favorite with new filepath
                if favorite.update_from_track(track):
                    FavoritesWindow.store_favorites()
                    Utils.log(f"Updated favorite for track {favorite.value} with new filepath: {track.filepath}")
            return track
            
        # Try to get track by filepath
        track = self.library_data.get_track(favorite.filepath)
        
        # Verify the track is valid by checking if it has a title or filepath
        if track and (track.title or track.filepath):
            return track
            
        # If track is invalid, try to find by metadata
        track = self._find_track_by_metadata(favorite)
        if track:
            # Update favorite with new filepath
            if favorite.update_from_track(track):
                FavoritesWindow.store_favorites()
                Utils.log(f"Updated favorite for track {favorite.value} with new filepath: {track.filepath}")
        return track

    def do_search(self, event=None):
        favorite = self.favorite.get().strip()
        self.favorite_data_search = FavoritesDataSearch(favorite, FavoritesWindow.MAX_RESULTS)
        self._do_search()

    def _do_search(self, event=None):
        assert self.favorite_data_search is not None
        self._refresh_widgets(add_results=False)
        
        # Filter favorites based on search criteria
        for favorite in FavoritesWindow.recent_favorites:
            # Get searchable text based on favorite type
            if favorite.attribute == TrackAttribute.TITLE:
                # Try to find the track using our safe wrapper
                # This wrapper handles both filepath and metadata-based lookups,
                # and updates the favorite's filepath if found by metadata
                track = self._get_track_for_favorite(favorite)
                if not track:
                    Utils.log_red(f"Track not found for favorite {favorite.value}")
                    continue
                search_text = favorite.value
            else:
                search_text = favorite.value

            self.favorite_data_search.add_result(favorite, search_text)
        
        self.favorite_data_search.sort_results()
        self._refresh_widgets()

    def add_widgets_for_results(self):
        assert self.favorite_data_search is not None
        results = self.favorite_data_search.get_results()
        Utils.log(f"Found {len(results)} results")
        for i in range(len(results)):
            row = i + 1
            favorite = results[i]

            # Get display text based on favorite type
            if favorite.attribute == TrackAttribute.TITLE:
                # Try to find the track using our safe wrapper
                # This wrapper handles both filepath and metadata-based lookups,
                # and updates the favorite's filepath if found by metadata
                track = self._get_track_for_favorite(favorite)
                if not track:
                    # Track not found - show as stranded
                    display_text = f"{favorite.value} ({_('File not found')})"
                else:
                    # Handle empty/whitespace values
                    title = track.title.strip() if track.title else ""
                    filepath = track.filepath.strip() if track.filepath else ""
                    Utils.log(f"Track display values - title: '{title}', filepath: '{filepath}'")
                    display_text = title or filepath or _("No title or filepath available")
            else:
                display_text = f"{favorite.attribute.value}: {favorite.value}"

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, display_text, row=row, column=0)
            self.favorite_list.append(title_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=1)
            def open_detail_handler(event, self=self, favorite=favorite):
                self.open_details(favorite)
            open_details_btn.bind("<Button-1>", open_detail_handler)

            remove_btn = Button(self.results_frame.viewPort, text=_("Remove"))
            self.open_details_btn_list.append(remove_btn)
            remove_btn.grid(row=row, column=2)
            def remove_handler(event, self=self, favorite=favorite):
                if FavoritesWindow.remove_favorite(favorite):
                    self._refresh_widgets()
            remove_btn.bind("<Button-1>", remove_handler)

    def open_details(self, favorite):
        if FavoritesWindow.details_window is not None:
            FavoritesWindow.details_window.master.destroy()
        FavoritesWindow.details_window = FavoriteWindow(FavoritesWindow.top_level, self, favorite, self.library_data)

    def refresh(self):
        self._refresh_widgets()

    def _refresh_widgets(self, add_results=True):
        self.clear_widget_lists()
        if add_results:
            if self.favorite_data_search is not None and self.favorite_data_search.favorite:
                self.add_widgets_for_results()
            else:
                self.show_recent_favorites()
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


class FavoriteWindow:
    """
    Window to view and edit a specific favorite.
    """
    def __init__(self, master, favorites_window, favorite, library_data, is_new=False):
        self.master = Toplevel(master, bg=AppStyle.BG_COLOR)
        self.master.geometry("400x300")
        self.master.title(_("Favorite Details"))
        self.favorites_window = favorites_window
        self.favorite = favorite
        self.library_data = library_data
        self.is_new = is_new

        self.outer_frame = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.outer_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Display favorite details
        self._create_details_frame()

        # Add action buttons
        self._create_buttons_frame()

        self.master.bind("<Escape>", self.close)
        self.master.protocol("WM_DELETE_WINDOW", self.close)

    def _create_details_frame(self):
        details_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR)
        details_frame.pack(fill="x", pady=(0, 10))

        # Get track if this is a track favorite
        track = None
        if self.favorite.attribute == TrackAttribute.TITLE:
            # Try to find the track by metadata
            for t in self.library_data.get_all_tracks():
                if (self.favorite.value == (t.title or t.filepath) and
                    (not self.favorite.artist or self.favorite.artist == t.artist) and
                    (not self.favorite.album or self.favorite.album == t.album) and
                    (not self.favorite.composer or self.favorite.composer == t.composer)):
                    track = t
                    break

        # Create labels for favorite details
        if track:
            # Track favorite details
            Label(details_frame, text=_("Type: Track"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(anchor="w")
            Label(details_frame, text=f"{_('Title')}: {track.title or track.filepath}", 
                  bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(anchor="w")
            Label(details_frame, text=f"{_('File')}: {track.filepath}", 
                  bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(anchor="w")
        else:
            # Attribute favorite details
            Label(details_frame, text=f"{_('Type')}: {self.favorite.attribute.value}", 
                  bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(anchor="w")
            Label(details_frame, text=f"{_('Value')}: {self.favorite.value}", 
                  bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(anchor="w")

        # Add timestamp
        from datetime import datetime
        timestamp = datetime.fromtimestamp(self.favorite.timestamp)
        Label(details_frame, text=f"{_('Added')}: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}", 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(anchor="w")

    def _create_buttons_frame(self):
        buttons_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR)
        buttons_frame.pack(fill="x", pady=(10, 0))

        # Confirm button for both new and existing favorites
        confirm_btn = Button(buttons_frame, 
                           text=_("Create Favorite") if self.is_new else _("Update Favorite"),
                           command=self._confirm_favorite)
        confirm_btn.pack(side="left", padx=5)

        if not self.is_new:
            # Remove button only for existing favorites
            remove_btn = Button(buttons_frame, text=_("Remove Favorite"), 
                              command=self._remove_favorite)
            remove_btn.pack(side="left", padx=5)

        # Close button
        close_btn = Button(buttons_frame, text=_("Close"), 
                          command=self.close)
        close_btn.pack(side="right", padx=5)

    def _confirm_favorite(self):
        if self.favorites_window.create_favorite(self.favorite, is_new=self.is_new):
            self.close()

    def _remove_favorite(self):
        if FavoritesWindow.remove_favorite(self.favorite):
            self.favorites_window.refresh()
        self.close()

    def close(self, event=None):
        self.master.destroy()

