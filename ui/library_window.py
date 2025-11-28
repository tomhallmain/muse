from tkinter import Label, StringVar, Frame, Entry
from tkinter.ttk import OptionMenu, Treeview, Scrollbar

from lib.multi_display import SmartToplevel
from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from utils.globals import TrackAttribute
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._

logger = get_logger(__name__)

class LibraryWindow(BaseWindow):
    '''
    Window to display and manage library statistics and browsing.
    '''
    CURRENT_LIBRARY_TEXT = _("Library")
    top_level = None

    def __init__(self, master, app_actions, library_data):
        super().__init__()
        
        # Create and configure top level window
        LibraryWindow.top_level = SmartToplevel(persistent_parent=master, title=_("Library"), geometry="1000x600")
        LibraryWindow.top_level.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.master = LibraryWindow.top_level
        self.app_actions = app_actions
        self.library_data = library_data

        # Configure grid weights for the window
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

        # Main container
        self.main = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.main.grid(column=0, row=0, sticky='nsew', padx=5, pady=5)
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_columnconfigure(1, weight=3)  # Give more weight to the content area

        # Sidebar
        self.sidebar = Frame(self.main, bg=AppStyle.BG_COLOR)
        self.sidebar.grid(column=0, row=0, sticky='nsew', padx=5, pady=5)
        self.sidebar.grid_columnconfigure(0, weight=1)

        # Content area
        self.content = Frame(self.main, bg=AppStyle.BG_COLOR)
        self.content.grid(column=1, row=0, sticky='nsew', padx=5, pady=5)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        # Initialize UI components
        self._init_sidebar()
        self._init_content()
        self._update_statistics()

        self.master.update()

    def _init_sidebar(self):
        """Initialize the sidebar with statistics."""
        current_row = 0

        # Title
        Label(self.sidebar, text=_("Library Statistics"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, columnspan=2, sticky='ew', pady=5)
        current_row += 1

        # Statistics labels
        self.total_tracks_label = Label(self.sidebar, 
                                      bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.total_tracks_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        self.total_albums_label = Label(self.sidebar, 
                                      bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.total_albums_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        self.total_artists_label = Label(self.sidebar, 
                                       bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.total_artists_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        self.total_composers_label = Label(self.sidebar, 
                                         bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.total_composers_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        self.total_instruments_label = Label(self.sidebar, 
                                           bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.total_instruments_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        self.total_forms_label = Label(self.sidebar, 
                                     bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.total_forms_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        # Cache information
        self.cache_update_label = Label(self.sidebar, 
                                      bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.cache_update_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        # Browse section
        Label(self.sidebar, text=_("Browse By"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, columnspan=2, sticky='ew', pady=5)
        current_row += 1

        # Attribute selection
        default_attribute = TrackAttribute.ARTIST.get_translation()
        self.attribute_var = StringVar(value=default_attribute)
        self.attribute_menu = OptionMenu(self.sidebar, self.attribute_var, default_attribute,
                                       *[attr.get_translation() for attr in TrackAttribute if attr != TrackAttribute.ARTIST],
                                       command=self._on_attribute_change)
        self.attribute_menu.grid(row=current_row, column=0, columnspan=2, sticky='ew', pady=2)
        current_row += 1

        # Search box
        Label(self.sidebar, text=_("Search:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', pady=2)
        current_row += 1

        self.search_var = StringVar()
        self.search_var.trace('w', self._on_search_change)
        search_entry = Entry(self.sidebar, textvariable=self.search_var)
        search_entry.grid(row=current_row, column=0, columnspan=2, sticky='ew', pady=2)
        current_row += 1

    def _init_content(self):
        """Initialize the content area with a treeview for browsing."""
        # Create treeview
        self.tree = Treeview(self.content, columns=('name', 'count'), show='headings')
        self.tree.heading('name', text=_('Name'))
        self.tree.heading('count', text=_('Count'))
        self.tree.column('name', width=300)
        self.tree.column('count', width=100)
        self.tree.grid(row=0, column=0, sticky='nsew')

        # Add scrollbar
        scrollbar = Scrollbar(self.content, orient='vertical', command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Configure grid weights
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    def _update_statistics(self):
        """Update the statistics labels."""
        # Get all tracks
        all_tracks = self.library_data.get_all_tracks()
        
        # Update labels
        self.total_tracks_label.config(
            text=_("Total Tracks: {}").format(len(all_tracks)))

        # Get unique albums
        albums = set()
        for track in all_tracks:
            if track.album:
                albums.add(track.album)
        self.total_albums_label.config(
            text=_("Total Albums: {}").format(len(albums)))

        # Get unique artists
        artists = set()
        for track in all_tracks:
            if track.artist:
                artists.add(track.artist)
        self.total_artists_label.config(
            text=_("Total Artists: {}").format(len(artists)))

        # Get unique composers
        composers = set()
        for track in all_tracks:
            if track.composer:
                composers.add(track.composer)
        self.total_composers_label.config(
            text=_("Total Composers: {}").format(len(composers)))

        # Get unique instruments
        instruments = set()
        for track in all_tracks:
            instrument = track.get_instrument()
            if instrument:
                instruments.add(instrument)
        self.total_instruments_label.config(
            text=_("Total Instruments: {}").format(len(instruments)))

        # Get unique forms
        forms = set()
        for track in all_tracks:
            form = track.get_form()
            if form:
                forms.add(form)
        self.total_forms_label.config(
            text=_("Total Forms: {}").format(len(forms)))

        # Update cache information
        cache_time = self.library_data.get_cache_update_time()
        if cache_time:
            cache_text = _("Cache Updated: {}").format(cache_time.strftime("%Y-%m-%d %H:%M"))
        else:
            cache_text = _("No Cache Available")
        self.cache_update_label.config(text=cache_text)

        # Update the treeview with the current attribute
        self._update_treeview()

    def _update_treeview(self):
        """Update the treeview with the current attribute's data."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Get the current attribute
        attr = TrackAttribute.get_from_translation(self.attribute_var.get())
        
        # Get all tracks
        all_tracks = self.library_data.get_all_tracks()
        
        # Count occurrences of each value
        counts = {}
        for track in all_tracks:
            if attr == TrackAttribute.TITLE:
                value = track.title
            elif attr == TrackAttribute.ALBUM:
                value = track.album
            elif attr == TrackAttribute.ARTIST:
                value = track.artist
            elif attr == TrackAttribute.COMPOSER:
                value = track.composer
            elif attr == TrackAttribute.GENRE:
                value = track.genre
            elif attr == TrackAttribute.FORM:
                value = track.get_form()
            elif attr == TrackAttribute.INSTRUMENT:
                value = track.get_instrument()
            
            if value:
                counts[value] = counts.get(value, 0) + 1

        # Filter by search term if any
        search_term = self.search_var.get().lower()
        if search_term:
            counts = {k: v for k, v in counts.items() if search_term in k.lower()}

        # Sort by count (descending) and then by name
        sorted_items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

        # Add to treeview
        for name, count in sorted_items:
            self.tree.insert('', 'end', values=(name, count))

    def _on_attribute_change(self, *args):
        """Handle attribute change."""
        self._update_treeview()

    def _on_search_change(self, *args):
        """Handle search term change."""
        self._update_treeview()

    def on_closing(self):
        """Handle window closing."""
        self.master.destroy()
        self.has_closed = True

    def update(self):
        """Update the window contents."""
        self._update_statistics() 