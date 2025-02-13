from tkinter import Toplevel, Label, StringVar, LEFT, W
from tkinter.ttk import Button, Entry

from extensions.open_weather import OpenWeatherAPI
from lib.tk_scroll_demo import ScrollFrame
from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class WeatherWindow(BaseWindow):
    '''
    Window to show Weather data.
    '''
    CITY = config.open_weather_city
    COL_0_WIDTH = 150
    top_level = None

    def __init__(self, master, app_actions, dimensions="600x600"):
        super().init()
        WeatherWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR)
        WeatherWindow.top_level.geometry(dimensions)
        WeatherWindow.set_title(_("Weather"))
        self.master = WeatherWindow.top_level
        self.app_actions = app_actions
        self.open_weather_api = OpenWeatherAPI()

        self.has_closed = False
        self.frame = ScrollFrame(self.master, bg_color=AppStyle.BG_COLOR)
        self.frame.pack(side="top", fill="both", expand=True)

        self._label_info = Label(self.frame.viewPort)
        self.add_label(self._label_info, _("Weather"), row=0, wraplength=WeatherWindow.COL_0_WIDTH)

        self.update_btn = None
        self.add_btn("update_btn", _("Update"), self.get_weather_data, row=0)

        self.city = StringVar(self.frame.viewPort)
        self.city.set(WeatherWindow.CITY)
        self.city_entry = Entry(self.frame.viewPort, textvariable=self.city)
        self.city_entry.grid(row=1)

        self._weather_label = Label(self.frame.viewPort)
        self.add_label(self._weather_label, "Gathering weather data...", row=2)

        # self.master.bind("<Key>", self.filter_targets)
        # self.master.bind("<Return>", self.do_action)
        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.frame.after(1, lambda: self.frame.focus_force())
        Utils.start_thread(self.get_weather_data, use_asyncio=False)

    def get_weather_data(self):
        city = self.city.get().strip()
        WeatherWindow.CITY = city
        weather = self.open_weather_api.get_weather_for_city(city)
        self._weather_label["text"] = str(weather)
        WeatherWindow.set_title(city)
        self.master.update()

    @staticmethod
    def set_title(extra_text):
        WeatherWindow.top_level.title(_("Weather") + " - " + extra_text)

    def close_windows(self, event=None):
        self.master.destroy()
        self.has_closed = True

    def add_label(self, label_ref, text, row=0, column=0, wraplength=500):
        label_ref['text'] = text
        label_ref.grid(column=column, row=row, sticky=W)
        label_ref.config(wraplength=wraplength, justify=LEFT, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)

    def add_btn(self, button_ref_name, text, command, row=0, column=0):
        if getattr(self, button_ref_name) is None:
            button = Button(master=self.frame.viewPort, text=text, command=command)
            setattr(self, button_ref_name, button)
            button # for some reason this is necessary to maintain the reference?
            button.grid(row=row, column=column)

