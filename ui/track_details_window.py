from tkinter import Toplevel, Label, StringVar, LEFT, W, Text, BOTH, END, messagebox
from tkinter.ttk import Button, Entry, Frame, Scrollbar

from extensions.open_weather import OpenWeatherAPI
from lib.tk_scroll_demo import ScrollFrame
from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils
import os

_ = I18N._

class ScrollableText(Frame):
    def __init__(self, master, height=4, width=40, **kwargs):
        super().__init__(master, **kwargs)
        self.text_widget = Text(self, height=height, width=width, wrap='word', bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.scrollbar = Scrollbar(self, orient='vertical', command=self.text_widget.yview)
        self.text_widget.configure(yscrollcommand=self.scrollbar.set)
        
        self.text_widget.pack(side='left', fill=BOTH, expand=True)
        self.scrollbar.pack(side='right', fill='y')

    def get(self):
        return self.text_widget.get('1.0', END).strip()

    def set(self, text):
        self.text_widget.delete('1.0', END)
        if text:
            self.text_widget.insert('1.0', text)

class TrackDetailsWindow(BaseWindow):
    '''
    Window to display and edit track metadata.
    '''
    AUDIO_TRACK = None
    COL_0_WIDTH = 150
    top_level = None

    def __init__(self, master, app_actions, audio_track, dimensions="800x800"):
        super().__init__()
        TrackDetailsWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR)
        TrackDetailsWindow.top_level.geometry(dimensions)
        TrackDetailsWindow.set_title(_("Track Details"))
        TrackDetailsWindow.AUDIO_TRACK = audio_track
        self.master = TrackDetailsWindow.top_level
        self.app_actions = app_actions
        self.open_weather_api = OpenWeatherAPI()

        self.has_closed = False
        self.frame = ScrollFrame(self.master, bg_color=AppStyle.BG_COLOR)
        self.frame.pack(side="top", fill="both", expand=True)

        # Create a grid of labels and inputs
        current_row = 0

        # Update button
        self.update_btn = None
        self.add_btn("update_btn", _("Update"), self.update_track_data, row=current_row)
        current_row += 1

        # Basic track information
        self.add_label_and_entry("title", _("Title"), audio_track.title, current_row)
        current_row += 1

        self.add_label_and_entry("album", _("Album"), audio_track.album, current_row)
        current_row += 1

        self.add_label_and_entry("artist", _("Artist"), audio_track.artist, current_row)
        current_row += 1

        self.add_label_and_entry("albumartist", _("Album Artist"), audio_track.albumartist, current_row)
        current_row += 1

        self.add_label_and_entry("composer", _("Composer"), audio_track.composer, current_row)
        current_row += 1

        self.add_label_and_entry("genre", _("Genre"), audio_track.genre, current_row)
        current_row += 1

        self.add_label_and_entry("year", _("Year"), str(audio_track.year) if audio_track.year else "", current_row)
        current_row += 1

        # Track numbers
        track_frame = Frame(self.frame.viewPort, style='Custom.TFrame')
        track_frame.grid(row=current_row, column=0, columnspan=2, sticky='ew', pady=5)
        
        Label(track_frame, text=_("Track Number"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side='left', padx=5)
        self.tracknumber = StringVar(value=str(audio_track.tracknumber) if audio_track.tracknumber > 0 else "")
        Entry(track_frame, textvariable=self.tracknumber, width=5).pack(side='left', padx=5)
        
        Label(track_frame, text=_("of"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side='left', padx=5)
        self.totaltracks = StringVar(value=str(audio_track.totaltracks) if audio_track.totaltracks > 0 else "")
        Entry(track_frame, textvariable=self.totaltracks, width=5).pack(side='left', padx=5)
        current_row += 1

        # Disc numbers
        disc_frame = Frame(self.frame.viewPort, style='Custom.TFrame')
        disc_frame.grid(row=current_row, column=0, columnspan=2, sticky='ew', pady=5)
        
        Label(disc_frame, text=_("Disc Number"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side='left', padx=5)
        self.discnumber = StringVar(value=str(audio_track.discnumber) if audio_track.discnumber > 0 else "")
        Entry(disc_frame, textvariable=self.discnumber, width=5).pack(side='left', padx=5)
        
        Label(disc_frame, text=_("of"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side='left', padx=5)
        self.totaldiscs = StringVar(value=str(audio_track.totaldiscs) if audio_track.totaldiscs > 0 else "")
        Entry(disc_frame, textvariable=self.totaldiscs, width=5).pack(side='left', padx=5)
        current_row += 1

        # Form and Instrument
        self.add_label_and_entry("form", _("Musical Form"), audio_track.get_form(), current_row)
        current_row += 1

        self.add_label_and_entry("instrument", _("Main Instrument"), audio_track.get_instrument(), current_row)
        current_row += 1

        # Scrollable text areas for longer content
        Label(self.frame.viewPort, text=_("Lyrics"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=current_row, column=0, sticky=W, padx=5, pady=5)
        self.lyrics = ScrollableText(self.frame.viewPort, height=6, width=50)
        self.lyrics.grid(row=current_row, column=1, sticky='ew', padx=5, pady=5)
        if hasattr(audio_track, 'lyrics'):
            self.lyrics.set(audio_track.lyrics)
        current_row += 1

        Label(self.frame.viewPort, text=_("Comments"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=current_row, column=0, sticky=W, padx=5, pady=5)
        self.comments = ScrollableText(self.frame.viewPort, height=6, width=50)
        self.comments.grid(row=current_row, column=1, sticky='ew', padx=5, pady=5)
        if hasattr(audio_track, 'comment'):
            self.comments.set(audio_track.comment)
        current_row += 1

        # File information (read-only)
        info_frame = Frame(self.frame.viewPort, style='Custom.TFrame')
        info_frame.grid(row=current_row, column=0, columnspan=2, sticky='ew', pady=10)
        
        duration = audio_track.get_track_length()
        if duration > 0:
            duration_text = f"{int(duration // 60)}:{int(duration % 60):02d}"
            Label(info_frame, text=_("Duration: ") + duration_text, 
                  bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side='left', padx=10)

        Label(info_frame, text=_("File: ") + os.path.basename(audio_track.filepath),
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side='left', padx=10)

        # Bindings
        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.frame.after(1, lambda: self.frame.focus_force())

    def add_label_and_entry(self, attr_name, label_text, initial_value, row):
        Label(self.frame.viewPort, text=label_text, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=row, column=0, sticky=W, padx=5, pady=5)
        setattr(self, attr_name, StringVar(self.frame.viewPort))
        getattr(self, attr_name).set(initial_value if initial_value else "")
        Entry(self.frame.viewPort, textvariable=getattr(self, attr_name)).grid(row=row, column=1, sticky='ew', padx=5, pady=5)

    def validate_numeric_field(self, value, field_name, allow_empty=True):
        """Validate numeric fields, allowing for empty values if specified."""
        if not value and allow_empty:
            return True, None
        try:
            num = int(value)
            if field_name == "year":
                if num < 0 or num > 9999:
                    return False, f"Year must be between 0 and 9999"
            elif "number" in field_name.lower():
                if num < 0:
                    return False, f"{field_name} cannot be negative"
            return True, num
        except ValueError:
            return False, f"{field_name} must be a valid number"

    def update_track_data(self):
        """Update the track with the modified metadata."""
        track = TrackDetailsWindow.AUDIO_TRACK
        
        # Prepare metadata dictionary
        metadata = {
            'title': self.title.get(),
            'album': self.album.get(),
            'artist': self.artist.get(),
            'albumartist': self.albumartist.get(),
            'composer': self.composer.get(),
            'genre': self.genre.get(),
            'lyrics': self.lyrics.get(),
            'comment': self.comments.get(),
            'form': self.form.get(),
            'instrument': self.instrument.get()
        }

        # Validate numeric fields
        numeric_fields = {
            'year': self.year.get(),
            'tracknumber': self.tracknumber.get(),
            'totaltracks': self.totaltracks.get(),
            'discnumber': self.discnumber.get(),
            'totaldiscs': self.totaldiscs.get()
        }

        validation_errors = []
        for field, value in numeric_fields.items():
            is_valid, result = self.validate_numeric_field(value, field)
            if not is_valid:
                validation_errors.append(result)
            else:
                metadata[field] = result

        if validation_errors:
            self.app_actions.alert(_("Validation Error"), "\n".join(validation_errors), kind="error")
            return

        # Attempt to update the metadata
        if track.update_metadata(metadata):
            self.app_actions.toast(_("Track details updated successfully"))
            self.set_title(track.title)
        else:
            self.app_actions.alert(_("Error"), _("Failed to update track details. Check the logs for more information."), kind="error")

    def close_windows(self, event=None):
        self.master.destroy()
        self.has_closed = True

    def add_btn(self, button_ref_name, text, command, row=0, column=0):
        if getattr(self, button_ref_name) is None:
            button = Button(master=self.frame.viewPort, text=text, command=command)
            setattr(self, button_ref_name, button)
            button.grid(row=row, column=column, columnspan=2, pady=10)

    @staticmethod
    def set_title(extra_text):
        TrackDetailsWindow.top_level.title(_("Track Details") + " - " + extra_text)

