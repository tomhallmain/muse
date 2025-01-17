from copy import deepcopy
import signal
import time
import traceback

from tkinter import messagebox, Toplevel, Frame, Label, Checkbutton, Text, StringVar, BooleanVar, Scale, END, HORIZONTAL, NW, BOTH, YES, N, E, W
from tkinter.constants import W
import tkinter.font as fnt
from tkinter.ttk import Button, Entry, OptionMenu, Scale

from utils.globals import Globals, WorkflowType

from muse.playback_config import PlaybackConfig
from muse.run import Run
from muse.run_config import RunConfig
from muse.schedules_manager import SchedulesManager
from ui.app_style import AppStyle
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import WorkflowType
from utils.runner_app_config import RunnerAppConfig
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

# TODO figure out why overwrite not working

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


class PlaybackConfigWindow():
    '''
    UI for defining specific playbacks / playlists.
    '''

    def __init__(self, master):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Sidebar
        self.sidebar = Sidebar(self.master)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.columnconfigure(0, weight=1)
        self.row_counter0 = 0
        self.row_counter1 = 0
        self.sidebar.grid(column=0, row=self.row_counter0)
        self.label_title = Label(self.sidebar)
        self.add_label(self.label_title, _("Muse"), sticky=None, columnspan=2)

        # TODO multiselect
        self.label_workflows = Label(self.sidebar)
        self.add_label(self.label_workflows, _("Workflow"), increment_row_counter=False)
        self.workflow = StringVar(master)
        self.workflows_choice = OptionMenu(self.sidebar, self.workflow, self.runner_app_config.workflow_type,
                                           *WorkflowType.__members__.keys(), command=self.set_workflow_type)
        self.apply_to_grid(self.workflows_choice, interior_column=1, sticky=W)

        self.label_directory = Label(self.sidebar)
        self.add_label(self.label_directory, _("Directory"), increment_row_counter=False)
        self.directory = StringVar(master)
        directory_options = ["ALL"]
        directory_options.extend(list(config.get_subdirectories().values()))
        self.directory_choice = OptionMenu(self.sidebar, self.directory, str(self.runner_app_config.directory),
                                           *directory_options, command=self.set_directory)
        self.apply_to_grid(self.directory_choice, interior_column=1, sticky=W)

        self.master.update()

    def on_closing(self):
        self.store_info_cache()
        # if self.server is not None:
        #     try:
        #         self.server.stop()
        #     except Exception as e:
        #         Utils.log_yellow(f"Error stopping server: {e}")
        self.master.destroy()

    def load_info_cache(self):
        try:
            PlaybackConfig.load_directory_cache()
            SchedulesManager.set_schedules()
            self.config_history_index = app_info_cache.get("config_history_index", default_val=0)
            return app_info_cache.get_history_latest()
        except Exception as e:
            Utils.log_red(e)
            return RunnerAppConfig()

    def set_widget_value(self, widget, value):
        if isinstance(widget, Scale):
            widget.set(float(value))
        elif isinstance(widget, Text):
            widget.delete("0.0", "end")
            widget.insert("0.0", str(value))
        else:
            widget.delete(0, "end")
            widget.insert(0, value)

    def set_widgets_from_config(self):
        self.set_workflow_type(self.runner_app_config.workflow_type)
        # self.set_widget_value(self.resolutions_box, self.runner_app_config.resolutions)

    def set_workflow_type(self, event=None, workflow_tag=None):
        if workflow_tag is None:
            workflow_tag = self.workflow.get()

    def set_directory(self, event=None):
        self.runner_app_config.directory = self.directory.get()

    def destroy_progress_bar(self):
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.grid_forget()
            self.destroy_grid_element("progress_bar")
            self.progress_bar = None

    def get_args(self):
        # self.set_concepts_dir()
        args = RunConfig()
        args.workflow_tag = self.workflow.get()
        args.directories = self.get_directories()

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

    def apply_to_grid(self, component, sticky=None, pady=0, interior_column=0, row=-1, column=0, increment_row_counter=True, columnspan=None):
        if row == -1:
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

    def add_label(self, label_ref, text, sticky=W, pady=0, row=-1, column=0, columnspan=None, increment_row_counter=True):
        label_ref['text'] = text
        self.apply_to_grid(label_ref, sticky=sticky, pady=pady, row=row, column=column, columnspan=columnspan, increment_row_counter=increment_row_counter)

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


