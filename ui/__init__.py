"""UI package for the Muse application."""

from ui.app_actions import AppActions
from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from ui.composers_window import ComposersWindow
from ui.extensions_window import ExtensionsWindow
from ui.favorites_window import FavoritesWindow
from ui.media_frame import MediaFrame
from ui.network_media_window import NetworkMediaWindow
from ui.playlist_window import PlaylistWindow
from ui.preset import Preset
from ui.presets_window import PresetsWindow
from ui.schedules_window import SchedulesWindow
from ui.search_window import SearchWindow
from ui.track_details_window import TrackDetailsWindow
from ui.weather_window import WeatherWindow

__all__ = [
    'AppActions',
    'AppStyle',
    'BaseWindow',
    'ComposersWindow',
    'ExtensionsWindow',
    'FavoritesWindow',
    'MediaFrame',
    'NetworkMediaWindow',
    'PlaylistWindow',
    'Preset',
    'PresetsWindow',
    'SchedulesWindow',
    'SearchWindow',
    'TrackDetailsWindow',
    'WeatherWindow',
] 