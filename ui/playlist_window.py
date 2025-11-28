from copy import deepcopy

from tkinter import Frame, Label, Text, StringVar, Scale, Listbox, Button, simpledialog, Entry, Checkbutton, BooleanVar
from tkinter.constants import W
from tkinter.ttk import OptionMenu, Scale

from lib.multi_display import SmartToplevel
from utils.globals import PlaylistSortType, PlaybackMasterStrategy

from muse.playback_config import PlaybackConfig
from muse.run_config import RunConfig
from ui.base_window import BaseWindow
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.translations import I18N

_ = I18N._

def set_attr_if_not_empty(text_box):
    current_value = text_box.get()
    if not current_value or current_value == "":
        return None
    return 

def set_tag(current_value, new_value):
    if current_value and (current_value.endswith("+") or current_value.endswith(",")):
        return current_value + new_value
    else:
        return new_value
    
def clear_quotes(s):
    if len(s) > 0:
        if s.startswith('"'):
            s = s[1:]
        if s.endswith('"'):
            s = s[:-1]
        if s.startswith("'"):
            s = s[1:]
        if s.endswith("'"):
            s = s[:-1]
    return s

class Sidebar(Frame):
    def __init__(self, master=None, cnf={}, **kw):
        Frame.__init__(self, master=master, cnf=cnf, **kw)


class ProgressListener:
    def __init__(self, update_func):
        self.update_func = update_func

    def update(self, context, percent_complete):
        self.update_func(context, percent_complete)


class MasterPlaylistWindow(BaseWindow):
    '''
    Main window for managing playlists using PlaybackMaster.
    '''
    named_playlist_configs = {}

    @staticmethod
    def load_named_playlist_configs():
        MasterPlaylistWindow.named_playlist_configs = app_info_cache.get('named_playlist_configs', {})

    @staticmethod
    def store_named_playlist_configs():
        app_info_cache.set('named_playlist_configs', MasterPlaylistWindow.named_playlist_configs)

    def __init__(self, master, app_actions, initial_configs=None, is_current_playlist=True):
        super().__init__(master)
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.app_actions = app_actions
        self.is_current_playlist = is_current_playlist
        
        # Load saved playlists
        MasterPlaylistWindow.load_named_playlist_configs()
        
        # Main container
        self.main = Frame(self.master)
        self.main.columnconfigure(0, weight=1)
        self.main.columnconfigure(1, weight=1)
        self.main.grid(column=0, row=0)
        
        # Available playlists section
        self.available_playlists_frame = Frame(self.main)
        self.available_playlists_frame.grid(column=0, row=0, sticky="nsew", padx=10, pady=10)
        
        self.label_available = Label(self.available_playlists_frame, text=_("Available Playlists"))
        self.label_available.grid(column=0, row=0, sticky="w", pady=(0, 10))
        
        self.available_playlists = Listbox(self.available_playlists_frame, width=40, height=15)
        self.available_playlists.grid(column=0, row=1, sticky="nsew")
        self.update_available_playlists()
        
        # Current playlist section
        self.current_playlist_frame = Frame(self.main)
        self.current_playlist_frame.grid(column=1, row=0, sticky="nsew", padx=10, pady=10)
        
        self.label_master = Label(self.current_playlist_frame, text=_("Current Playlist"))
        self.label_master.grid(column=0, row=0, sticky="w", pady=(0, 10))
        
        self.master_playlist = Listbox(self.current_playlist_frame, width=40, height=15)
        self.master_playlist.grid(column=0, row=1, sticky="nsew")
        
        # Playback config settings
        self.settings_frame = Frame(self.main)
        self.settings_frame.grid(column=0, row=1, columnspan=2, sticky="ew", padx=10, pady=10)
        
        # Tracks per config
        self.label_tracks = Label(self.settings_frame, text=_("Tracks per Config"))
        self.label_tracks.grid(column=0, row=0, sticky="w", padx=5)
        self.tracks_per_config = StringVar(value="2")
        self.entry_tracks = Entry(self.settings_frame, textvariable=self.tracks_per_config, width=5)
        self.entry_tracks.grid(column=1, row=0, sticky="w", padx=5)
        
        # Controls
        self.controls_frame = Frame(self.main)
        self.controls_frame.grid(column=0, row=2, columnspan=2, sticky="ew", pady=10)
        
        self.btn_add = Button(self.controls_frame, text=_("Add to Master"),
                            command=self.add_to_master)
        self.btn_add.grid(column=0, row=0, padx=5)
        
        self.btn_remove = Button(self.controls_frame, text=_("Remove from Master"),
                               command=self.remove_from_master)
        self.btn_remove.grid(column=1, row=0, padx=5)
        
        self.btn_new_playlist = Button(self.controls_frame, text=_("New Playlist"),
                                     command=self.open_new_playlist)
        self.btn_new_playlist.grid(column=2, row=0, padx=5)
        
        self.btn_save = Button(self.controls_frame, text=_("Save Master Playlist"),
                             command=self.save_master_playlist)
        self.btn_save.grid(column=3, row=0, padx=5)
        
        # Initialize data
        self.playback_master = PlaybackMaster(initial_configs or [])
        self.update_master_playlist_display()

    def update_available_playlists(self):
        """Update the list of available playlists."""
        self.available_playlists.delete(0, END)
        for name in MasterPlaylistWindow.named_playlist_configs.keys():
            self.available_playlists.insert(END, name)

    def update_master_playlist_display(self):
        """Update the display of the master playlist."""
        self.master_playlist.delete(0, END)
        for config in self.playback_master.playback_configs:
            self.master_playlist.insert(END, str(config))

    def add_to_master(self):
        """Add selected playlist to master playlist."""
        selection = self.available_playlists.curselection()
        if selection:
            playlist_name = self.available_playlists.get(selection[0])
            if playlist_name not in [str(config) for config in self.playback_master.playback_configs]:
                config = MasterPlaylistWindow.named_playlist_configs[playlist_name]
                playback_config = PlaybackConfig(
                    args=RunConfig(
                        playlist_sort_type=config['sort_type'],
                        directories=[]  # Will be populated from tracks
                    ),
                    data_callbacks=self.app_actions
                )
                playback_config.list = Playlist(
                    tracks=config['tracks'],
                    _type=config['sort_type'],
                    data_callbacks=self.app_actions
                )
                self.playback_master.playback_configs.append(playback_config)
                self.update_master_playlist_display()
                # Set the playback master strategy to PLAYLIST_CONFIG
                self.app_actions.set_playback_master_strategy(PlaybackMasterStrategy.PLAYLIST_CONFIG)

    def remove_from_master(self):
        """Remove selected playlist from master playlist."""
        selection = self.master_playlist.curselection()
        if selection:
            del self.playback_master.playback_configs[selection[0]]
            self.update_master_playlist_display()
            # If no playlists left, set strategy back to ALL_MUSIC
            if not self.playback_master.playback_configs:
                self.app_actions.set_playback_master_strategy(PlaybackMasterStrategy.ALL_MUSIC)

    def open_new_playlist(self):
        """Open the new playlist creation window."""
        new_window = SmartToplevel(persistent_parent=self.master)
        NewPlaylistWindow(new_window, self.app_actions, self)

    def set_playlist(self, playback_config):
        """Set the current playlist to a new config."""
        self.playback_master.playback_configs = [playback_config]
        self.update_master_playlist_display()
        # Set the playback master strategy to PLAYLIST_CONFIG
        self.app_actions.set_playback_master_strategy(PlaybackMasterStrategy.PLAYLIST_CONFIG)

    def add_playlist(self, playback_config):
        """Add a new playlist to the current master playlist."""
        self.playback_master.playback_configs.append(playback_config)
        self.update_master_playlist_display()
        # Set the playback master strategy to PLAYLIST_CONFIG
        self.app_actions.set_playback_master_strategy(PlaybackMasterStrategy.PLAYLIST_CONFIG)

    def save_master_playlist(self):
        """Save the master playlist configuration."""
        if self.playback_master.playback_configs:
            playlist_name = simpledialog.askstring(_("Save Master Playlist"),
                                                 _("Enter a name for this master playlist:"))
            if playlist_name:
                # Save master playlist config
                MasterPlaylistWindow.named_playlist_configs[playlist_name] = {
                    'configs': [{
                        'tracks': [track.filepath for track in config.list.sorted_tracks],
                        'sort_type': config.list.sort_type,
                        'config_type': config.type,
                        'tracks_per_play': int(self.tracks_per_config.get())
                    } for config in self.playback_master.playback_configs]
                }
                MasterPlaylistWindow.store_named_playlist_configs()
                
                messagebox.showinfo(_("Success"), _("Master playlist created successfully"))

    def on_closing(self):
        """Handle window closing."""
        # Save any changes to playlists
        MasterPlaylistWindow.store_named_playlist_configs()
        self.master.destroy()


class NewPlaylistWindow(BaseWindow):
    '''
    Window for creating new playlists and playback configs.
    '''
    def __init__(self, master, runner_app_config, current_master_window=None):
        super().__init__(master)
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.runner_app_config = runner_app_config
        self.current_master_window = current_master_window
        
        # Main container
        self.main = Frame(self.master)
        self.main.columnconfigure(0, weight=1)
        self.main.columnconfigure(1, weight=1)
        self.main.grid(column=0, row=0)
        
        # Playlist settings
        self.settings_frame = Frame(self.main)
        self.settings_frame.grid(column=0, row=0, sticky="nsew", padx=10, pady=10)
        
        # Playlist name
        self.label_name = Label(self.settings_frame, text=_("Playlist Name"))
        self.label_name.grid(column=0, row=0, sticky="w", pady=(0, 5))
        self.playlist_name = StringVar()
        self.entry_name = Entry(self.settings_frame, textvariable=self.playlist_name)
        self.entry_name.grid(column=0, row=1, sticky="ew", pady=(0, 10))
        
        # Sort type
        self.label_sort = Label(self.settings_frame, text=_("Sort Type"))
        self.label_sort.grid(column=0, row=2, sticky="w", pady=(0, 5))
        self.sort_type = StringVar()
        self.sort_type.set(PlaylistSortType.RANDOM.value)
        self.sort_menu = OptionMenu(self.settings_frame, self.sort_type,
                                  *[t.value for t in PlaylistSortType])
        self.sort_menu.grid(column=0, row=3, sticky="ew", pady=(0, 10))
        
        # Directory selection
        self.label_dir = Label(self.settings_frame, text=_("Directory"))
        self.label_dir.grid(column=0, row=4, sticky="w", pady=(0, 5))
        self.directory = StringVar()
        self.directory.set("ALL_MUSIC")
        directory_options = ["ALL_MUSIC"]
        directory_options.extend(list(config.get_subdirectories().values()))
        self.dir_menu = OptionMenu(self.settings_frame, self.directory, *directory_options)
        self.dir_menu.grid(column=0, row=5, sticky="ew", pady=(0, 10))
        
        # Playback config settings
        self.label_config = Label(self.settings_frame, text=_("Playback Config Settings"))
        self.label_config.grid(column=0, row=6, sticky="w", pady=(0, 5))
        
        # Dynamic volume
        self.enable_dynamic_volume = BooleanVar(value=True)
        self.check_dynamic_volume = Checkbutton(self.settings_frame, text=_("Enable Dynamic Volume"),
                                              variable=self.enable_dynamic_volume)
        self.check_dynamic_volume.grid(column=0, row=7, sticky="w", pady=(0, 5))
        
        # Long track splitting
        self.enable_long_track_splitting = BooleanVar(value=False)
        self.check_long_track = Checkbutton(self.settings_frame, text=_("Enable Long Track Splitting"),
                                          variable=self.enable_long_track_splitting)
        self.check_long_track.grid(column=0, row=8, sticky="w", pady=(0, 5))
        
        # Track splitting cutoff
        self.label_cutoff = Label(self.settings_frame, text=_("Track Splitting Cutoff (minutes)"))
        self.label_cutoff.grid(column=0, row=9, sticky="w", pady=(0, 5))
        self.cutoff_minutes = StringVar(value="20")
        self.entry_cutoff = Entry(self.settings_frame, textvariable=self.cutoff_minutes)
        self.entry_cutoff.grid(column=0, row=10, sticky="ew", pady=(0, 10))
        
        # Controls
        self.controls_frame = Frame(self.main)
        self.controls_frame.grid(column=0, row=1, sticky="ew", pady=10)
        
        self.btn_start = Button(self.controls_frame, text=_("Start Playlist"),
                              command=lambda: self.create_playlist("start"))
        self.btn_start.grid(column=0, row=0, padx=5)
        
        self.btn_add_current = Button(self.controls_frame, text=_("Add to Current Playlist"),
                                    command=lambda: self.create_playlist("add_current"))
        self.btn_add_current.grid(column=1, row=0, padx=5)
        
        self.btn_new_master = Button(self.controls_frame, text=_("Add to New Master Playlist"),
                                   command=lambda: self.create_playlist("new_master"))
        self.btn_new_master.grid(column=2, row=0, padx=5)
        
        self.btn_cancel = Button(self.controls_frame, text=_("Cancel"),
                               command=self.on_closing)
        self.btn_cancel.grid(column=3, row=0, padx=5)

    def create_playlist(self, action):
        """Create a new playlist and handle it according to the specified action."""
        name = self.playlist_name.get().strip()
        if not name:
            messagebox.showerror(_("Error"), _("Please enter a playlist name"))
            return
            
        # Get tracks from selected directory
        directories = []
        selection = self.directory.get()
        all_dirs = config.get_subdirectories()
        if selection == "ALL_MUSIC":
            directories = list(all_dirs.keys())
        else:
            for full_path, key in all_dirs.items():
                if key == selection:
                    directories.append(full_path)
                    break
        
        # Create RunConfig for PlaybackConfig
        run_config = RunConfig(
            playlist_sort_type=PlaylistSortType(self.sort_type.get()),
            directories=directories,
            enable_dynamic_volume=self.enable_dynamic_volume.get(),
            enable_long_track_splitting=self.enable_long_track_splitting.get(),
            long_track_splitting_time_cutoff_minutes=int(self.cutoff_minutes.get())
        )
        
        # Create PlaybackConfig
        playback_config = PlaybackConfig(
            args=run_config,
            data_callbacks=self.runner_app_config.data_callbacks
        )
        
        # Save playlist
        MasterPlaylistWindow.named_playlist_configs[name] = {
            'tracks': [track.filepath for track in playback_config.list.sorted_tracks],
            'sort_type': playback_config.list.sort_type,
            'config_type': playback_config.type
        }
        MasterPlaylistWindow.store_named_playlist_configs()
        
        # Handle the playlist based on the action
        if action == "start":
            if self.current_master_window:
                self.current_master_window.set_playlist(playback_config)
        elif action == "add_current":
            if self.current_master_window:
                self.current_master_window.add_playlist(playback_config)
        elif action == "new_master":
            new_window = SmartToplevel(persistent_parent=self.master)
            MasterPlaylistWindow(new_window, self.runner_app_config, [playback_config])
        
        messagebox.showinfo(_("Success"), _("Playlist created successfully"))
        self.on_closing()

    def on_closing(self):
        """Handle window closing."""
        self.master.destroy()


