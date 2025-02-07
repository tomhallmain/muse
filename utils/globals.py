from enum import Enum
import os

from utils.config import config
from utils.translations import I18N

_ = I18N._


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
            self.RANDOM: 'recently_played_filepaths',
            self.SEQUENCE: None,
            self.ALBUM_SHUFFLE: 'recently_played_albums',
            self.ARTIST_SHUFFLE: 'recently_played_artists',
            self.COMPOSER_SHUFFLE: 'recently_played_composers',
            self.GENRE_SHUFFLE: 'recently_played_genres',
            self.FORM_SHUFFLE: 'recently_played_forms',
            self.INSTRUMENT_SHUFFLE: 'recently_played_instruments'
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

