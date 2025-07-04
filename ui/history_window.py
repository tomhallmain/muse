from tkinter import Toplevel, Frame, Label, StringVar, LEFT, RIGHT, W, Entry
from tkinter.ttk import Button, OptionMenu

from utils.globals import HistoryType, ProtectedActions
from ui.auth.password_utils import require_password
from lib.tk_scroll_demo import ScrollFrame
from muse.playlist import Playlist
from ui.app_style import AppStyle
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._

logger = get_logger(__name__)

class HistoryDataSearch:
    def __init__(self, search_term="", max_results=200):
        self.search_term = search_term.lower()
        self.max_results = max_results
        self.results = []

    def is_valid(self):
        return len(self.search_term.strip()) > 0

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
        if not self.search_term:
            return 0
            
        search_text = search_text.lower()
        
        # Tier 1: Match at start of string
        if search_text.startswith(self.search_term):
            return 3
            
        # Tier 2: Match at start of word
        words = search_text.split()
        for word in words:
            if word.startswith(self.search_term):
                return 2
                
        # Tier 3: Contains match
        if self.search_term in search_text:
            return 1
            
        return 0

    def add_result(self, item, search_text: str):
        """Add a result with its priority level."""
        priority = self._get_match_priority(search_text)
        if priority > 0:
            self.results.append((priority, item))

    def sort_results(self):
        """Sort results by priority (highest first) and limit to max_results."""
        # Sort by priority (descending) and then by the item itself
        self.results.sort(key=lambda x: (-x[0], x[1]))
        # Extract just the items, maintaining the sorted order
        self.results = [item for _, item in self.results[:self.max_results]]


class HistoryWindow:
    '''
    Window to view playback history data.
    '''
    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200

    def __init__(self, master, app_actions, library_data, dimensions="600x600"):
        logger.info(f"Opening HistoryWindow with dimensions {dimensions}")
        HistoryWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        HistoryWindow.top_level.geometry(dimensions)
        HistoryWindow.set_title(_("History"))
        self.master = HistoryWindow.top_level
        self.master.resizable(True, True)
        self.app_actions = app_actions
        self.library_data = library_data
        self.history_data_search = None

        self.outer_frame = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.outer_frame.rowconfigure(0, weight=1)
        self.outer_frame.rowconfigure(1, weight=8)
        self.outer_frame.grid(row=0, column=0)

        self.inner_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR)
        self.inner_frame.columnconfigure(0, weight=1)
        self.inner_frame.columnconfigure(1, weight=1)
        self.inner_frame.grid(row=0, column=0, sticky="nsew")

        self.results_frame = ScrollFrame(self.outer_frame, bg_color=AppStyle.BG_COLOR, width=600)
        self.results_frame.grid(row=1, column=0, sticky="nsew")

        # Add history type selection
        self._history_type_label = Label(self.inner_frame)
        self.add_label(self._history_type_label, _("History Type"), row=0)
        
        # Create dropdown for history types using translated names
        self.history_type_var = StringVar(self.inner_frame)
        self.history_type_var.set(HistoryType.TRACKS.get_translation())  # Default value
        self.history_type_menu = OptionMenu(self.inner_frame, self.history_type_var,
                                          *HistoryType.get_translated_names(),
                                          command=self.show_history)
        self.history_type_menu.grid(row=0, column=1)

        # Add search entry
        self._search_label = Label(self.inner_frame)
        self.add_label(self._search_label, _("Search History"), row=1)
        self.search_term = StringVar(self.inner_frame)
        self.search_entry = Entry(self.inner_frame, textvariable=self.search_term)
        self.search_entry.grid(row=1, column=1)
        self.search_entry.bind("<Return>", self.do_search)

        self.search_btn = None
        self.add_btn("search_btn", _("Search"), self.do_search, row=2)

        self.master.bind("<Escape>", self.close_window)
        self.master.protocol("WM_DELETE_WINDOW", self.close_window)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        
        # Show tracks history by default
        self.show_history(HistoryType.TRACKS.get_translation())

    @require_password(ProtectedActions.VIEW_HISTORY)
    def do_search(self, event=None):
        search_term = self.search_term.get().strip()
        self.history_data_search = HistoryDataSearch(search_term, HistoryWindow.MAX_RESULTS)
        self._do_search()

    @require_password(ProtectedActions.VIEW_HISTORY)
    def _do_search(self, event=None):
        assert self.history_data_search is not None
        self._refresh_widgets(add_results=False)
        
        # Get the current history type
        history_type = HistoryType.get_from_translation(self.history_type_var.get())
        
        # Get the appropriate history list based on type
        history_list = getattr(Playlist, history_type.value)
        
        # Filter history based on search criteria
        for item in history_list:
            # Get searchable text based on history type
            if history_type == HistoryType.TRACKS:
                track = self.library_data.get_track(item)
                if track:
                    search_text = f"{track.title} - {track.artist}"
                else:
                    search_text = item
            else:
                search_text = item

            self.history_data_search.add_result(item, search_text)
        
        self.history_data_search.sort_results()
        self._refresh_widgets()

    def show_history(self, history_type_translation):
        """Show history for the specified type"""
        logger.info(f"Showing history for type: {history_type_translation}")
        self.clear_widgets()
        
        # Convert the translated name back to the enum value
        history_type = HistoryType.get_from_translation(history_type_translation)
        
        # Get the appropriate history list based on type
        history_list = getattr(Playlist, history_type.value)
        logger.info(f"Found {len(history_list)} items in history")

        if not history_list:
            logger.info("No history items found")
            self.add_label(Label(self.results_frame.viewPort), 
                         _("No history found."), row=1, column=1)
            return

        # Display history items
        for i, item in enumerate(history_list[:HistoryWindow.MAX_RESULTS]):
            row = i + 1
            if history_type == HistoryType.TRACKS:
                # For tracks, try to get the track details
                track = self.library_data.get_track(item)
                if track:
                    display_text = f"{track.title} - {track.artist}"
                else:
                    display_text = item
                    logger.info(f"Could not find track details for: {item}")
            else:
                display_text = item

            # Create a frame for each item to hold the label and buttons
            item_frame = Frame(self.results_frame.viewPort, bg=AppStyle.BG_COLOR)
            item_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=2)

            # Add the item label
            label = Label(item_frame, text=display_text, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=200)
            label.pack(side=LEFT, padx=5)

            # Add favorite button
            favorite_btn = Button(item_frame, text="★", 
                                command=lambda v=item, t=history_type: self.add_favorite(v, t))
            favorite_btn.pack(side=RIGHT, padx=5)

            # Add track details button for tracks
            if history_type == HistoryType.TRACKS and track:
                details_btn = Button(item_frame, text=_("Details"),
                                   command=lambda t=track: self.app_actions.open_track_details(t))
                details_btn.pack(side=RIGHT, padx=5)

    @require_password(ProtectedActions.EDIT_FAVORITES)
    def add_favorite(self, value: str, history_type: HistoryType):
        """Add the selected item to favorites."""
        from library_data.favorite import Favorite
        favorite = Favorite.from_attribute(history_type.get_track_attribute(), value)
        self.app_actions.add_favorite(favorite)

    def clear_widgets(self):
        """Clear all widgets from the results frame"""
        for widget in self.results_frame.viewPort.winfo_children():
            widget.destroy()

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

    def _refresh_widgets(self, add_results=True):
        self.clear_widgets()
        if add_results:
            if self.history_data_search is not None and self.history_data_search.search_term:
                self.add_widgets_for_results()
            else:
                self.show_history(self.history_type_var.get())
        self.master.update()

    def add_widgets_for_results(self):
        assert self.history_data_search is not None
        results = self.history_data_search.get_results()
        for i in range(len(results[:HistoryWindow.MAX_RESULTS])):
            row = i + 1
            item = results[i]

            # Get the current history type
            history_type = HistoryType.get_from_translation(self.history_type_var.get())
            
            # Get display text based on history type
            if history_type == HistoryType.TRACKS:
                track = self.library_data.get_track(item)
                if track:
                    display_text = f"{track.title} - {track.artist}"
                else:
                    display_text = item
            else:
                display_text = item

            # Create a frame for each item to hold the label and buttons
            item_frame = Frame(self.results_frame.viewPort, bg=AppStyle.BG_COLOR)
            item_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=2)

            # Add the item label
            label = Label(item_frame, text=display_text, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=200)
            label.pack(side=LEFT, padx=5)

            # Add favorite button
            favorite_btn = Button(item_frame, text="★", 
                                command=lambda v=item, t=history_type: self.add_favorite(v, t))
            favorite_btn.pack(side=RIGHT, padx=5)

            # Add track details button for tracks
            if history_type == HistoryType.TRACKS and track:
                details_btn = Button(item_frame, text=_("Details"),
                                   command=lambda t=track: self.app_actions.open_track_details(t))
                details_btn.pack(side=RIGHT, padx=5)

    def close_window(self, event=None):
        self.master.destroy()

    @staticmethod
    def set_title(extra_text):
        HistoryWindow.top_level.title(_("History") + " - " + extra_text) 
