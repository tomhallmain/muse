from enum import Enum
import os

from utils.translations import I18N

_ = I18N._


class AppInfo:
    SERVICE_NAME = "MyPersonalApplicationsService"
    APP_IDENTIFIER = "muse"


class Globals:
    HOME = os.path.expanduser("~")
    DELAY_TIME_SECONDS = 5
    DEFAULT_VOLUME_THRESHOLD = 60

    @classmethod
    def set_delay(cls, delay=5):
        cls.DELAY_TIME_SECONDS = int(delay)

    @classmethod
    def set_volume(cls, volume=60):
        cls.DEFAULT_VOLUME_THRESHOLD = int(volume)

class MediaFileType(Enum):
    MKV = '.MKV'
    MP4 = '.MP4'
    MOV = '.MOV'
    WEBM = '.WEBM'
    FLV = '.FLV'
    AVI = '.AVI'
    WMV = '.WMV'
    VOB = '.VOB'
    MPG = '.MPG'
    ASF = '.ASF'
    MP3 = '.MP3'
    OGG = '.OGG'
    AAC = '.AAC'
    FLAC = '.FLAC'
    ALAC = '.ALAC'
    WAV = '.WAV'
    AIFF = '.AIFF'
    TTA = '.TTA'
    M4A = '.M4A'
    MP2 = '.MP2'
    MP1 = '.MP1'
    AU = '.AU'
    S3M = '.S3M'
    IT = '.IT'
    XM = '.XM'
    MOD = '.MOD'
    MIDI = '.MIDI'
    MID = '.MID'
    WMA = '.WMA'
    OGG_OPUS = '.OGG_OPUS'
    WEBM_VP8 = '.WEBM_VP8'
    OPUS = '.OPUS'

    @classmethod
    def is_media_filetype(cls, filename):
        f = filename.upper()
        for e in cls:
            if f.endswith(e.value):
                return True
        return False

class PlaylistSortType(Enum):
    RANDOM = 'RANDOM'
    SEQUENCE = 'SEQUENCE'
    ALBUM_SHUFFLE = 'ALBUM_SHUFFLE'
    ARTIST_SHUFFLE = 'ARTIST_SHUFFLE'
    COMPOSER_SHUFFLE = 'COMPOSER_SHUFFLE'
    GENRE_SHUFFLE = 'GENRE_SHUFFLE'
    FORM_SHUFFLE = 'FORM_SHUFFLE'
    INSTRUMENT_SHUFFLE = 'INSTRUMENT_SHUFFLE'

    def is_grouping_type(self):
        return self not in [PlaylistSortType.RANDOM, PlaylistSortType.SEQUENCE]

    def getter_name_mapping(self):
        return {
            self.RANDOM: 'filepath',
            self.SEQUENCE: None,
            self.ALBUM_SHUFFLE: 'album',
            self.ARTIST_SHUFFLE: 'artist',
            self.COMPOSER_SHUFFLE: 'composer',
            self.GENRE_SHUFFLE: 'get_genre',
            self.FORM_SHUFFLE: 'get_form',
            self.INSTRUMENT_SHUFFLE: 'get_instrument'
        }[self]

    def grouping_list_name_mapping(self):
        return {
            self.RANDOM: HistoryType.TRACKS,
            self.SEQUENCE: None,
            self.ALBUM_SHUFFLE: HistoryType.ALBUMS,
            self.ARTIST_SHUFFLE: HistoryType.ARTISTS,
            self.COMPOSER_SHUFFLE: HistoryType.COMPOSERS,
            self.GENRE_SHUFFLE: HistoryType.GENRES,
            self.FORM_SHUFFLE: HistoryType.FORMS,
            self.INSTRUMENT_SHUFFLE: HistoryType.INSTRUMENTS
        }[self]

    def get_translation(self):
        types = [
            PlaylistSortType.RANDOM,
            PlaylistSortType.SEQUENCE,
            PlaylistSortType.ALBUM_SHUFFLE,
            PlaylistSortType.ARTIST_SHUFFLE,
            PlaylistSortType.COMPOSER_SHUFFLE,
            PlaylistSortType.GENRE_SHUFFLE,
            PlaylistSortType.FORM_SHUFFLE,
            PlaylistSortType.INSTRUMENT_SHUFFLE
        ]
        return PlaylistSortType.get_translated_names()[types.index(self)]

    def get_grouping_readable_name(self):
        if self == PlaylistSortType.RANDOM or self == PlaylistSortType.SEQUENCE:
            return None
        if self == PlaylistSortType.ALBUM_SHUFFLE:
            return _("Album")
        if self == PlaylistSortType.ARTIST_SHUFFLE:
            return _("Artist")
        if self == PlaylistSortType.COMPOSER_SHUFFLE:
            return _("Composer")
        if self == PlaylistSortType.GENRE_SHUFFLE:
            return _("Genre")
        if self == PlaylistSortType.FORM_SHUFFLE:
            return _("Form")
        if self == PlaylistSortType.INSTRUMENT_SHUFFLE:
            return _("Instrument")
        raise Exception(f"Unhandled sort type {self}")

    @staticmethod
    def get_translated_names():
        return [
            _('Random'),
            _('Sequence'),
            _('Album Shuffle'),
            _('Artist Shuffle'),
            _('Composer Shuffle'),
            _('Genre Shuffle'),
            _('Form Shuffle'),
            _('Instrument Shuffle'),
        ]

    @staticmethod
    def get_from_translation(translation):
        types = [
            PlaylistSortType.RANDOM,
            PlaylistSortType.SEQUENCE,
            PlaylistSortType.ALBUM_SHUFFLE,
            PlaylistSortType.ARTIST_SHUFFLE,
            PlaylistSortType.COMPOSER_SHUFFLE,
            PlaylistSortType.GENRE_SHUFFLE,
            PlaylistSortType.FORM_SHUFFLE,
            PlaylistSortType.INSTRUMENT_SHUFFLE
        ]
        try:
            return types[PlaylistSortType.get_translated_names().index(translation)]
        except ValueError:
            return PlaylistSortType.RANDOM


class PlaybackMasterStrategy(Enum):
    ALL_MUSIC = "ALL_MUSIC"
    PLAYLIST_CONFIG = "PLAYLIST_CONFIG"

    def get_translation(self):
        strategies = [
            PlaybackMasterStrategy.ALL_MUSIC,
            PlaybackMasterStrategy.PLAYLIST_CONFIG,
        ]
        return PlaybackMasterStrategy.get_translated_names()[strategies.index(self)]

    @staticmethod
    def get_translated_names():
        return [
            _('All Music'),
            _('Playlist Config'),
        ]

    @staticmethod
    def get_from_translation(translation):
        strategies = [
            PlaybackMasterStrategy.ALL_MUSIC,
            PlaybackMasterStrategy.PLAYLIST_CONFIG,
        ]
        try:
            return strategies[PlaybackMasterStrategy.get_translated_names().index(translation)]
        except ValueError:
            return PlaybackMasterStrategy.ALL_MUSIC



class TrackAttribute(Enum):
    TITLE = "title"
    ALBUM = "album"
    ARTIST = "artist"
    COMPOSER = "composer"
    GENRE = "genre"
    FORM = "form"
    INSTRUMENT = "instrument"

    def get_translation(self):
        types = [
            TrackAttribute.TITLE,
            TrackAttribute.ALBUM,
            TrackAttribute.ARTIST,
            TrackAttribute.COMPOSER,
            TrackAttribute.GENRE,
            TrackAttribute.FORM,
            TrackAttribute.INSTRUMENT,
        ]
        return TrackAttribute.get_translated_names()[types.index(self)]

    @staticmethod
    def get_translated_names():
        return [
            _('Title'),
            _('Album'),
            _('Artist'),
            _('Composer'),
            _('Genre'),
            _('Form'),
            _('Instrument'),
        ]

    @staticmethod
    def get_from_translation(translation):
        types = [
            TrackAttribute.TITLE,
            TrackAttribute.ALBUM,
            TrackAttribute.ARTIST,
            TrackAttribute.COMPOSER,
            TrackAttribute.GENRE,
            TrackAttribute.FORM,
            TrackAttribute.INSTRUMENT,
        ]
        try:
            return types[TrackAttribute.get_translated_names().index(translation)]
        except ValueError:
            return TrackAttribute.ARTIST

    def get_playlist_sort_type(self) -> PlaylistSortType:
        if self == TrackAttribute.COMPOSER:
            return PlaylistSortType.COMPOSER_SHUFFLE
        elif self == TrackAttribute.ARTIST:
            return PlaylistSortType.ARTIST_SHUFFLE
        elif self == TrackAttribute.GENRE:
            return PlaylistSortType.GENRE_SHUFFLE
        elif self == TrackAttribute.INSTRUMENT:
            return PlaylistSortType.INSTRUMENT_SHUFFLE
        elif self == TrackAttribute.FORM:
            return PlaylistSortType.FORM_SHUFFLE
        elif self == TrackAttribute.ALBUM:
            return PlaylistSortType.ALBUM_SHUFFLE
        else:
            return PlaylistSortType.RANDOM



class ExtensionStrategy(Enum):
    COMPOSER = "extend by composer"
    ARTIST = "extend by artist"
    GENRE = "extend by genre"
    FORM = "extend by form"
    INSTRUMENT = "extend by instrument"
    RANDOM = "random"
    PROMPT = "extend by prompt"
    SPECIFIC_TAGS = "extend by specific tags"
    LINK_TYPE_A = "extend by link type a" # i.e. provide a link to a forum post with scrapable media content

    def get_translation(self):
        types = [
            ExtensionStrategy.COMPOSER,
            ExtensionStrategy.ARTIST,
            ExtensionStrategy.GENRE,
            ExtensionStrategy.FORM,
            ExtensionStrategy.INSTRUMENT,
            ExtensionStrategy.RANDOM,
            ExtensionStrategy.PROMPT,
            ExtensionStrategy.SPECIFIC_TAGS,
            ExtensionStrategy.LINK_TYPE_A,
        ]
        return ExtensionStrategy.get_translated_names()[types.index(self)]

    @staticmethod
    def get_translated_names():
        return [
            _('Composer'),
            _('Artist'),
            _('Genre'),
            _('Form'),
            _('Instrument'),
            _('Random'),
            'Prompt',
            'Specific tags',
            'Link type A',
        ]

    @staticmethod
    def get_from_translation(translation):
        types = [
            ExtensionStrategy.COMPOSER,
            ExtensionStrategy.ARTIST,
            ExtensionStrategy.GENRE,
            ExtensionStrategy.FORM,
            ExtensionStrategy.INSTRUMENT,
            ExtensionStrategy.RANDOM,
            ExtensionStrategy.PROMPT,
            ExtensionStrategy.SPECIFIC_TAGS,
            ExtensionStrategy.LINK_TYPE_A,
        ]
        try:
            return types[ExtensionStrategy.get_translated_names().index(translation)]
        except ValueError:
            return ExtensionStrategy.ARTIST


class Topic(Enum):
    WEATHER = "weather"
    NEWS = "news"
    HACKERNEWS = "hackernews"
    JOKE = "joke"
    FACT = "fact"
    FABLE = "fable"
    TRUTH_AND_LIE = "truth_and_lie"
    APHORISM = "aphorism"
    POEM = "poem"
    QUOTE = "quote"
    TONGUE_TWISTER = "tongue_twister"
    MOTIVATION = "motivation"
    CALENDAR = "calendar"
    TRACK_CONTEXT_PRIOR = "track_context_prior"
    TRACK_CONTEXT_POST = "track_context_post"
    PLAYLIST_CONTEXT = "playlist_context"
    RANDOM_WIKI_ARTICLE = "random_wiki_article"
    FUNNY_STORY = "funny_story"
    LANGUAGE_LEARNING = "language_learning"

    def translate(self):
        if self == Topic.WEATHER:
            return _("weather")
        elif self == Topic.NEWS:
            return _("news")
        elif self == Topic.HACKERNEWS:
            return "hacker news"
        elif self == Topic.JOKE:
            return _("joke")
        elif self == Topic.FACT:
            return _("fact")
        elif self == Topic.FABLE:
            return _("fable")
        elif self == Topic.TRUTH_AND_LIE:
            return _("truth and lie")
        elif self == Topic.APHORISM:
            return _("aphorism")
        elif self == Topic.POEM:
            return _("poem")
        elif self == Topic.QUOTE:
            return _("quote")
        elif self == Topic.TONGUE_TWISTER:
            return _("tongue twister")
        elif self == Topic.MOTIVATION:
            return _("motivation")
        elif self == Topic.CALENDAR:
            return _("calendar")
        elif self == Topic.TRACK_CONTEXT_PRIOR:
            return _("more about the next track")
        elif self == Topic.TRACK_CONTEXT_POST:
            return _("more about the last track")
        elif self == Topic.PLAYLIST_CONTEXT:
            return _("more about our playlist")
        elif self == Topic.RANDOM_WIKI_ARTICLE:
            return _("random wiki article")
        elif self == Topic.FUNNY_STORY:
            return _("funny story")
        elif self == Topic.LANGUAGE_LEARNING:
            return  _("language learning")
        else:
            raise Exception(f"unhandled topic: {self}")

    def get_prompt_topic_value(self):
        if self == Topic.HACKERNEWS:
            return "news"
        return str(self.value)

class HistoryType(Enum):
    TRACKS = "recently_played_filepaths"
    ALBUMS = "recently_played_albums"
    ARTISTS = "recently_played_artists"
    COMPOSERS = "recently_played_composers"
    GENRES = "recently_played_genres"
    FORMS = "recently_played_forms"
    INSTRUMENTS = "recently_played_instruments"

    def get_translation(self):
        types = [
            HistoryType.TRACKS,
            HistoryType.ALBUMS,
            HistoryType.ARTISTS,
            HistoryType.COMPOSERS,
            HistoryType.GENRES,
            HistoryType.FORMS,
            HistoryType.INSTRUMENTS,
        ]
        return HistoryType.get_translated_names()[types.index(self)]

    @staticmethod
    def get_translated_names():
        return [
            _('Tracks'),
            _('Albums'),
            _('Artists'),
            _('Composers'),
            _('Genres'),
            _('Forms'),
            _('Instruments'),
        ]

    @staticmethod
    def get_from_translation(translation):
        types = [
            HistoryType.TRACKS,
            HistoryType.ALBUMS,
            HistoryType.ARTISTS,
            HistoryType.COMPOSERS,
            HistoryType.GENRES,
            HistoryType.FORMS,
            HistoryType.INSTRUMENTS,
        ]
        try:
            return types[HistoryType.get_translated_names().index(translation)]
        except ValueError:
            return HistoryType.TRACKS

    def get_track_attribute(self) -> TrackAttribute:
        """Get the corresponding TrackAttribute for this history type."""
        return {
            HistoryType.TRACKS: TrackAttribute.TITLE,
            HistoryType.ALBUMS: TrackAttribute.ALBUM,
            HistoryType.ARTISTS: TrackAttribute.ARTIST,
            HistoryType.COMPOSERS: TrackAttribute.COMPOSER,
            HistoryType.GENRES: TrackAttribute.GENRE,
            HistoryType.FORMS: TrackAttribute.FORM,
            HistoryType.INSTRUMENTS: TrackAttribute.INSTRUMENT
        }[self]

class ProtectedActions(Enum):
    """Enumeration of actions that can be password protected."""
    RUN_SEARCH = "run_search"
    VIEW_LIBRARY = "view_library"
    VIEW_HISTORY = "view_history"
    EDIT_COMPOSERS = "edit_composers"
    EDIT_SCHEDULES = "edit_schedules"
    EDIT_EXTENSIONS = "edit_extensions"
    EDIT_PLAYLISTS = "edit_playlists"
    EDIT_FAVORITES = "edit_favorites"
    DELETE_MEDIA = "delete_media"
    EDIT_CONFIGURATION = "edit_configuration"
    START_APPLICATION = "start_application"
    ACCESS_ADMIN = "access_admin"
    
    @staticmethod
    def get_action(action_name: str):
        """Get the ProtectedActions enum value for a given action name."""
        try:
            return ProtectedActions(action_name.lower().replace(" ", "_"))
        except ValueError:
            return None

    def get_description(self):
        """Get the user-friendly description for this action."""
        descriptions = {
            ProtectedActions.RUN_SEARCH: _("Run Search"),
            ProtectedActions.VIEW_LIBRARY: _("View Library"),
            ProtectedActions.VIEW_HISTORY: _("View History"),
            ProtectedActions.EDIT_COMPOSERS: _("Edit Composers"),
            ProtectedActions.EDIT_SCHEDULES: _("Edit Schedules"),
            ProtectedActions.EDIT_EXTENSIONS: _("Edit Extensions"),
            ProtectedActions.EDIT_PLAYLISTS: _("Edit Playlists"),
            ProtectedActions.EDIT_FAVORITES: _("Edit Favorites"),
            ProtectedActions.DELETE_MEDIA: _("Delete Media"),
            ProtectedActions.EDIT_CONFIGURATION: _("Edit Configuration"),
            ProtectedActions.START_APPLICATION: _("Start Application"),
            ProtectedActions.ACCESS_ADMIN: _("Access Password Administration")
        }
        return descriptions.get(self, self.value)

