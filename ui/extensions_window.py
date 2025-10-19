from datetime import datetime
import os

from tkinter import Toplevel, Label, StringVar, Frame, messagebox
from tkinter.ttk import Button, OptionMenu

from extensions.extension_manager import ExtensionManager
from extensions.library_extender import q20, q23
from lib.tk_scroll_demo import ScrollFrame
from library_data.library_data import LibraryDataSearch
from ui.app_style import AppStyle
from ui.auth.password_utils import require_password
from ui.base_window import BaseWindow
# from utils.config import config
from utils.globals import ExtensionStrategy, ProtectedActions
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)

class ExtensionsWindow(BaseWindow):
    '''
    Window to display and manage extension history.
    '''
    CURRENT_EXTENSION_TEXT = _("Extensions")
    COL_0_WIDTH = 150
    MAX_EXTENSIONS = 100
    top_level = None

    def __init__(self, master, app_actions, library_data):
        super().__init__()
        
        # Create and configure top level window
        ExtensionsWindow.top_level = Toplevel(master)
        ExtensionsWindow.top_level.title(_("Extensions"))
        ExtensionsWindow.top_level.geometry("1400x800")
        ExtensionsWindow.top_level.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.master = ExtensionsWindow.top_level
        self.app_actions = app_actions
        self.library_data = library_data

        # Main container
        self.main = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.main.columnconfigure(0, weight=1)
        self.main.columnconfigure(1, weight=3)  # Give more weight to the content area
        self.main.grid(column=0, row=0, sticky='nsew')

        # Sidebar
        self.sidebar = Frame(self.main, bg=AppStyle.BG_COLOR)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.grid(column=0, row=0, sticky='nsew', padx=5, pady=5)

        # Content area with ScrollFrame
        self.content = Frame(self.main, bg=AppStyle.BG_COLOR)
        self.content.columnconfigure(0, weight=1)
        self.content.grid(column=1, row=0, sticky='nsew', padx=5, pady=5)

        # Initialize UI components
        self._init_sidebar()
        self._init_extension_list()
        self._refresh_extension_list()

        self.master.update()

    def _init_sidebar(self):
        """Initialize the sidebar with configuration options."""
        current_row = 0

        # Title
        Label(self.sidebar, text=_("Extension Settings"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, columnspan=2, sticky='ew', pady=5)
        current_row += 1

        # Status section
        Label(self.sidebar, text=_("Thread Status"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, columnspan=2, sticky='ew', pady=5)
        current_row += 1
        
        self.status_label = Label(self.sidebar, text=_("Click Check Status to see thread state"),
                                 bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=150)
        self.status_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        # Status check button
        check_status_btn = Button(self.sidebar, text=_("Check Status"), 
                                 command=self._check_thread_status)
        check_status_btn.grid(row=current_row, column=0, columnspan=2, pady=5)
        current_row += 1

        # Strategy selection
        Label(self.sidebar, text=_("Strategy"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', pady=2)
        self.strategy_var = StringVar(value=ExtensionManager.strategy.get_translation())
        strategy_menu = OptionMenu(self.sidebar, self.strategy_var, ExtensionManager.strategy.get_translation(),
                                 *ExtensionStrategy.get_translated_names(),
                                 command=self._on_strategy_change)
        strategy_menu.grid(row=current_row, column=1, sticky='ew', pady=2)
        current_row += 1

        # Clear button
        clear_btn = Button(self.sidebar, text=_("Clear History"), 
                          command=self._clear_history)
        clear_btn.grid(row=current_row, column=0, columnspan=2, pady=10)
        current_row += 1

        # Stats
        Label(self.sidebar, text=_("Statistics"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, columnspan=2, sticky='ew', pady=5)
        current_row += 1

        self.total_extensions_label = Label(self.sidebar, 
                                          bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.total_extensions_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

        self.avg_duration_label = Label(self.sidebar, 
                                      bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        self.avg_duration_label.grid(row=current_row, column=0, columnspan=2, sticky='w', pady=2)
        current_row += 1

    def _init_extension_list(self):
        """Initialize the extension list view using ScrollFrame."""
        # Create outer frame for ScrollFrame
        self.outer_frame = Frame(self.content, bg=AppStyle.BG_COLOR)
        self.outer_frame.grid_rowconfigure(0, weight=1)
        self.outer_frame.grid_columnconfigure(0, weight=1)
        self.outer_frame.grid(row=0, column=0, sticky="nsew")

        # Create ScrollFrame for the extension list
        self.scroll_frame = ScrollFrame(self.outer_frame, bg_color=AppStyle.BG_COLOR, 
                                        width=1400, height=800)
        self.scroll_frame.grid(row=0, column=0, sticky="nsew")

        # Lists to maintain references to widgets
        self.date_labels = []
        self.published_labels = []
        self.title_labels = []
        self.duration_labels = []
        self.strategy_labels = []
        self.attribute_labels = []
        self.query_labels = []
        self.status_labels = []
        self.details_buttons = []
        self.delete_buttons = []
        self.play_buttons = []

        # Configure grid weights
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    def _refresh_extension_list(self):
        """Refresh the extension list with current data."""
        # Clear existing widgets
        for widget in self.scroll_frame.viewPort.winfo_children():
            widget.destroy()
        
        # Clear reference lists
        self.date_labels.clear()
        self.published_labels.clear()
        self.title_labels.clear()
        self.duration_labels.clear()
        self.strategy_labels.clear()
        self.attribute_labels.clear()
        self.query_labels.clear()
        self.status_labels.clear()
        self.details_buttons.clear()
        self.delete_buttons.clear()
        self.play_buttons.clear()

        # Header row
        header_bg = AppStyle.BG_COLOR
        header_fg = AppStyle.FG_COLOR
        
        Label(self.scroll_frame.viewPort, text=_('Date'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=0, sticky='w', padx=5, pady=2)
        Label(self.scroll_frame.viewPort, text=_('Published'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=1, sticky='w', padx=5, pady=2)
        Label(self.scroll_frame.viewPort, text=_('Title'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=2, sticky='w', padx=5, pady=2)
        Label(self.scroll_frame.viewPort, text=_('Duration'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=3, sticky='w', padx=5, pady=2)
        Label(self.scroll_frame.viewPort, text=_('Strategy'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=4, sticky='w', padx=5, pady=2)
        Label(self.scroll_frame.viewPort, text=_('Attribute'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=5, sticky='w', padx=5, pady=2)
        Label(self.scroll_frame.viewPort, text=_('Search Query'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=6, sticky='w', padx=5, pady=2)
        Label(self.scroll_frame.viewPort, text=_('Status'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=7, sticky='w', padx=5, pady=2)
        Label(self.scroll_frame.viewPort, text=_('Actions'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=8, columnspan=3, sticky='w', padx=5, pady=2)

        # Get recent extensions (most recent first, limited to 500)
        recent_extensions = sorted(
            ExtensionManager.extensions[-ExtensionsWindow.MAX_EXTENSIONS:],
            key=lambda x: x.get('date', ''),
            reverse=True
        )

        for i, ext in enumerate(recent_extensions):
            row = i + 1  # Start after header row
            
            duration = ext.get('duration', 0)
            duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else _("N/A")

            date_str = ""
            try:
                date_str = ext['date']
                if date_str:
                    date = datetime.fromisoformat(date_str)
                    date_str = date.strftime("%Y-%m-%d")
            except:
                pass

            published_date_str = ""
            try:
                published_date_str = ext['snippet']['publishTime']
                if published_date_str:
                    date = datetime.fromisoformat(published_date_str)
                    published_date_str = date.strftime("%Y-%m-%d")
            except:
                pass

            date_label = Label(self.scroll_frame.viewPort, text=date_str, 
                             bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=150)
            date_label.grid(row=row, column=0, sticky='w', padx=5, pady=2)
            self.date_labels.append(date_label)

            published_label = Label(self.scroll_frame.viewPort, text=published_date_str,
                             bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=150)
            published_label.grid(row=row, column=1, sticky='w', padx=5, pady=2)
            self.published_labels.append(published_label)

            title_label = Label(self.scroll_frame.viewPort, text=ext['snippet']['title'],
                              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=200)
            title_label.grid(row=row, column=2, sticky='w', padx=5, pady=2)
            self.title_labels.append(title_label)

            duration_label = Label(self.scroll_frame.viewPort, text=duration_str,
                                 bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
            duration_label.grid(row=row, column=3, sticky='w', padx=5, pady=2)
            self.duration_labels.append(duration_label)

            strategy_label = Label(self.scroll_frame.viewPort, text=ext.get('strategy', ''),
                                 bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
            strategy_label.grid(row=row, column=4, sticky='w', padx=5, pady=2)
            self.strategy_labels.append(strategy_label)

            attribute_label = Label(self.scroll_frame.viewPort, text=ext.get('track_attr', ''),
                                  bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
            attribute_label.grid(row=row, column=5, sticky='w', padx=5, pady=2)
            self.attribute_labels.append(attribute_label)

            query_label = Label(self.scroll_frame.viewPort, text=ext.get('search_query', ''),
                              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=300)
            query_label.grid(row=row, column=6, sticky='w', padx=5, pady=2)
            self.query_labels.append(query_label)

            # Status column - show X for failed extensions, blank for successful ones
            status_text = "X" if ext.get('failed', False) else ""
            status_label = Label(self.scroll_frame.viewPort, text=status_text,
                              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
            status_label.grid(row=row, column=7, sticky='w', padx=5, pady=2)
            self.status_labels.append(status_label)

            # Add Details button
            details_btn = Button(self.scroll_frame.viewPort, text=_("Details"))
            details_btn.grid(row=row, column=8, padx=2, pady=2)
            self.details_buttons.append(details_btn)
            def details_handler(event, self=self, extension=ext):
                self._show_extension_details(extension)
            details_btn.bind("<Button-1>", details_handler)

            # Add Play button
            play_btn = Button(self.scroll_frame.viewPort, text=_("Play"))
            play_btn.grid(row=row, column=9, padx=2, pady=2)
            self.play_buttons.append(play_btn)
            def play_handler(event, self=self, extension=ext):
                self._play_extension(extension)
            play_btn.bind("<Button-1>", play_handler)

            # Add Delete button
            delete_btn = Button(self.scroll_frame.viewPort, text=_("Delete"))
            delete_btn.grid(row=row, column=10, padx=2, pady=2)
            self.delete_buttons.append(delete_btn)
            def delete_handler(event, self=self, extension=ext):
                self._delete_extension(extension)
            delete_btn.bind("<Button-1>", delete_handler)

        self._update_statistics()

    def _update_statistics(self):
        """Update the statistics labels."""
        total = len(ExtensionManager.extensions)
        self.total_extensions_label.config(
            text=_("Total Extensions: {}").format(total))

        if total > 0:
            avg_duration = sum(ext.get('duration', 0) for ext in ExtensionManager.extensions) / total
            avg_duration_str = f"{int(avg_duration // 60)}:{int(avg_duration % 60):02d}"
            self.avg_duration_label.config(
                text=_("Average Duration: {}").format(avg_duration_str))
        else:
            self.avg_duration_label.config(text=_("Average Duration: N/A"))

    def _on_strategy_change(self, *args):
        """Handle strategy change."""
        try:
            # Convert from display value back to enum
            new_strategy = ExtensionStrategy.get_from_translation(self.strategy_var.get())
            ExtensionManager.strategy = new_strategy
            logger.info(f"Extension strategy changed to: {new_strategy.name}")
            ExtensionManager.store_extensions()
            self.library_data.extension_manager.reset_extension()
            self._refresh_extension_list()
        except Exception as e:
            logger.warning(f"Invalid strategy selected: {self.strategy_var.get()} - {e}")

    @require_password(ProtectedActions.EDIT_EXTENSIONS)
    def _clear_history(self):
        """Clear the extension history."""
        res = self.app_actions.alert(_("Confirm Clear"), 
                              _("Are you sure you want to clear all extension history?"),
                              kind="askokcancel")
        if res == messagebox.OK or res == True:
            ExtensionManager.extensions = []
            ExtensionManager.store_extensions()
            self._refresh_extension_list()

    def on_closing(self):
        """Handle window closing."""
        self.master.destroy()
        self.has_closed = True

    def update(self):
        """Update the window contents."""
        self._refresh_extension_list()

    @staticmethod
    def set_title(extra_text):
        """Set the window title."""
        ExtensionsWindow.top_level.title(_("Extensions") + " - " + extra_text)

    @require_password(ProtectedActions.EDIT_EXTENSIONS)
    def _show_extension_details(self, extension):
        """Show details for a specific extension."""
        ExtensionDetailsWindow(self.master, extension)

    @require_password(ProtectedActions.EDIT_EXTENSIONS)
    @require_password(ProtectedActions.DELETE_MEDIA)
    def _delete_extension(self, extension):
        """Delete a specific extension."""
        res = self.app_actions.alert(_("Confirm Delete"), 
                              _("Are you sure you want to delete this extension?"),
                              kind="askokcancel")
        if res == messagebox.OK or res == True:
            if extension in ExtensionManager.extensions:
                ExtensionManager.extensions.remove(extension)
                ExtensionManager.store_extensions()
                self._refresh_extension_list()

    def _play_extension(self, extension):
        """Attempt to play an extension by searching for its original file."""
        try:
            id = extension.get(q20, {}).get(q23, None)

            # Get the original filename without extension
            original_filename = os.path.splitext(os.path.basename(extension.get('filename', '')))[0]
            if not id or not original_filename:
                raise ValueError(_("No original filename or id found in extension data"))
                
            # Create a search query using the filename
            search = LibraryDataSearch(
                title=original_filename,  # Search in title field
                id=id,
                max_results=1  # We only need one match
            )
            
            # Call the search callback
            self.app_actions.search_and_play(search)
                
        except Exception as e:
            error_msg = str(e)
            if "No matching tracks found" in error_msg:
                error_msg += "\n\n" + _("Tip: If you've recently added or moved files, try checking 'Overwrite Cache' in the search options.")
            logger.error(f"Error playing extension: {error_msg}")
            self.app_actions.alert(_("Error"), error_msg, kind="error")

    def _check_thread_status(self):
        """Check and display the current status of the extension thread."""
        if ExtensionManager.extension_thread is None:
            status = _("No extension thread running")
        elif not ExtensionManager.extension_thread.is_alive():
            status = _("Extension thread terminated")
        else:
            status = _("Extension thread running")
            if ExtensionManager.EXTENSION_QUEUE.has_pending():
                status += _(" (with pending jobs)")
            if not ExtensionManager.extension_thread_delayed_complete:
                status += _(" (processing delayed operation)")
        
        self.status_label.config(text=status)
        self.master.update_idletasks()


class ExtensionDetailsWindow(BaseWindow):
    """Window to display detailed information about an extension."""
    def __init__(self, master, extension):
        super().__init__()
        
        # Create and configure top level window
        self.top_level = Toplevel(master)
        self.top_level.title(_("Extension Details"))
        self.top_level.geometry("800x600")
        self.top_level.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.master = self.top_level
        self.extension = extension

        # Main container
        self.main = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.main.columnconfigure(0, weight=1)
        self.main.grid(column=0, row=0, sticky='nsew', padx=10, pady=10)

        # Configure master grid weights
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

        # Title
        title = extension['snippet']['title']
        Label(self.main, text=title, 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR,
              font=('Helvetica', 12, 'bold')).grid(
                  row=0, column=0, sticky='w', pady=(0, 10))

        # Details frame
        details_frame = Frame(self.main, bg=AppStyle.BG_COLOR)
        details_frame.columnconfigure(1, weight=1)  # Give weight to the value column
        details_frame.grid(row=1, column=0, sticky='nsew', pady=5)

        # Configure main frame grid weights
        self.main.grid_rowconfigure(1, weight=1)  # Give weight to the details frame row

        # Add details in a grid layout
        current_row = 0
        
        Label(details_frame, text=_("Published:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', padx=5, pady=2)
        try:
            published_date = datetime.fromisoformat(extension['snippet']['publishTime'])
            published_str = published_date.strftime("%Y-%m-%d")
        except:
            published_str = _("N/A")
        Label(details_frame, text=published_str,
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)
        current_row += 1

        Label(details_frame, text=_("Duration:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', padx=5, pady=2)
        duration = extension.get('duration', 0)
        duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else _("N/A")
        Label(details_frame, text=duration_str,
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)
        current_row += 1

        Label(details_frame, text=_("Strategy:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', padx=5, pady=2)
        Label(details_frame, text=extension.get('strategy', ''),
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)
        current_row += 1

        Label(details_frame, text=_("Attribute:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', padx=5, pady=2)
        Label(details_frame, text=extension.get('track_attr', ''),
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)
        current_row += 1

        Label(details_frame, text=_("Search Query:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', padx=5, pady=2)
        Label(details_frame, text=extension.get('search_query', ''),
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=500).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)
        current_row += 1

        # Status field for failed/successful extensions
        Label(details_frame, text=_("Status:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', padx=5, pady=2)
        status_text = _("Failed") if extension.get('failed', False) else _("Success")
        Label(details_frame, text=status_text,
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)
        current_row += 1

        Label(details_frame, text=_("Description:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', padx=5, pady=2)
        Label(details_frame, text=extension['snippet'].get('description', ''),
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=500).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)
        current_row += 1

        Label(details_frame, text=_("File:"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', padx=5, pady=2)
        
        # Show filename or exception for failed extensions
        if extension.get('failed', False) and extension.get('exception'):
            file_text = extension.get('exception', '')
        else:
            file_text = extension.get('filename', '')
            
        Label(details_frame, text=file_text,
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=500).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)

        Button(self.main, text=_("Close"), command=self.on_closing).grid(row=2, column=0, pady=20)

        self.master.update()

    def on_closing(self):
        """Handle window closing."""
        self.master.destroy()
        self.has_closed = True

