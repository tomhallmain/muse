import time

from tkinter import Toplevel, Frame, Label, Checkbutton, BooleanVar, StringVar, LEFT, W, messagebox
import tkinter.font as fnt
from tkinter.ttk import Button, Entry

from lib.tk_scroll_demo import ScrollFrame
from library_data.composer import Composer, ComposersDataSearch, ComposersData
from ui.app_style import AppStyle
from ui.auth.password_utils import require_password
# from ui.base_window import BaseWindow
from utils.app_info_cache import app_info_cache
from utils.globals import ProtectedActions
from utils.logging_setup import get_logger
from utils.translations import I18N
from utils.utils import Utils

logger = get_logger(__name__)

_ = I18N._



class ComposerDetailsWindow():
    '''
    Window to show composer details.
    '''
    top_level = None
    COL_0_WIDTH = 600

    def __init__(self, master, composers_window, composer=None, dimensions="600x600"):
        # super().__init__()
        ComposerDetailsWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR)
        ComposerDetailsWindow.top_level.geometry(dimensions)
        self.master = ComposerDetailsWindow.top_level
        self.composers_window = composers_window
        self.app_actions = composers_window.app_actions
        self.composer = composer if composer is not None else Composer(None, None)
        self.is_new = composer is None
        ComposerDetailsWindow.top_level.title(_("New Composer") if self.is_new else _("Modify Composer: {0}").format(self.composer.name))

        self.frame = Frame(self.master)
        self.frame.grid(column=0, row=0)
        self.frame.columnconfigure(0, weight=9)
        self.frame.columnconfigure(1, weight=1)
        self.frame.columnconfigure(2, weight=1)
        self.frame.columnconfigure(3, weight=1)
        self.frame.columnconfigure(4, weight=1)

        self._label_info = Label(self.frame)
        self.add_label(self._label_info, _("Modify Composer"), row=0, wraplength=ComposerDetailsWindow.COL_0_WIDTH)

        self._label_composer = Label(self.frame)
        self.add_label(self._label_composer, _("Name"), row=1, wraplength=ComposerDetailsWindow.COL_0_WIDTH)
        self.new_composer_name = StringVar(self.master, value=_("New Composer") if composer is None else composer.name)
        self.new_composer_name_entry = Entry(self.frame, textvariable=self.new_composer_name, width=50, font=fnt.Font(size=8))
        self.new_composer_name_entry.grid(column=1, row=1, sticky="w")

        self._label_indicators = Label(self.frame)
        self.add_label(self._label_indicators, _("Indicators"), row=2, wraplength=ComposerDetailsWindow.COL_0_WIDTH)
        self.indicators = StringVar(self.master, value="" if composer is None else ":".join(composer.indicators))
        self.indicators_entry = Entry(self.frame, textvariable=self.indicators, width=50, font=fnt.Font(size=8))
        self.indicators_entry.grid(column=1, row=2, sticky="w")

        self._label_start_date = Label(self.frame)
        self.add_label(self._label_start_date, _("Start Date"), row=3, wraplength=ComposerDetailsWindow.COL_0_WIDTH)
        self.start_date = StringVar(self.master, value="" if composer is None else str(composer.start_date))
        self.start_date_entry = Entry(self.frame, textvariable=self.start_date, width=50, font=fnt.Font(size=8))
        self.start_date_entry.grid(column=1, row=3, sticky="w")

        self._label_end_date = Label(self.frame)
        self.add_label(self._label_end_date, _("End Date"), row=4, wraplength=ComposerDetailsWindow.COL_0_WIDTH)
        self.end_date = StringVar(self.master, value="" if composer is None else str(composer.end_date))
        self.end_date_entry = Entry(self.frame, textvariable=self.end_date, width=50, font=fnt.Font(size=8))
        self.end_date_entry.grid(column=1, row=4, sticky="w")

        self._label_dates_are_lifespan = Label(self.frame)
        self.add_label(self._label_dates_are_lifespan, _("Dates are lifespan"), row=5, wraplength=ComposerDetailsWindow.COL_0_WIDTH)
        self.dates_are_lifespan = BooleanVar(self.master, value=True if composer is None else composer.dates_are_lifespan)
        self.dates_are_lifespan_check = Checkbutton(self.frame, text=_("Dates are lifespan"), variable=self.dates_are_lifespan, font=fnt.Font(size=8))
        self.dates_are_lifespan_check.grid(column=1, row=5)

        self._label_dates_uncertain = Label(self.frame)
        self.add_label(self._label_dates_uncertain, _("Dates uncertain"), row=6, wraplength=ComposerDetailsWindow.COL_0_WIDTH)
        self.dates_uncertain = BooleanVar(self.master, value=True if composer is None else composer.dates_uncertain)
        self.dates_uncertain_check = Checkbutton(self.frame, text=_("Dates are uncertain"), variable=self.dates_uncertain, font=fnt.Font(size=8))
        self.dates_uncertain_check.grid(column=1, row=6)

        self._label_genres = Label(self.frame)
        self.add_label(self._label_genres, _("Genres"), row=7, wraplength=ComposerDetailsWindow.COL_0_WIDTH)
        self.genres = StringVar(self.master, value="" if composer is None else ":".join(composer.genres))
        self.genres_entry = Entry(self.frame, textvariable=self.genres, width=50, font=fnt.Font(size=8))
        self.genres_entry.grid(column=1, row=7)

        # self.works_label = Label(self.frame, text=_("Works:"))
        # self.works_label.grid(column=8, row=0)
        # TODO button to open search window with this composer searched

        # Add Notes section
        self._label_notes = Label(self.frame)
        self.add_label(self._label_notes, _("Notes"), row=8, wraplength=ComposerDetailsWindow.COL_0_WIDTH)
        self.add_note_btn = Button(self.frame, text=_("Add Note"), command=self.add_note)
        self.add_note_btn.grid(row=8, column=1, sticky="w")

        self.note_key_list = []
        self.note_key_widget_list = []
        self.note_value_list = []
        self.note_value_widget_list = []
        self.delete_task_btn_list = []
        self.move_down_btn_list = []

        self.add_widgets()

        self.add_composer_btn = None
        self.add_btn("add_composer_btn", _("Save"), self.finalize_composer, column=1)

        # Add delete button for existing composers
        if not self.is_new:
            self.delete_composer_btn = None
            self.add_btn("delete_composer_btn", _("Delete"), self.delete_composer, column=2)

        self.master.update()

    def add_widgets(self):
        row = 8

        for note_key, note_value in self.composer.notes.items():
            row += 1

            note_key_var = StringVar(self.master, value=str(note_key))
            self.note_key_list.append(note_key_var)
            note_key_entry = Entry(self.frame, textvariable=note_key_var, width=50, font=fnt.Font(size=8))
            note_key_entry.grid(column=0, row=row, sticky="w")
            self.note_key_widget_list.append(note_key_entry)
            note_value_var = StringVar(self.master, value=str(note_value))
            self.note_value_list.append(note_value_var)
            note_value_entry = Entry(self.frame, textvariable=note_value_var, width=50, font=fnt.Font(size=8))
            note_value_entry.grid(column=1, row=row, sticky="w")
            self.note_value_widget_list.append(note_value_entry)

            delete_btn = Button(self.frame, text=_("Delete"))
            self.delete_task_btn_list.append(delete_btn)
            delete_btn.grid(row=row, column=2)
            def delete_handler(event, self=self, key=note_key):
                self.composer.notes.pop(key)
                self.refresh()
            delete_btn.bind("<Button-1>", delete_handler)

            # move_down_btn = Button(self.frame, text=_("Move Down"))
            # self.move_down_btn_list.append(move_down_btn)
            # move_down_btn.grid(row=row, column=base_col+4)
            # def move_down_handler(event, self=self, idx=i):
            #     self.composer.move_index(idx, 1)
            #     self.refresh()
            # move_down_btn.bind("<Button-1>", move_down_handler)

    def add_note(self):
        self.composer.new_note(key=_("New note"))
        self.refresh()

    def refresh(self):
        self.clear_widget_lists()
        self.add_widgets()
        self.master.update()

    def clear_widget_lists(self):
        for wgt in self.note_key_widget_list:
            wgt.destroy()
        for wgt in self.note_value_widget_list:
            wgt.destroy()
        for btn in self.delete_task_btn_list:
            btn.destroy()
        for btn in self.move_down_btn_list:
            btn.destroy()
        self.note_key_list = []
        self.note_key_widget_list = []
        self.note_value_list = []
        self.note_value_widget_list = []
        self.delete_task_btn_list = []
        self.move_down_btn_list = []

    def apply_fixes(self, fixes={}):
        if fixes:
            if 'name' in fixes:
                self.new_composer_name.set(fixes['name'])
            if 'indicators' in fixes:
                self.indicators.set(":".join(fixes['indicators']))
            if 'start_date' in fixes:
                self.start_date.set(fixes['start_date'])
            if 'end_date' in fixes:
                self.end_date.set(fixes['end_date'])
            self.master.update()

    @require_password(ProtectedActions.EDIT_COMPOSERS)
    def finalize_composer(self, event=None):
        # Create a temporary composer with current UI values
        temp_composer = Composer(
            id=self.composer.id,
            name=self.new_composer_name.get(),
            indicators=[i.strip() for i in self.indicators.get().split(":") if i.strip()],
            start_date=int(self.start_date.get()) if self.start_date.get().strip() else -1,
            end_date=int(self.end_date.get()) if self.end_date.get().strip() else -1,
            dates_are_lifespan=self.dates_are_lifespan.get(),
            dates_uncertain=self.dates_uncertain.get(),
            genres=[g.strip() for g in self.genres.get().split(":") if g.strip()]
        )
        
        # Update notes from UI
        temp_composer.notes = {}
        for i in range(len(self.note_key_list)):
            key = self.note_key_list[i].get().strip()
            value = self.note_value_list[i].get().strip()
            if key:
                temp_composer.notes[key] = value

        # Validate composer data and apply fixes
        is_valid, error_message, fixes = temp_composer.validate()

        # Update UI with any fixes that were applied
        self.apply_fixes(fixes)

        if not is_valid:
            self.app_actions.alert(_("Validation Error"), error_message, type="warning")
            return

        # Check if there are any changes
        if not self.is_new and temp_composer.to_json() == self.composer.to_json():
            self.close_windows()
            return

        # Update the actual composer with the new values
        self.composer = temp_composer

        # Save the composer
        success, error_msg = self.composers_window.composers_data.save_composer(self.composer)
        if success:
            if fixes:
                self.app_actions.alert(_("Fixes applied"), "\n".join(fixes.values()), type="info")
                time.sleep(2)

            self.close_windows()
            
            # For new composers, search for them after saving
            if self.is_new:
                self.composers_window.composer.set(self.composer.name)
                self.composers_window.genre.set("")
                self.composers_window.do_search()
            else:
                self.composers_window._refresh_widgets()
        else:
            self.app_actions.alert(_("Error"), _("Failed to save composer:") + "\n\n" + error_msg, type="error")

    @require_password(ProtectedActions.EDIT_COMPOSERS)
    def delete_composer(self, event=None):
        """Delete the current composer after confirmation"""
        res = self.app_actions.alert(_("Delete composer"), 
                _("Are you sure you want to delete {0}? This action cannot be undone.").format(self.composer.name),
                kind="askokcancel")
        if res == messagebox.OK or res == True:
            # Delete the composer
            success, error_msg = self.composers_window.composers_data.delete_composer(self.composer)
            if success:
                self.close_windows()
                self.composers_window._refresh_widgets()
            else:
                self.app_actions.alert(_("Error"), _("Failed to delete composer:") + "\n\n" + error_msg, type="error")

    def close_windows(self, event=None):
        self.master.destroy()

    def add_label(self, label_ref, text, row=0, column=0, wraplength=500):
        label_ref['text'] = text
        label_ref.grid(column=column, row=row, sticky=W)
        label_ref.config(wraplength=wraplength, justify=LEFT, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)

    def add_btn(self, button_ref_name, text, command, row=0, column=0):
        if getattr(self, button_ref_name) is None:
            button = Button(master=self.frame, text=text, command=command)
            setattr(self, button_ref_name, button)
            button # for some reason this is necessary to maintain the reference?
            button.grid(row=row, column=column)


class ComposersWindow:
    '''
    Window to search composers data.
    '''
    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200
    details_window = None
    recent_searches = []

    @staticmethod
    def load_recent_searches():
        # NOTE be sure not to modify the key to "recent_searches" as this is shared with another key.
        json_searches = app_info_cache.get("recent_composer_searches", [])
        assert isinstance(json_searches, list)
        for search_details in json_searches:
            ComposersWindow.recent_searches.append(ComposersDataSearch(**search_details))

    @staticmethod
    def store_recent_searches():
        json_searches = []
        for search in ComposersWindow.recent_searches:
            if search.is_valid() and search.stored_results_count > 0:
                json_searches.append(search.get_dict())
        app_info_cache.set("recent_composer_searches", json_searches)


    def __init__(self, master, app_actions, dimensions="600x600"):

        ComposersWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        ComposersWindow.top_level.geometry(dimensions)
        ComposersWindow.set_title(_("Search Composers"))
        self.master = ComposersWindow.top_level
        self.master.resizable(True, True)
        self.app_actions = app_actions
        self.composers_data = ComposersData()
        self.composer_data_search = None
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

        # Add New Composer button
        self.new_composer_btn = Button(self.inner_frame, text=_("New Composer"), 
                                     command=self.new_composer)
        self.new_composer_btn.grid(row=0, column=2, padx=5)

        # Name search
        self._composer_label = Label(self.inner_frame)
        self.add_label(self._composer_label, _("Search Composer"), row=0)
        self.composer = StringVar(self.inner_frame)
        self.composer_entry = Entry(self.inner_frame, textvariable=self.composer)
        self.composer_entry.grid(row=0, column=1)
        self.composer_entry.bind("<Return>", self.do_search)

        # Genre search
        self._genre_label = Label(self.inner_frame)
        self.add_label(self._genre_label, _("Search Genre"), row=1)
        self.genre = StringVar(self.inner_frame)
        self.genre_entry = Entry(self.inner_frame, textvariable=self.genre)
        self.genre_entry.grid(row=1, column=1)
        self.genre_entry.bind("<Return>", self.do_search)

        # Start date range
        self._start_date_greater_label = Label(self.inner_frame)
        self.add_label(self._start_date_greater_label, _("Start Date After"), row=2)
        self.start_date_greater = StringVar(self.inner_frame)
        self.start_date_greater_entry = Entry(self.inner_frame, textvariable=self.start_date_greater)
        self.start_date_greater_entry.grid(row=2, column=1)
        self.start_date_greater_entry.bind("<Return>", self.do_search)

        self._start_date_less_label = Label(self.inner_frame)
        self.add_label(self._start_date_less_label, _("Start Date Before"), row=3)
        self.start_date_less = StringVar(self.inner_frame)
        self.start_date_less_entry = Entry(self.inner_frame, textvariable=self.start_date_less)
        self.start_date_less_entry.grid(row=3, column=1)
        self.start_date_less_entry.bind("<Return>", self.do_search)

        # End date range
        self._end_date_greater_label = Label(self.inner_frame)
        self.add_label(self._end_date_greater_label, _("End Date After"), row=4)
        self.end_date_greater = StringVar(self.inner_frame)
        self.end_date_greater_entry = Entry(self.inner_frame, textvariable=self.end_date_greater)
        self.end_date_greater_entry.grid(row=4, column=1)
        self.end_date_greater_entry.bind("<Return>", self.do_search)

        self._end_date_less_label = Label(self.inner_frame)
        self.add_label(self._end_date_less_label, _("End Date Before"), row=5)
        self.end_date_less = StringVar(self.inner_frame)
        self.end_date_less_entry = Entry(self.inner_frame, textvariable=self.end_date_less)
        self.end_date_less_entry.grid(row=5, column=1)
        self.end_date_less_entry.bind("<Return>", self.do_search)

        self.composer_list = []
        self.start_date_list = []
        self.end_date_list = []
        self.open_details_btn_list = []
        self.search_btn_list = []

        self.search_btn = None
        self.add_btn("search_btn", _("Search"), self.do_search, row=6)

        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        Utils.start_thread(self.show_recent_searches, use_asyncio=False)


    def show_recent_searches(self):
        if len(ComposersWindow.recent_searches) == 0:
            self.searching_label = Label(self.results_frame.viewPort)
            self.add_label(self.searching_label, text=_("No recent searches found."), row=0, column=1)
            self.composer_list.append(self.searching_label)
            self.master.update()
            return
        for i in range(len(ComposersWindow.recent_searches)):
            row = i + 1
            search = ComposersWindow.recent_searches[i]
            if search is None:
                continue

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, search.get_title(), row=row, column=1, wraplength=200)
            self.composer_list.append(title_label)

            album_label = Label(self.results_frame.viewPort)
            self.add_label(album_label, search.genre, row=row, column=2, wraplength=200)
            self.open_details_btn_list.append(album_label)

            results_count_label = Label(self.results_frame.viewPort)
            self.add_label(results_count_label, search.get_readable_stored_results_count(), row=row, column=3, wraplength=200)
            self.composer_list.append(results_count_label)

            search_btn = Button(self.results_frame.viewPort, text=_("Search"))
            self.search_btn_list.append(search_btn)
            search_btn.grid(row=row, column=4)
            def search_handler(event, self=self, search=search):
                self.load_stored_search(composer_data_search=search)
                self._do_search(event)
            search_btn.bind("<Button-1>", search_handler)

            # play_btn = Button(self.results_frame.viewPort, text=_("Play"))
            # self.play_btn_list.append(play_btn)
            # play_btn.grid(row=row, column=6)
            # def play_handler(event, self=self, search=search, track=track):
            #     self.load_stored_search(library_data_search=search)
            #     self._do_search(event)
            #     if track is None:
            #         logger.info("No specific track defined on search, using first available track.")
            #         track = search.get_first_available_track()
            #         if track is None:
            #             raise Exception("No tracks available on search.")
            #     elif track.is_invalid():
            #         raise Exception(f"Invalid track: {track}")
            #     self.run_play_callback(track)
            # play_btn.bind("<Button-1>", play_handler)
        self.master.update()

    def load_stored_search(self, composer_data_search):
        assert composer_data_search is not None
        self.composer.set(composer_data_search.composer)
        self.genre.set(composer_data_search.genre)
        self.start_date_greater.set(str(composer_data_search.start_date_greater_than) if composer_data_search.start_date_greater_than is not None else "")
        self.start_date_less.set(str(composer_data_search.start_date_less_than) if composer_data_search.start_date_less_than is not None else "")
        self.end_date_greater.set(str(composer_data_search.end_date_greater_than) if composer_data_search.end_date_greater_than is not None else "")
        self.end_date_less.set(str(composer_data_search.end_date_less_than) if composer_data_search.end_date_less_than is not None else "")
        self.composer_data_search = composer_data_search

    def do_search(self, event=None):
        composer = self.composer.get().strip()
        genre = self.genre.get().strip()
        
        # Parse date values
        start_date_greater = self._parse_date(self.start_date_greater.get().strip())
        start_date_less = self._parse_date(self.start_date_less.get().strip())
        end_date_greater = self._parse_date(self.end_date_greater.get().strip())
        end_date_less = self._parse_date(self.end_date_less.get().strip())
        
        # If search is empty or just whitespace, show recent searches
        if not any([composer, genre]):
            if sum([start_date_greater, start_date_less, end_date_greater, end_date_less]) == -4:
                self._refresh_widgets(add_results=False)
                self.show_recent_searches()
                return
            
        self.composer_data_search = ComposersDataSearch(
            composer=composer,
            genre=genre,
            max_results=ComposersWindow.MAX_RESULTS,
            start_date_greater_than=start_date_greater,
            start_date_less_than=start_date_less,
            end_date_greater_than=end_date_greater,
            end_date_less_than=end_date_less
        )
        self._do_search()

    def _parse_date(self, date_str):
        """Parse a date string into an integer year, or return -1 if invalid/empty."""
        if not date_str:
            return -1
        try:
            return int(date_str)
        except ValueError:
            return -1

    def _do_search(self, event=None):
        assert self.composer_data_search is not None
        self._refresh_widgets(add_results=False)
        self.composers_data.do_search(self.composer_data_search)
        if self.composer_data_search in ComposersWindow.recent_searches:
            ComposersWindow.recent_searches.remove(self.composer_data_search)
        ComposersWindow.recent_searches.insert(0, self.composer_data_search)
        self._refresh_widgets()

    def add_widgets_for_results(self):
        assert self.composer_data_search is not None
        results = self.composer_data_search.get_results()
        logger.info(f"Found {len(results)} results")
        for i in range(len(results)):
            row = i + 1
            composer = results[i]

            # Name column
            composer_label = Label(self.results_frame.viewPort)
            self.add_label(composer_label, composer.name, row=row, column=0)
            self.composer_list.append(composer_label)

            # Start date column
            start_date_label = Label(self.results_frame.viewPort)
            start_date_text = ""
            if composer.start_date is not None and composer.start_date != -1:
                start_date_text = str(composer.start_date)
            self.add_label(start_date_label, start_date_text, row=row, column=1)
            self.start_date_list.append(start_date_label)

            # End date column
            end_date_label = Label(self.results_frame.viewPort)
            end_date_text = ""
            if composer.end_date is not None and composer.end_date != -1:
                end_date_text = str(composer.end_date)
            self.add_label(end_date_label, end_date_text, row=row, column=2)
            self.end_date_list.append(end_date_label)

            # Details button column
            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=3)
            def open_detail_handler(event, self=self, composer=composer):
                self.open_details(composer)
            open_details_btn.bind("<Button-1>", open_detail_handler)

            open_details_btn = None
            self.add_btn("search_btn", _("Search"), self.do_search, row=0)

    @require_password(ProtectedActions.EDIT_COMPOSERS)
    def open_details(self, composer):
        if ComposersWindow.details_window is not None:
            ComposersWindow.details_window.master.destroy()
        ComposersWindow.details_window = ComposerDetailsWindow(ComposersWindow.top_level, self, composer)

    @require_password(ProtectedActions.EDIT_COMPOSERS)
    def new_composer(self):
        """Open the composer details window to create a new composer"""
        if ComposersWindow.details_window is not None:
            ComposersWindow.details_window.master.destroy()
        ComposersWindow.details_window = ComposerDetailsWindow(ComposersWindow.top_level, self, None)

    def refresh(self):
        pass

    def _refresh_widgets(self, add_results=True):
        self.clear_widget_lists()
        if add_results:
            self.add_widgets_for_results()
        self.master.update()

    def clear_widget_lists(self):
        for label in self.composer_list:
            label.destroy()
        for label in self.start_date_list:
            label.destroy()
        for label in self.end_date_list:
            label.destroy()
        for btn in self.open_details_btn_list:
            btn.destroy()
        for btn in self.search_btn_list:
            btn.destroy()
        self.composer_list = []
        self.start_date_list = []
        self.end_date_list = []
        self.open_details_btn_list = []
        self.search_btn_list = []

    @staticmethod
    def set_title(extra_text):
        ComposersWindow.top_level.title(_("Composer Search") + " - " + extra_text)

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
