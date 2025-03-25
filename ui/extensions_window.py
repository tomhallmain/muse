from enum import Enum
from datetime import datetime

from tkinter import Toplevel, Label, StringVar, LEFT, W, Frame, ttk, messagebox
from tkinter.ttk import Button, Entry, OptionMenu

from extensions.extension_manager import ExtensionManager
from lib.tk_scroll_demo import ScrollFrame
from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from utils.config import config
from utils.globals import ExtensionStrategy
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

class ExtensionsWindow(BaseWindow):
    '''
    Window to display and manage extension history.
    '''
    CURRENT_EXTENSION_TEXT = _("Extensions")
    COL_0_WIDTH = 150
    top_level = None

    def __init__(self, master, app_actions):
        super().init()
        
        # Create and configure top level window
        ExtensionsWindow.top_level = Toplevel(master)
        ExtensionsWindow.top_level.title(_("Extensions"))
        ExtensionsWindow.top_level.geometry("1000x800")
        ExtensionsWindow.top_level.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.master = ExtensionsWindow.top_level
        self.app_actions = app_actions

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

        # Strategy selection
        Label(self.sidebar, text=_("Strategy"), 
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(
                  row=current_row, column=0, sticky='w', pady=2)
        self.strategy_var = StringVar(value=ExtensionManager.strategy.name)
        strategy_menu = OptionMenu(self.sidebar, self.strategy_var, 
                                 *[s.name for s in ExtensionStrategy],
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
                                        width=1000, height=800)  # Set initial height
        self.scroll_frame.grid(row=0, column=0, sticky="nsew")

        # Lists to maintain references to widgets
        self.date_labels = []
        self.published_labels = []
        self.title_labels = []
        self.duration_labels = []
        self.strategy_labels = []
        self.attribute_labels = []
        self.query_labels = []
        self.details_buttons = []
        self.delete_buttons = []

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
        self.details_buttons.clear()
        self.delete_buttons.clear()

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
        Label(self.scroll_frame.viewPort, text=_('Actions'), 
              bg=header_bg, fg=header_fg).grid(row=0, column=7, columnspan=2, sticky='w', padx=5, pady=2)

        # Get recent extensions (last 100)
        recent_extensions = ExtensionManager.extensions[-100:]

        for i, ext in enumerate(recent_extensions):
            row = i + 1  # Start after header row
            
            duration = ext.get('duration', 0)
            duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else _("N/A")

            date_str = ""
            try:
                date_str = ext['date']
                if date_str:
                    date = datetime.fromisoformat(date_str)
                    date_str = date.strftime("%Y-%m-%d %H:%M")
            except:
                pass

            published_date_str = ""
            try:
                published_date_str = ext['snippet']['publishTime']
                if published_date_str:
                    date = datetime.fromisoformat(published_date_str)
                    published_date_str = date.strftime("%Y-%m-%d %H:%M")
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

            # Add Details button
            details_btn = Button(self.scroll_frame.viewPort, text=_("Details"))
            details_btn.grid(row=row, column=7, padx=2, pady=2)
            self.details_buttons.append(details_btn)
            def details_handler(event, self=self, extension=ext):
                self._show_extension_details(extension)
            details_btn.bind("<Button-1>", details_handler)

            # Add Delete button
            delete_btn = Button(self.scroll_frame.viewPort, text=_("Delete"))
            delete_btn.grid(row=row, column=8, padx=2, pady=2)
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
            new_strategy = ExtensionStrategy[self.strategy_var.get()]
            ExtensionManager.strategy = new_strategy
            Utils.log(f"Extension strategy changed to: {new_strategy.name}")
        except KeyError:
            Utils.log_yellow(f"Invalid strategy selected: {self.strategy_var.get()}")

    def _clear_history(self):
        """Clear the extension history."""
        if messagebox.askyesno(_("Confirm Clear"), 
                              _("Are you sure you want to clear all extension history?")):
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

    def _show_extension_details(self, extension):
        """Show details for a specific extension."""
        ExtensionDetailsWindow(self.master, extension)

    def _delete_extension(self, extension):
        """Delete a specific extension."""
        if messagebox.askyesno(_("Confirm Delete"), 
                              _("Are you sure you want to delete this extension?")):
            if extension in ExtensionManager.extensions:
                ExtensionManager.extensions.remove(extension)
                ExtensionManager.store_extensions()
                self._refresh_extension_list()


class ExtensionDetailsWindow(BaseWindow):
    """Window to display detailed information about an extension."""
    def __init__(self, master, extension):
        super().init()
        
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
            published_str = published_date.strftime("%Y-%m-%d %H:%M")
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
        Label(details_frame, text=extension.get('filename', ''),
              bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=500).grid(
                  row=current_row, column=1, sticky='w', padx=5, pady=2)

        Button(self.main, text=_("Close"), command=self.on_closing).grid(row=2, column=0, pady=20)

        self.master.update()

    def on_closing(self):
        """Handle window closing."""
        self.master.destroy()
        self.has_closed = True

