from copy import deepcopy
import os
import signal
import time
import traceback

from tkinter import messagebox, Toplevel, Frame, Label, Checkbutton, Text, StringVar, BooleanVar, END, HORIZONTAL, NW, BOTH, YES, N, E, W
from tkinter.constants import W
import tkinter.font as fnt
from tkinter.ttk import Button, Entry, OptionMenu, Progressbar, Scale
from lib.autocomplete_entry import AutocompleteEntry, matches
from ttkthemes import ThemedTk

from utils.globals import Globals, WorkflowType

from ops.run import Run
from ops.run_config import RunConfig
from ops.playback_config import PlaybackConfig
from ui.app_style import AppStyle
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import WorkflowType
from utils.job_queue import JobQueue
from utils.runner_app_config import RunnerAppConfig
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

def set_attr_if_not_empty(text_box):
    current_value = text_box.get()
    if not current_value or current_value == "":
        return None
    return 

def matches_tag(fieldValue, acListEntry):
    if fieldValue and "+" in fieldValue:
        pattern_base = fieldValue.split("+")[-1]
    elif fieldValue and "," in fieldValue:
        pattern_base = fieldValue.split(",")[-1]
    else:
        pattern_base = fieldValue
    return matches(pattern_base, acListEntry)

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


class App():
    '''
    UI for Stable Diffusion workflow management.
    '''

    def __init__(self, master):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.progress_bar = None
        self.job_queue = JobQueue("Playlist Runs")
#        self.job_queue_preset_schedules = JobQueue("Preset Schedules")
        self.runner_app_config = self.load_info_cache()
        self.config_history_index = 0
        self.current_run = Run(RunConfig())

        # Sidebar
        self.sidebar = Sidebar(self.master)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.columnconfigure(0, weight=1)
        self.row_counter0 = 0
        self.row_counter1 = 0
        self.sidebar.grid(column=0, row=self.row_counter0)
        self.label_title = Label(self.sidebar)
        self.add_label(self.label_title, _("Muse"), sticky=None, columnspan=2)
        ## TODO change above label to be software-agnostic

        self.run_btn = None
        self.add_button("run_btn", _("Play"), self.run)

        self.run_plus_btn = None
        self.add_button("run_plus_btn", _("Play Plus"), lambda event: self.run(event, only_music=False))

        self.next_btn = None
        self.add_button("next_btn", _("Next"), self.next)

        self.pause_btn = None
        self.add_button("pause_btn", _("Pause"), self.pause)

        self.cancel_btn = Button(self.sidebar, text=_("Stop"), command=self.cancel)
        self.label_song_text = Label(self.sidebar)
        self.add_label(self.label_song_text, "", sticky=None)


        # TODO multiselect
        self.label_workflows = Label(self.sidebar)
        self.add_label(self.label_workflows, _("Workflow"), increment_row_counter=False)
        self.workflow = StringVar(master)
        self.workflows_choice = OptionMenu(self.sidebar, self.workflow, self.runner_app_config.workflow_type,
                                           *WorkflowType.__members__.keys(), command=self.set_workflow_type)
        self.apply_to_grid(self.workflows_choice, interior_column=1, sticky=W)

        self.label_total = Label(self.sidebar)
        self.add_label(self.label_total, _("Set Total"), increment_row_counter=False)
        self.total = StringVar(master)
        total_options = [str(i) for i in list(range(-1, 101))]
        total_options.remove('0')
        self.total_choice = OptionMenu(self.sidebar, self.total, str(self.runner_app_config.total), *total_options)
        self.apply_to_grid(self.total_choice, interior_column=1, sticky=W)

        self.label_delay = Label(self.sidebar)
        self.add_label(self.label_delay, _("Delay Seconds"), increment_row_counter=False)
        self.delay = StringVar(master)
        self.delay_choice = OptionMenu(self.sidebar, self.delay, str(self.runner_app_config.delay_time_seconds), *[str(i) for i in list(range(101))], command=self.set_delay)
        self.apply_to_grid(self.delay_choice, interior_column=1, sticky=W)

        self.label_directory = Label(self.sidebar)
        self.add_label(self.label_directory, _("Directory"), increment_row_counter=False)
        self.directory = StringVar(master)
        directory_options = ["ALL"]
        directory_options.extend(list(config.get_subdirectories().values()))
        self.directory_choice = OptionMenu(self.sidebar, self.directory, str(self.runner_app_config.directory), *directory_options)
        self.apply_to_grid(self.directory_choice, interior_column=1, sticky=W)

        # self.label_model_tags = Label(self.sidebar)
        # self.add_label(self.label_model_tags, _("Model Tags"))
        # self.model_tags = StringVar()
        # model_names = list(map(lambda l: str(l).split('.')[0], Model.CHECKPOINTS))
        # self.model_tags_box = AutocompleteEntry(model_names,
        #                                        self.sidebar,
        #                                        listboxLength=6,
        #                                        textvariable=self.model_tags,
        #                                        matchesFunction=matches_tag,
        #                                        setFunction=set_tag,
        #                                        width=55, font=fnt.Font(size=8))
        # self.model_tags_box.bind("<Return>", self.set_model_dependent_fields)
        # self.model_tags_box.insert(0, self.runner_app_config.model_tags)
        # self.apply_to_grid(self.model_tags_box, sticky=W, columnspan=2)

        # self.tag_blacklist_btn = None
        # self.presets_window_btn = None
        # self.add_button("tag_blacklist_btn", text=_("Tag Blacklist"), command=self.show_tag_blacklist, sidebar=False, increment_row_counter=False)
        # self.add_button("presets_window_btn", text=_("Presets Window"), command=self.open_presets_window, sidebar=False, interior_column=1)


        self.overwrite = BooleanVar(value=False)
        self.overwrite_choice = Checkbutton(self.sidebar, text=_('Overwrite'), variable=self.overwrite)
        self.apply_to_grid(self.overwrite_choice, sticky=W)

        self.master.bind("<Control-Return>", self.run)
        self.master.bind("<Shift-R>", self.run)
        self.master.bind("<Prior>", lambda event: self.one_config_away(change=1))
        self.master.bind("<Next>", lambda event: self.one_config_away(change=-1))
        self.master.bind("<Home>", lambda event: self.first_config())
        self.master.bind("<End>", lambda event: self.first_config(end=True))
        self.master.bind("<Control-q>", self.quit)
        self.toggle_theme()
        self.master.update()
        # self.close_autocomplete_popups()

    def toggle_theme(self, to_theme=None, do_toast=True):
        if (to_theme is None and AppStyle.IS_DEFAULT_THEME) or to_theme == AppStyle.LIGHT_THEME:
            if to_theme is None:
                self.master.set_theme("breeze", themebg="black")  # Changes the window to light theme
            AppStyle.BG_COLOR = "gray"
            AppStyle.FG_COLOR = "black"
        else:
            if to_theme is None:
                self.master.set_theme("black", themebg="black")  # Changes the window to dark theme
            AppStyle.BG_COLOR = config.background_color if config.background_color and config.background_color != "" else "#053E10"
            AppStyle.FG_COLOR = config.foreground_color if config.foreground_color and config.foreground_color != "" else "white"
        AppStyle.IS_DEFAULT_THEME = (not AppStyle.IS_DEFAULT_THEME or to_theme
                                     == AppStyle.DARK_THEME) and to_theme != AppStyle.LIGHT_THEME
        self.master.config(bg=AppStyle.BG_COLOR)
        self.sidebar.config(bg=AppStyle.BG_COLOR)
        for name, attr in self.__dict__.items():
            if isinstance(attr, Label):
                attr.config(bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
                            # font=fnt.Font(size=config.font_size))
            elif isinstance(attr, Checkbutton):
                attr.config(bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR,
                            selectcolor=AppStyle.BG_COLOR)#, font=fnt.Font(size=config.font_size))
        self.master.update()
        if do_toast:
            self.toast(f"Theme switched to {AppStyle.get_theme_name()}.")

    # def close_autocomplete_popups(self):
    #     self.model_tags_box.closeListbox()
    #     self.lora_tags_box.closeListbox()

    def on_closing(self):
        self.store_info_cache()
        # if self.server is not None:
        #     try:
        #         self.server.stop()
        #     except Exception as e:
        #         print(f"Error stopping server: {e}")
        self.master.destroy()


    def quit(self, event=None):
        res = self.alert(_("Confirm Quit"), _("Would you like to quit the application?"), kind="askokcancel")
        if res == messagebox.OK or res == True:
            print("Exiting application")
            self.on_closing()


    def store_info_cache(self):
        if self.runner_app_config is not None:
            if app_info_cache.set_history(self.runner_app_config):
                if self.config_history_index > 0:
                    self.config_history_index -= 1
        app_info_cache.set("config_history_index", self.config_history_index)
        PlaybackConfig.store_directory_cache()
        app_info_cache.store()

    def load_info_cache(self):
        try:
            PlaybackConfig.load_directory_cache()
            self.config_history_index = app_info_cache.get("config_history_index", default_val=0)
            return RunnerAppConfig.from_dict(app_info_cache.get_history(0))
        except Exception as e:
            print(e)
            return RunnerAppConfig()

    def one_config_away(self, change=1):
        assert type(self.config_history_index) == int, "History index must be an integer"
        self.config_history_index += change
        try:
            self.runner_app_config = RunnerAppConfig.from_dict(app_info_cache.get_history(self.config_history_index))
            self.set_widgets_from_config()
            # self.close_autocomplete_popups()
        except Exception as e:
            self.config_history_index -= change

    def first_config(self, end=False):
        self.config_history_index = app_info_cache.get_last_history_index() if end else 0
        try:
            self.runner_app_config = RunnerAppConfig.from_dict(app_info_cache.get_history(self.config_history_index))
            self.set_widgets_from_config()
            # self.close_autocomplete_popups()
        except Exception as e:
            self.config_history_index = 0

    def set_default_config(self, event=None):
        self.runner_app_config = RunnerAppConfig()
        self.set_widgets_from_config()
        # self.close_autocomplete_popups()

    def set_widget_value(self, widget, value):
        if isinstance(widget, Scale):
            widget.set(float(value) * 100)
        elif isinstance(widget, Text):
            widget.delete("0.0", "end")
            widget.insert("0.0", str(value))
        else:
            widget.delete(0, "end")
            widget.insert(0, value)

    def set_widgets_from_config(self):
        if self.runner_app_config is None:
            raise Exception("No config to set widgets from")
        self.set_workflow_type(self.runner_app_config.workflow_type)
        # self.set_widget_value(self.resolutions_box, self.runner_app_config.resolutions)
        # self.set_widget_value(self.model_tags_box, self.runner_app_config.model_tags)
        # if self.runner_app_config.lora_tags is not None and self.runner_app_config.lora_tags!= "":
        #     self.set_widget_value(self.lora_tags_box, self.runner_app_config.lora_tags)

        self.total.set(str(self.runner_app_config.total))
        self.delay.set(str(self.runner_app_config.delay_time_seconds))
        self.overwrite.set(self.runner_app_config.overwrite)

    # def set_widgets_from_preset(self, preset):
    #     self.prompt_mode.set(preset.prompt_mode)
    #     self.set_widget_value(self.positive_tags_box, preset.positive_tags)
    #     self.set_widget_value(self.negative_tags_box, preset.negative_tags)
    #     self.master.update()

    # def construct_preset(self, name):
    #     args, args_copy = self.get_args()
    #     self.runner_app_config.set_from_run_config(args)
    #     return Preset.from_runner_app_config(name, self.runner_app_config)

    # def run_preset_schedule(self, override_args={}):
    #     def run_preset_async():
    #         self.job_queue_preset_schedules.job_running = True
    #         if "control_net" in override_args:
    #             self.controlnet_file.set(override_args["control_net"])
    #             print(f"Updated Control Net for next preset schedule: " + str(override_args["control_net"]))
    #         if "ip_adapter" in override_args:
    #             self.ipadapter_file.set(override_args["ip_adapter"])
    #             print(f"Updated IP Adapater for next preset schedule: " + str(override_args["ip_adapter"]))
    #         starting_total = int(self.total.get())
    #         schedule = config.prompt_preset_schedules[self.preset_schedule.get()]
    #         for preset_name, count in schedule.items():
    #             if not self.job_queue_preset_schedules.has_pending() or not self.run_preset_schedule_var.get() or \
    #                     (self.current_run is not None and not self.current_run.is_infinite() and self.current_run.is_cancelled):
    #                 self.job_queue_preset_schedules.cancel()
    #                 return
    #             try:
    #                 preset = PresetsWindow.get_preset_by_name(preset_name)
    #             except Exception as e:
    #                 self.handle_error(str(e), "Preset Schedule Error")
    #                 raise e
    #             self.set_widgets_from_preset(preset)
    #             if count > 0:
    #                 self.total.set(str(count))
    #             self.run()
    #             # NOTE have to do some special handling here because the runs are still not self-contained,
    #             # and overwriting widget values may cause the current run to have its settings changed mid-run
    #             time.sleep(0.1)
    #             started_run_id = self.current_run.id
    #             while (self.current_run is not None and started_run_id == self.current_run.id
    #                     and not self.current_run.is_cancelled and not self.current_run.is_complete):
    #                 if not self.job_queue_preset_schedules.has_pending() or not self.run_preset_schedule_var.get():
    #                     self.job_queue_preset_schedules.cancel()
    #                     return
    #                 time.sleep(1)
    #         self.total.set(str(starting_total))
    #         self.job_queue_preset_schedules.job_running = False
    #         next_preset_schedule_args = self.job_queue_preset_schedules.take()
    #         if next_preset_schedule_args is None:
    #             play_sound()
    #             self.job_queue_preset_schedules.cancel()
    #         else:
    #             self.run_preset_schedule(override_args=next_preset_schedule_args)

    #     start_thread(run_preset_async, use_asyncio=False, args=[])

    def set_workflow_type(self, event=None, workflow_tag=None):
        if workflow_tag is None:
            workflow_tag = self.workflow.get()

    def set_delay(self, event=None):
        self.runner_app_config.delay_time_seconds = self.delay.get()
        Globals.set_delay(int(self.runner_app_config.delay_time_seconds))

    def destroy_progress_bar(self):
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.grid_forget()
            self.destroy_grid_element("progress_bar")
            self.progress_bar = None

    def run(self, event=None, only_music=True):
        if self.current_run.is_infinite():
            self.current_run.cancel()
        # if event is not None and self.job_queue_preset_schedules.has_pending():
        #     res = self.alert(_("Confirm Run"),
        #         _("Starting a new run will cancel the current preset schedule. Are you sure you want to proceed?"),
        #         kind="warning")
        #     if res != messagebox.OK:
        #         return
        # self.job_queue_preset_schedules.cancel()
        args, args_copy = self.get_args(only_music=only_music)

        try:
            args.validate()
        except Exception as e:
            res = self.alert(_("Confirm Run"),
                str(e) + "\n\n" + _("Are you sure you want to proceed?"),
                kind="warning")
            if res != messagebox.OK:
                return None

        def run_async(args) -> None:
            self.job_queue.job_running = True
            self.destroy_progress_bar()
            self.progress_bar = Progressbar(self.sidebar, orient=HORIZONTAL, length=100, mode='indeterminate')
            self.progress_bar.grid(row=1, column=1)
            self.progress_bar.start()
            self.cancel_btn.grid(row=2, column=1)
            self.current_run = Run(args, song_text_callback=self.update_song_text)
            self.current_run.execute()
            self.cancel_btn.grid_forget()
            self.destroy_progress_bar()
            self.job_queue.job_running = False
            next_job_args = self.job_queue.take()
            if next_job_args:
                Utils.start_thread(run_async, use_asyncio=False, args=[next_job_args])

        if self.job_queue.has_pending():
            self.job_queue.add(args)
        else:
            self.runner_app_config.set_from_run_config(args_copy)
            Utils.start_thread(run_async, use_asyncio=False, args=[args])

    def next(self, event=None) -> None:
        self.current_run.next()
    
    def pause(self, event=None) -> None:
        self.current_run.pause()

    def cancel(self, event=None):
        self.current_run.cancel()

    def get_args(self, only_music=True):
        self.store_info_cache()
        self.set_delay()
        # self.set_concepts_dir()
        args = RunConfig()
        args.workflow_tag = self.workflow.get()
        args.total = self.total.get()
        args.directories = self.get_directories()
        args.overwrite = self.overwrite.get()
        args.only_music = only_music

        # controlnet_file = clear_quotes(self.controlnet_file.get())
        # self.runner_app_config.control_net_file = controlnet_file
        args_copy = deepcopy(args)

        return args, args_copy

    def get_directories(self):
        directories = []
        selection = self.directory.get()
        all_dirs = config.get_subdirectories()
        if selection == "ALL":
            return list(all_dirs.keys())
        else:
            for full_path, key in all_dirs.items():
                if key == selection:
                    directories.append(full_path)
                    break
            return directories

    def update_song_text(self, song_name, directory):
        text = "Song: " + song_name + "\nDirectory: " + directory
        text = Utils._wrap_text_to_fit_length(text, 100)
        self.label_song_text["text"] = text
        self.master.update()

    # def open_presets_window(self):
    #     top_level = Toplevel(self.master, bg=AppStyle.BG_COLOR)
    #     top_level.title(_("Presets Window"))
    #     top_level.geometry(PresetsWindow.get_geometry(is_gui=True))
    #     try:
    #         presets_window = PresetsWindow(top_level, self.toast, self.construct_preset, self.set_widgets_from_preset)
    #     except Exception as e:
    #         self.handle_error(str(e), title="Presets Window Error")

    def alert(self, title, message, kind="info", hidemain=True) -> None:
        if kind not in ("error", "warning", "info"):
            raise ValueError("Unsupported alert kind.")

        print(f"Alert - Title: \"{title}\" Message: {message}")
        show_method = getattr(messagebox, "show{}".format(kind))
        return show_method(title, message)

    def handle_error(self, error_text, title=None, kind="error"):
        traceback.print_exc()
        if title is None:
            title = _("Error")
        self.alert(title, error_text, kind=kind)

    def toast(self, message):
        print("Toast message: " + message)

        # Set the position of the toast on the screen (top right)
        width = 300
        height = 100
        x = self.master.winfo_screenwidth() - width
        y = 0

        # Create the toast on the top level
        toast = Toplevel(self.master, bg=AppStyle.BG_COLOR)
        toast.geometry(f'{width}x{height}+{int(x)}+{int(y)}')
        self.container = Frame(toast, bg=AppStyle.BG_COLOR)
        self.container.pack(fill=BOTH, expand=YES)
        label = Label(
            self.container,
            text=message,
            anchor=NW,
            bg=AppStyle.BG_COLOR,
            fg=AppStyle.FG_COLOR,
            font=('Helvetica', 12)
        )
        label.grid(row=1, column=1, sticky="NSEW", padx=10, pady=(0, 5))
        
        # Make the window invisible and bring it to front
        toast.attributes('-topmost', True)
#        toast.withdraw()

        # Start a new thread that will destroy the window after a few seconds
        def self_destruct_after(time_in_seconds):
            time.sleep(time_in_seconds)
            label.destroy()
            toast.destroy()
        Utils.start_thread(self_destruct_after, use_asyncio=False, args=[2])

    def apply_to_grid(self, component, sticky=None, pady=0, interior_column=0, column=0, increment_row_counter=True, columnspan=None):
        row = self.row_counter0 if column == 0 else self.row_counter1
        if sticky is None:
            if columnspan is None:
                component.grid(column=interior_column, row=row, pady=pady)
            else:
                component.grid(column=interior_column, row=row, pady=pady, columnspan=columnspan)
        else:
            if columnspan is None:
                component.grid(column=interior_column, row=row, sticky=sticky, pady=pady)
            else:
                component.grid(column=interior_column, row=row, sticky=sticky, pady=pady, columnspan=columnspan)
        if increment_row_counter:
            if column == 0:
                self.row_counter0 += 1
            else:
                self.row_counter1 += 1

    def add_label(self, label_ref, text, sticky=W, pady=0, column=0, columnspan=None, increment_row_counter=True):
        label_ref['text'] = text
        self.apply_to_grid(label_ref, sticky=sticky, pady=pady, column=column, columnspan=columnspan, increment_row_counter=increment_row_counter)

    def add_button(self, button_ref_name, text, command, sidebar=True, interior_column=0, increment_row_counter=True):
        if getattr(self, button_ref_name) is None:
            master = self.sidebar if sidebar else self.prompter_config_bar
            button = Button(master=master, text=text, command=command)
            setattr(self, button_ref_name, button)
            button
            self.apply_to_grid(button, column=(0 if sidebar else 1), interior_column=interior_column, increment_row_counter=increment_row_counter)

    def new_entry(self, text_variable, text="", width=55, sidebar=True, **kw):
        master = self.sidebar if sidebar else self.prompter_config_bar
        return Entry(master, text=text, textvariable=text_variable, width=width, font=fnt.Font(size=8), **kw)

    def destroy_grid_element(self, element_ref_name):
        element = getattr(self, element_ref_name)
        if element is not None:
            element.destroy()
            setattr(self, element_ref_name, None)
            self.row_counter0 -= 1


if __name__ == "__main__":
    try:
        # assets = os.path.join(os.path.dirname(os.path.realpath(__file__)), "assets")
        root = ThemedTk(theme="black", themebg="black")
        root.title(_(" Muse "))
        #root.iconbitmap(bitmap=r"icon.ico")
        # icon = PhotoImage(file=os.path.join(assets, "icon.png"))
        # root.iconphoto(False, icon)
        root.geometry("700x500")
        # root.attributes('-fullscreen', True)
        root.resizable(1, 1)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # Graceful shutdown handler
        def graceful_shutdown(signum, frame):
            print("Caught signal, shutting down gracefully...")
            app.on_closing()
            exit(0)

        # Register the signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)

        app = App(root)
        root.mainloop()
        exit()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
