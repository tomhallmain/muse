from enum import Enum
import os

from utils.config import config

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
    MKV = 'MKV'
    MP4 = 'MP4'
    MOV = 'MOV'
    WEBM = 'WEBM'
    FLV = 'FLV'
    AVI = 'AVI'
    WMV = 'WMV'
    VOB = 'VOB'
    MPG = 'MPG'
    ASF = 'ASF'
    MP3 = 'MP3'
    OGG = 'OGG'
    AAC = 'AAC'
    FLAC = 'FLAC'
    ALAC = 'ALAC'
    WAV = 'WAV'
    AIFF = 'AIFF'
    TTA = 'TTA'
    M4A = 'M4A'
    MP2 = 'MP2'
    MP1 = 'MP1'
    AU = 'AU'
    S3M = 'S3M'
    IT = 'IT'
    XM = 'XM'
    MOD = 'MOD'
    MIDI = 'MIDI'
    MID = 'MID'
    WMA = 'WMA'
    OGG_OPUS = 'OGG_OPUS'
    WEBM_VP8 = 'WEBM_VP8'
    OPUS = 'OPUS'

    @classmethod
    def is_media_filetype(cls, filename):
        f = filename.upper()
        for e in cls:
            if f.endswith(e.value):
                return True
        return False

class WorkflowType(Enum):
    RANDOM = 'RANDOM'
    SEQUENCE = 'SEQUENCE'

