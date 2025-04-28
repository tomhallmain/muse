from tkinter import Toplevel, Frame, Label, StringVar, LEFT, RIGHT, W
from tkinter.ttk import Button, OptionMenu

from utils.globals import HistoryType

from lib.tk_scroll_demo import ScrollFrame
from muse.playlist import Playlist
from ui.app_style import AppStyle
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class HistoryWindow:
    '''
    Window to view playback history data.
    '''
    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200

    def __init__(self, master, app_actions, library_data, dimensions="600x600"):
        Utils.log(f"Opening HistoryWindow with dimensions {dimensions}")
        HistoryWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        HistoryWindow.top_level.geometry(dimensions)
        HistoryWindow.set_title(_("History"))
        self.master = HistoryWindow.top_level
        self.master.resizable(True, True)
        self.app_actions = app_actions
        self.library_data = library_data

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

        self.master.bind("<Escape>", self.close_window)
        self.master.protocol("WM_DELETE_WINDOW", self.close_window)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        
        # Show tracks history by default
        self.show_history(HistoryType.TRACKS.get_translation())

    def show_history(self, history_type_translation):
        """Show history for the specified type"""
        Utils.log(f"Showing history for type: {history_type_translation}")
        self.clear_widgets()
        
        # Convert the translated name back to the enum value
        history_type = HistoryType.get_from_translation(history_type_translation)
        
        # Get the appropriate history list based on type
        history_list = getattr(Playlist, history_type.value)
        Utils.log(f"Found {len(history_list)} items in history")

        if not history_list:
            Utils.log("No history items found")
            self.add_label(Label(self.results_frame.viewPort), 
                         _("No history found."), row=1, column=1)
            return

        # Display history items
        for i, item in enumerate(history_list):
            row = i + 1
            if history_type == HistoryType.TRACKS:
                # For tracks, try to get the track details
                track = self.library_data.get_track(item)
                if track:
                    display_text = f"{track.title} - {track.artist}"
                    Utils.log(f"Found track details: {display_text}")
                else:
                    display_text = item
                    Utils.log(f"Could not find track details for: {item}")
            else:
                display_text = item

            # Create a frame for each item to hold the label and buttons
            item_frame = Frame(self.results_frame.viewPort, bg=AppStyle.BG_COLOR)
            item_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=2)

            # Add the item label
            label = Label(item_frame, text=display_text, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=200)
            label.pack(side=LEFT, padx=5)

            # Add favorite button
            favorite_btn = Button(item_frame, text=_("★"), 
                                command=lambda v=item, t=history_type: self.add_favorite(v, t))
            favorite_btn.pack(side=RIGHT, padx=5)

            # Add track details button for tracks
            if history_type == HistoryType.TRACKS and track:
                details_btn = Button(item_frame, text=_("Details"),
                                   command=lambda t=track: self.app_actions.open_track_details(t))
                details_btn.pack(side=RIGHT, padx=5)

    def add_favorite(self, value: str, history_type: HistoryType):
        """Add the selected item to favorites."""
        self.app_actions.add_favorite(value, history_type.get_track_attribute())

    def clear_widgets(self):
        """Clear all widgets from the results frame"""
        for widget in self.results_frame.viewPort.winfo_children():
            widget.destroy()

    def add_label(self, label_ref, text, row=0, column=0, wraplength=500):
        label_ref['text'] = text
        label_ref.grid(column=column, row=row, sticky=W)
        label_ref.config(wraplength=wraplength, justify=LEFT, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)

    def close_window(self, event=None):
        self.master.destroy()

    @staticmethod
    def set_title(extra_text):
        HistoryWindow.top_level.title(_("History") + " - " + extra_text) 