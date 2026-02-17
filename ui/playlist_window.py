import os
from datetime import datetime
from tkinter import (
    Frame, Label, StringVar, IntVar, BooleanVar,
    Listbox, Spinbox, Checkbutton, Radiobutton,
    messagebox, simpledialog, END, BOTH, YES, W, SINGLE,
)
from tkinter.ttk import Button, Entry, OptionMenu

from lib.multi_display import SmartToplevel
from muse.named_playlist import NamedPlaylist, NamedPlaylistStore
from muse.playback_config import PlaybackConfig
from muse.playback_config_master import PlaybackConfigMaster
from muse.playback_state import PlaybackStateManager
from utils.globals import PlaylistSortType, PlaybackMasterStrategy
from utils.config import config
from utils.translations import I18N
from utils.logging_setup import get_logger

logger = get_logger(__name__)
_ = I18N._


class MasterPlaylistWindow:
    """Window for assembling a master playlist from named playlists.

    Left panel shows available NamedPlaylists (from NamedPlaylistStore).
    Right panel shows the current master playlist with per-entry weight /
    loop controls and reordering.
    Bottom shows an interspersed preview.
    """

    def __init__(self, master, app_actions, library_data=None):
        self.app_actions = app_actions
        self.library_data = library_data

        self.top = SmartToplevel(
            persistent_parent=master,
            title=_("Playlists"),
            geometry="820x620",
        )
        self.top.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._named_playlists = {}
        self._master_entries = []  # list of dicts: {name, named_playlist, weight, loop}

        self._build_ui()
        self._load_available()
        self._load_existing_master()
        self._refresh_master_list()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = Frame(self.top)
        outer.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        panels = Frame(outer)
        panels.pack(fill=BOTH, expand=YES)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=0)
        panels.columnconfigure(2, weight=1)

        # --- Left panel: available playlists ---
        left = Frame(panels)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        Label(left, text=_("Available Playlists")).grid(row=0, column=0, sticky=W)
        self._avail_listbox = Listbox(left, width=36, height=16, selectmode=SINGLE)
        self._avail_listbox.grid(row=1, column=0, sticky="nsew")

        avail_btns = Frame(left)
        avail_btns.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        Button(avail_btns, text=_("New Playlist"), command=self._open_new_playlist).pack(side="left", padx=(0, 5))
        Button(avail_btns, text=_("Freeze to Tracks"), command=self._freeze_to_tracks).pack(side="left", padx=(0, 5))
        Button(avail_btns, text=_("Delete"), command=self._delete_available).pack(side="left")

        # --- Centre: add/remove arrows ---
        centre = Frame(panels)
        centre.grid(row=0, column=1, padx=5)
        Button(centre, text=">>>", command=self._add_to_master).pack(pady=(40, 5))
        Button(centre, text="<<<", command=self._remove_from_master).pack()

        # --- Right panel: master playlist ---
        right = Frame(panels)
        right.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        Label(right, text=_("Master Playlist")).grid(row=0, column=0, sticky=W)
        self._master_listbox = Listbox(right, width=40, height=16, selectmode=SINGLE)
        self._master_listbox.grid(row=1, column=0, sticky="nsew")
        self._master_listbox.bind("<<ListboxSelect>>", self._on_master_select)

        # Per-entry controls
        ctrl = Frame(right)
        ctrl.grid(row=2, column=0, sticky="ew", pady=(5, 0))

        Label(ctrl, text=_("Weight:")).pack(side="left")
        self._weight_var = IntVar(value=1)
        self._weight_spin = Spinbox(ctrl, from_=1, to=99, width=4,
                                    textvariable=self._weight_var,
                                    command=self._on_weight_change)
        self._weight_spin.pack(side="left", padx=(0, 10))

        self._loop_var = BooleanVar(value=False)
        Checkbutton(ctrl, text=_("Loop"), variable=self._loop_var,
                    command=self._on_loop_change).pack(side="left", padx=(0, 10))

        Button(ctrl, text=_("Up"), command=self._move_up).pack(side="left", padx=(0, 2))
        Button(ctrl, text=_("Down"), command=self._move_down).pack(side="left")

        # --- Bottom: preview ---
        preview_frame = Frame(outer)
        preview_frame.pack(fill=BOTH, expand=False, pady=(10, 0))
        Label(preview_frame, text=_("Interspersed Preview")).pack(anchor=W)
        self._preview_listbox = Listbox(preview_frame, height=5)
        self._preview_listbox.pack(fill=BOTH, expand=False)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_available(self):
        self._named_playlists = NamedPlaylistStore.load_all()
        self._refresh_available_list()

    def _load_existing_master(self):
        """Populate master entries from existing PlaybackStateManager config."""
        master = PlaybackStateManager.get_master_config()
        if master and master.playback_configs:
            for i, pc in enumerate(master.playback_configs):
                weight = master.weights[i] if i < len(master.weights) else 1
                self._master_entries.append({
                    "name": str(pc),
                    "named_playlist": None,
                    "playback_config": pc,
                    "weight": weight,
                    "loop": pc.loop,
                })

    # ------------------------------------------------------------------
    # List refresh helpers
    # ------------------------------------------------------------------

    def _refresh_available_list(self):
        self._avail_listbox.delete(0, END)
        for name, np in self._named_playlists.items():
            self._avail_listbox.insert(END, f"{name}  ({np.get_source_description()})")

    def _refresh_master_list(self):
        self._master_listbox.delete(0, END)
        for entry in self._master_entries:
            loop_label = _("yes") if entry["loop"] else _("no")
            self._master_listbox.insert(
                END,
                f"{entry['name']}  [w:{entry['weight']}  loop:{loop_label}]"
            )
        self._update_preview()

    # ------------------------------------------------------------------
    # Available panel actions
    # ------------------------------------------------------------------

    def _open_new_playlist(self):
        NewPlaylistWindow(self.top, self.app_actions, self.library_data,
                          on_save=self._on_new_playlist_saved)

    def _on_new_playlist_saved(self):
        """Callback from NewPlaylistWindow after a playlist is saved."""
        self._load_available()

    def _freeze_to_tracks(self):
        """Convert a search/directory playlist to an explicit track list."""
        sel = self._avail_listbox.curselection()
        if not sel:
            return
        name = list(self._named_playlists.keys())[sel[0]]
        np = self._named_playlists[name]
        if not np.can_freeze():
            messagebox.showinfo(
                _("Freeze to Tracks"),
                _("This playlist is already track-based.")
            )
            return
        if self.library_data is None:
            messagebox.showerror(_("Error"), _("Library data not available."))
            return
        if not messagebox.askyesno(
            _("Freeze to Tracks"),
            _("Convert \"{0}\" to an explicit track list?\n\n"
              "This will resolve the current {1} source and replace it "
              "with a fixed list of tracks. This cannot be undone.").format(
                name, "search" if np.is_search_based() else "directory"
            )
        ):
            return
        try:
            count = np.freeze_to_tracks(self.library_data)
            NamedPlaylistStore.save(np)
            self._load_available()
            messagebox.showinfo(
                _("Freeze to Tracks"),
                _("Playlist \"{0}\" frozen to {1} tracks.").format(name, count)
            )
        except Exception as e:
            logger.error(f"Failed to freeze playlist '{name}': {e}")
            messagebox.showerror(_("Error"), str(e))

    def _delete_available(self):
        sel = self._avail_listbox.curselection()
        if not sel:
            return
        name = list(self._named_playlists.keys())[sel[0]]
        if messagebox.askyesno(_("Delete"), _("Delete playlist \"{0}\"?").format(name)):
            NamedPlaylistStore.delete(name)
            self._load_available()

    # ------------------------------------------------------------------
    # Master panel actions
    # ------------------------------------------------------------------

    def _add_to_master(self):
        sel = self._avail_listbox.curselection()
        if not sel:
            return
        name = list(self._named_playlists.keys())[sel[0]]
        np = self._named_playlists[name]

        try:
            pc = PlaybackConfig.from_named_playlist(
                np,
                data_callbacks=self.library_data.data_callbacks if self.library_data else None,
                library_data=self.library_data,
            )
        except Exception as e:
            logger.error(f"Failed to create PlaybackConfig from '{name}': {e}")
            messagebox.showerror(_("Error"), str(e))
            return

        self._master_entries.append({
            "name": name,
            "named_playlist": np,
            "playback_config": pc,
            "weight": 1,
            "loop": np.loop,
        })
        self._apply_master_change()

    def _remove_from_master(self):
        sel = self._master_listbox.curselection()
        if not sel:
            return
        del self._master_entries[sel[0]]
        self._apply_master_change()

    def _on_master_select(self, event=None):
        sel = self._master_listbox.curselection()
        if not sel:
            return
        entry = self._master_entries[sel[0]]
        self._weight_var.set(entry["weight"])
        self._loop_var.set(entry["loop"])

    def _on_weight_change(self):
        sel = self._master_listbox.curselection()
        if not sel:
            return
        try:
            w = int(self._weight_var.get())
        except (ValueError, TypeError):
            w = 1
        w = max(1, w)
        self._master_entries[sel[0]]["weight"] = w
        self._apply_master_change()

    def _on_loop_change(self):
        sel = self._master_listbox.curselection()
        if not sel:
            return
        loop_val = self._loop_var.get()
        self._master_entries[sel[0]]["loop"] = loop_val
        pc = self._master_entries[sel[0]].get("playback_config")
        if pc:
            pc.loop = loop_val
        self._apply_master_change()

    def _move_up(self):
        sel = self._master_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        idx = sel[0]
        self._master_entries[idx], self._master_entries[idx - 1] = \
            self._master_entries[idx - 1], self._master_entries[idx]
        self._apply_master_change()
        self._master_listbox.selection_set(idx - 1)

    def _move_down(self):
        sel = self._master_listbox.curselection()
        if not sel or sel[0] >= len(self._master_entries) - 1:
            return
        idx = sel[0]
        self._master_entries[idx], self._master_entries[idx + 1] = \
            self._master_entries[idx + 1], self._master_entries[idx]
        self._apply_master_change()
        self._master_listbox.selection_set(idx + 1)

    # ------------------------------------------------------------------
    # Master config rebuild + strategy activation (3.9)
    # ------------------------------------------------------------------

    def _apply_master_change(self):
        """Rebuild PlaybackConfigMaster from entries, update state, refresh UI."""
        self._refresh_master_list()

        if self._master_entries:
            configs = [e["playback_config"] for e in self._master_entries]
            weights = [e["weight"] for e in self._master_entries]
            master = PlaybackConfigMaster(configs, weights)
            PlaybackStateManager.set_master_config(master)
            try:
                self.app_actions.set_playback_master_strategy(
                    PlaybackMasterStrategy.PLAYLIST_CONFIG
                )
            except (AttributeError, TypeError):
                pass
        else:
            PlaybackStateManager.clear_master_config()
            try:
                self.app_actions.set_playback_master_strategy(
                    PlaybackMasterStrategy.ALL_MUSIC
                )
            except (AttributeError, TypeError):
                pass

    # ------------------------------------------------------------------
    # Preview (3.8)
    # ------------------------------------------------------------------

    def _update_preview(self, max_tracks: int = 15):
        """Show the first N track slots in weighted round-robin order."""
        self._preview_listbox.delete(0, END)
        if not self._master_entries:
            return

        names = [e["name"] for e in self._master_entries]
        weights = [e["weight"] for e in self._master_entries]

        preview_names = []
        cursor = 0
        counter = 0
        for _ in range(max_tracks):
            for _attempt in range(len(names)):
                if counter >= weights[cursor]:
                    cursor = (cursor + 1) % len(names)
                    counter = 0
                break
            preview_names.append(names[cursor])
            counter += 1
            if counter >= weights[cursor]:
                cursor = (cursor + 1) % len(names)
                counter = 0

        for i, n in enumerate(preview_names):
            self._preview_listbox.insert(END, f"  {i + 1}. {n}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_closing(self):
        self.top.destroy()


class NewPlaylistWindow:
    """Window for creating / editing a NamedPlaylist.

    Supports three source modes:
    - Directory: pick from configured library directories.
    - Search Query: enter search fields (re-resolved at play time).
    - Explicit Tracks: add individual tracks via search, reorder manually.
    """

    def __init__(self, master, app_actions, library_data=None, on_save=None):
        self.app_actions = app_actions
        self.library_data = library_data
        self._on_save = on_save

        self.top = SmartToplevel(
            persistent_parent=master,
            title=_("New Playlist"),
            geometry="560x520",
        )
        self.top.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._track_filepaths = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = Frame(self.top)
        outer.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # Name
        row = 0
        Label(outer, text=_("Playlist Name")).grid(row=row, column=0, sticky=W)
        row += 1
        self._name_var = StringVar()
        Entry(outer, textvariable=self._name_var, width=40).grid(
            row=row, column=0, columnspan=2, sticky="ew"
        )

        # Source mode
        row += 1
        Label(outer, text=_("Source Mode")).grid(row=row, column=0, sticky=W, pady=(10, 0))
        row += 1
        self._mode_var = StringVar(value="directory")
        modes_frame = Frame(outer)
        modes_frame.grid(row=row, column=0, columnspan=2, sticky=W)
        for val, txt in [("directory", _("Directory")),
                         ("search", _("Search Query")),
                         ("tracks", _("Explicit Tracks"))]:
            Radiobutton(modes_frame, text=txt, variable=self._mode_var,
                        value=val, command=self._on_mode_change).pack(side="left", padx=(0, 10))

        # Source-specific frame (swapped based on mode)
        row += 1
        self._source_frame = Frame(outer)
        self._source_frame.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(5, 0))
        outer.rowconfigure(row, weight=1)
        outer.columnconfigure(0, weight=1)

        # Sort type
        row += 1
        Label(outer, text=_("Sort Type")).grid(row=row, column=0, sticky=W, pady=(10, 0))
        row += 1
        self._sort_var = StringVar(value=PlaylistSortType.SEQUENCE.value)
        OptionMenu(outer, self._sort_var, PlaylistSortType.SEQUENCE.value,
                   *[t.value for t in PlaylistSortType]).grid(row=row, column=0, sticky="ew")

        # Loop
        row += 1
        self._loop_var = BooleanVar(value=False)
        Checkbutton(outer, text=_("Loop"), variable=self._loop_var).grid(
            row=row, column=0, sticky=W, pady=(5, 0)
        )

        # Description
        row += 1
        Label(outer, text=_("Description (optional)")).grid(row=row, column=0, sticky=W, pady=(10, 0))
        row += 1
        self._desc_var = StringVar()
        Entry(outer, textvariable=self._desc_var, width=40).grid(
            row=row, column=0, columnspan=2, sticky="ew"
        )

        # Save button
        row += 1
        Button(outer, text=_("Save"), command=self._save).grid(
            row=row, column=0, sticky=W, pady=(10, 0)
        )

        self._on_mode_change()

    # ------------------------------------------------------------------
    # Source-mode panels
    # ------------------------------------------------------------------

    def _on_mode_change(self):
        for child in self._source_frame.winfo_children():
            child.destroy()

        mode = self._mode_var.get()
        if mode == "directory":
            self._build_directory_panel()
        elif mode == "search":
            self._build_search_panel()
        elif mode == "tracks":
            self._build_tracks_panel()

    def _build_directory_panel(self):
        f = self._source_frame
        Label(f, text=_("Directory")).grid(row=0, column=0, sticky=W)
        self._dir_var = StringVar()
        all_dirs = config.get_subdirectories()
        options = list(all_dirs.values()) if all_dirs else [_("(no directories)")]
        self._dir_var.set(options[0] if options else "")
        self._dir_map = {v: k for k, v in all_dirs.items()}
        OptionMenu(f, self._dir_var, options[0] if options else "",
                   *options).grid(row=1, column=0, sticky="ew")

    def _build_search_panel(self):
        f = self._source_frame
        self._search_vars = {}
        fields = ["all", "title", "album", "artist", "composer",
                  "genre", "instrument", "form"]
        for i, field in enumerate(fields):
            Label(f, text=_(field.capitalize())).grid(row=i, column=0, sticky=W)
            var = StringVar()
            Entry(f, textvariable=var, width=30).grid(row=i, column=1, sticky="ew", padx=(5, 0))
            self._search_vars[field] = var

    def _build_tracks_panel(self):
        f = self._source_frame
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        self._tracks_listbox = Listbox(f, height=8, selectmode=SINGLE)
        self._tracks_listbox.grid(row=0, column=0, sticky="nsew")
        self._refresh_tracks_listbox()

        btns = Frame(f)
        btns.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        Button(btns, text=_("Add Track via Search"), command=self._add_track).pack(side="left", padx=(0, 5))
        Button(btns, text=_("Remove"), command=self._remove_track).pack(side="left", padx=(0, 5))
        Button(btns, text=_("Up"), command=self._track_up).pack(side="left", padx=(0, 2))
        Button(btns, text=_("Down"), command=self._track_down).pack(side="left")

    def _refresh_tracks_listbox(self):
        if not hasattr(self, "_tracks_listbox"):
            return
        self._tracks_listbox.delete(0, END)
        for fp in self._track_filepaths:
            self._tracks_listbox.insert(END, os.path.basename(fp))

    def _add_track(self):
        from ui.search_window import SearchWindow
        if self.library_data is None:
            messagebox.showerror(_("Error"), _("Library data not available"))
            return
        from library_data.library_data import LibraryDataSearch
        search = LibraryDataSearch()
        track = SearchWindow.find_track(self.library_data, search, save_to_recent=False)
        if track and hasattr(track, "filepath"):
            self._track_filepaths.append(track.filepath)
            self._refresh_tracks_listbox()

    def _remove_track(self):
        sel = self._tracks_listbox.curselection()
        if not sel:
            return
        del self._track_filepaths[sel[0]]
        self._refresh_tracks_listbox()

    def _track_up(self):
        sel = self._tracks_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        idx = sel[0]
        self._track_filepaths[idx], self._track_filepaths[idx - 1] = \
            self._track_filepaths[idx - 1], self._track_filepaths[idx]
        self._refresh_tracks_listbox()
        self._tracks_listbox.selection_set(idx - 1)

    def _track_down(self):
        sel = self._tracks_listbox.curselection()
        if not sel or sel[0] >= len(self._track_filepaths) - 1:
            return
        idx = sel[0]
        self._track_filepaths[idx], self._track_filepaths[idx + 1] = \
            self._track_filepaths[idx + 1], self._track_filepaths[idx]
        self._refresh_tracks_listbox()
        self._tracks_listbox.selection_set(idx + 1)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showerror(_("Error"), _("Please enter a playlist name."))
            return

        if NamedPlaylistStore.exists(name):
            if not messagebox.askyesno(_("Overwrite"), _("A playlist named \"{0}\" already exists. Overwrite?").format(name)):
                return

        mode = self._mode_var.get()
        search_query = None
        source_directories = None
        track_filepaths = None

        if mode == "directory":
            label = self._dir_var.get()
            full_path = self._dir_map.get(label)
            if not full_path:
                messagebox.showerror(_("Error"), _("Please select a directory."))
                return
            source_directories = [full_path]
        elif mode == "search":
            query = {}
            for field, var in self._search_vars.items():
                val = var.get().strip()
                if val:
                    query[field] = val
            if not query:
                messagebox.showerror(_("Error"), _("Please fill in at least one search field."))
                return
            search_query = query
        elif mode == "tracks":
            if not self._track_filepaths:
                messagebox.showerror(_("Error"), _("Please add at least one track."))
                return
            track_filepaths = list(self._track_filepaths)

        sort_type_str = self._sort_var.get()
        sort_type = PlaylistSortType.get(sort_type_str)

        np = NamedPlaylist(
            name=name,
            search_query=search_query,
            source_directories=source_directories,
            track_filepaths=track_filepaths,
            sort_type=sort_type,
            loop=self._loop_var.get(),
            created_at=datetime.now().isoformat(),
            description=self._desc_var.get().strip() or None,
        )
        NamedPlaylistStore.save(np)
        logger.info(f"Saved named playlist: {np}")

        if self._on_save:
            self._on_save()

        self.top.destroy()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_closing(self):
        self.top.destroy()
