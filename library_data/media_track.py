"""Media track management for the Muse application."""

from datetime import datetime
import glob
import os
import re
from time import sleep
import threading
import traceback

from pymediainfo import MediaInfo

from library_data.composer import composers_data
from library_data.form import forms_data
from library_data.instrument import instruments_data
from utils.config import config
from utils.ffmpeg_handler import FFmpegHandler
from utils.logging_setup import get_logger
from utils.temp_dir import TempDir
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

# Get logger for this module
logger = get_logger(__name__)

# Optional third party imports
try:
    import music_tag
    MUSIC_TAG_AVAILABLE = True
except ImportError as e:
    MUSIC_TAG_AVAILABLE = False
    logger.warning("No music tag support: %s" % str(e))

try:
    from mutagen import File
    from mutagen.mp4 import MP4Cover
    MUTAGEN_AVAILABLE = True
except ImportError as e:
    MUTAGEN_AVAILABLE = False
    logger.warning("No mutagen (album artwork) support: %s" % str(e))



def has_video_stream(file_path):
    media_info = MediaInfo.parse(file_path)
    for track in media_info.tracks:
        if track.track_type == "Video":
            return True
    return False

"""
See music-tag README: https://github.com/KristoforMaynard/music-tag

iTunes M4A example tag map:
{'#bitrate': TAG_MAP_ENTRY(getter='bitrate', setter=<function setter_not_implemented>, remover=None, type=<class 'int'>, sanitizer=None),
 '#bitspersample': TAG_MAP_ENTRY(getter='bits_per_sample', setter=<function setter_not_implemented>, remover=None, type=<class 'int'>, sanitizer=None),
 '#channels': TAG_MAP_ENTRY(getter='channels', setter=<function setter_not_implemented>, remover=None, type=<class 'int'>, sanitizer=None),
 '#codec': TAG_MAP_ENTRY(getter='codec', setter=<function setter_not_implemented>, remover=None, type=<class 'str'>, sanitizer=None),
 '#length': TAG_MAP_ENTRY(getter='length', setter=<function setter_not_implemented>, remover=None, type=<class 'float'>, sanitizer=None),
 '#samplerate': TAG_MAP_ENTRY(getter='sample_rate', setter=<function setter_not_implemented>, remover=None, type=<class 'int'>, sanitizer=None),
 'album': TAG_MAP_ENTRY(getter='©alb', setter='©alb', remover=None, type=<class 'str'>, sanitizer=None),
 'albumartist': TAG_MAP_ENTRY(getter='aART', setter='aART', remover=None, type=<class 'str'>, sanitizer=None),
 'artist': TAG_MAP_ENTRY(getter='©ART', setter='©ART', remover=None, type=<class 'str'>, sanitizer=None),
 'artwork': TAG_MAP_ENTRY(getter=<function get_artwork>, setter=<function set_artwork>, remover=None, type=<class 'music_tag.file.Artwork'>, sanitizer=None),
 'comment': TAG_MAP_ENTRY(getter='©cmt', setter='©cmt', remover=None, type=<class 'str'>, sanitizer=None),
 'compilation': TAG_MAP_ENTRY(getter='cpil', setter='cpil', remover=None, type=<class 'bool'>, sanitizer=<function sanitize_bool>),
 'composer': TAG_MAP_ENTRY(getter='©wrt', setter='©wrt', remover=None, type=<class 'str'>, sanitizer=None),
 'discnumber': TAG_MAP_ENTRY(getter=<function get_discnum>, setter=<function set_discnum>, remover=None, type=<class 'int'>, sanitizer=None),
 'genre': TAG_MAP_ENTRY(getter='©gen', setter='©gen', remover=None, type=<class 'str'>, sanitizer=None),
 'isrc': TAG_MAP_ENTRY(getter=<function Mp4File.<lambda>>, setter=<function Mp4File.<lambda>>, remover='----:com.apple.iTunes:ISRC', type=<class 'str'>, sanitizer=None),
 'lyrics': TAG_MAP_ENTRY(getter='©lyr', setter='©lyr', remover=None, type=<class 'str'>, sanitizer=None),
 'totaldiscs': TAG_MAP_ENTRY(getter=<function get_totaldiscs>, setter=<function set_totaldiscs>, remover=None, type=<class 'int'>, sanitizer=None),
 'totaltracks': TAG_MAP_ENTRY(getter=<function get_totaltracks>, setter=<function set_totaltracks>, remover=None, type=<class 'int'>, sanitizer=None),
 'tracknumber': TAG_MAP_ENTRY(getter=<function get_tracknum>, setter=<function set_tracknum>, remover=None, type=<class 'int'>, sanitizer=None),
 'tracktitle': TAG_MAP_ENTRY(getter='©nam', setter='©nam', remover=None, type=<class 'str'>, sanitizer=None),
 'year': TAG_MAP_ENTRY(getter='©day', setter='©day', remover=None, type=<class 'int'>, sanitizer=<function sanitize_year>)}

Look at "mfile" info on music_tag.mp4.Mp4File object as well.
dict_keys(['tag_aliases', 'tag_map', 'resolvers', 'singular_keys', 'filename', 'mfile'])
"""

class MediaTrack:
    music_tag_ignored_tags = ['comment', 'isrc', 'lyrics', 'artwork']
    non_numeric_chars = re.compile(r"[^0-9\.\-]+")
    ffprobe_available = None

    # Class-level error collection
    _collected_errors = []
    _error_lock = threading.Lock()

    @classmethod
    def collect_error(cls, error_msg, stack_trace=None):
        with cls._error_lock:
            cls._collected_errors.append((error_msg, stack_trace))

    @classmethod
    def clear_errors(cls):
        with cls._error_lock:
            cls._collected_errors.clear()

    @classmethod
    def write_errors_to_file(cls, filename="media_track_errors.log"):
        with cls._error_lock:
            if not cls._collected_errors:
                return
            errors_to_write = cls._collected_errors.copy()
            cls._collected_errors.clear()  # Clear directly instead of calling clear_errors()
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"MediaTrack Errors - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                for error_msg, stack_trace in errors_to_write:
                    f.write(f"{error_msg}\n")
                    if stack_trace:
                        f.write(f"{stack_trace}\n")
                    f.write("\n")
            logger.info(f"Wrote {len(errors_to_write)} errors to {filename}")
        except Exception as e:
            logger.error(f"Failed to write errors to file: {str(e)}")

    def _try_media_info_fallback(self, filepath):
        """Attempt to get basic metadata using MediaInfo as a fallback."""
        try:
            media_info = MediaInfo.parse(filepath)
            for track in media_info.tracks:
                # Check for any track that has audio data
                if hasattr(track, 'duration') and track.duration:
                    if not self.title and hasattr(track, 'title') and track.title:
                        self.title = track.title
                    if not self.artist and hasattr(track, 'performer') and track.performer:
                        self.artist = track.performer
                    if not self.album and hasattr(track, 'album') and track.album:
                        self.album = track.album
                    if self.length == -1.0:
                        self.length = float(track.duration) / 1000  # Convert ms to seconds
                    
                    # Additional MediaInfo attributes
                    if hasattr(track, 'composer') and track.composer and not self.composer:
                        self.composer = track.composer
                    if hasattr(track, 'genre') and track.genre and not self.genre:
                        self.genre = track.genre
                    if hasattr(track, 'track_name') and track.track_name and not self.tracktitle:
                        self.tracktitle = track.track_name
                    if hasattr(track, 'track_name_position') and track.track_name_position and self.tracknumber == -1:
                        try:
                            self.tracknumber = int(track.track_name_position)
                        except (ValueError, TypeError):
                            pass
                    if hasattr(track, 'track_name_total') and track.track_name_total and self.totaltracks == -1:
                        try:
                            self.totaltracks = int(track.track_name_total)
                        except (ValueError, TypeError):
                            pass
                    if hasattr(track, 'part') and track.part and self.discnumber == -1:
                        try:
                            self.discnumber = int(track.part)
                        except (ValueError, TypeError):
                            pass
                    if hasattr(track, 'part_total') and track.part_total and self.totaldiscs == -1:
                        try:
                            self.totaldiscs = int(track.part_total)
                        except (ValueError, TypeError):
                            pass
                    if hasattr(track, 'recorded_date') and track.recorded_date and not self.year:
                        try:
                            # Try to extract year from recorded date
                            date_str = str(track.recorded_date)
                            if len(date_str) >= 4:
                                self.year = int(date_str[:4])
                        except (ValueError, TypeError):
                            pass
        except FileNotFoundError:
            error_msg = f"File not found: {filepath}. This may be due to an outdated cache. Consider refreshing the cache in the UI."
            logger.error(error_msg)
            self.__class__.collect_error(error_msg)
            raise
        except Exception as e2:
            error_msg = f"Failed to get basic info using MediaInfo for {filepath}: {str(e2)}"
            stack_trace = traceback.format_exc()
            logger.error(f"{error_msg}\nMediaInfo error details:\n{stack_trace}")
            self.__class__.collect_error(error_msg, stack_trace)

    def _get_year_from_media_info(self, filepath):
        try:
            media_info = MediaInfo.parse(filepath)
            for track in media_info.tracks:
                if hasattr(track, 'recorded_date') and track.recorded_date:
                    date_str = str(track.recorded_date)
                    if len(date_str) >= 4:
                        self.year = int(date_str[:4])
                        return
                if hasattr(track, 'original_date') and track.original_date:
                    date_str = str(track.original_date)
                    if len(date_str) >= 4:
                        self.year = int(date_str[:4])
                        return
        except Exception as e:
            logger.error(f"Failed to get year from MediaInfo: {str(e)}")

    def _try_music_tag_load(self, filepath):
        try:
            music_tag_wrapper = music_tag.load_file(filepath)
        except FileNotFoundError:
            error_msg = f"File not found: {filepath}. This may be due to an outdated cache. Consider refreshing the cache in the UI."
            logger.warning(error_msg)
            self.__class__.collect_error(error_msg)
            raise
        except NotImplementedError as e:
            stack_trace = None
            if "Mutagen type" in str(e):
                error_msg = f"Unsupported file format for metadata reading: {filepath}. The file format is not supported by the metadata library."
            else:
                error_msg = f"Failed to load metadata for {filepath}: {str(e)}"
                stack_trace = traceback.format_exc()
            logger.warning(error_msg)
            self.__class__.collect_error(error_msg, stack_trace)
            self._try_media_info_fallback(filepath)
            return
        except Exception as e:
            error_msg = f"Failed to load metadata for {filepath}: {str(e)}"
            logger.warning(error_msg)
            self.__class__.collect_error(error_msg, traceback.format_exc())
            self._try_media_info_fallback(filepath)
            return

        # Verify tag_map exists and is a dictionary
        if not hasattr(music_tag_wrapper, "tag_map") or not isinstance(music_tag_wrapper.tag_map, dict):
            logger.warning(f"Invalid music_tag wrapper for {filepath}: missing or invalid tag_map")
            self._try_media_info_fallback(filepath)
            return

        # Track failures in tag processing
        failure_count = 0
        max_failures = 3  # Adjust this threshold as needed

        for k in music_tag_wrapper.tag_map.keys():
            if not k in MediaTrack.music_tag_ignored_tags and not k.startswith("#"):
                try:
                    value = music_tag_wrapper[k].first
                    if value is not None:
                        setattr(self, k, value)
                except Exception as e:
                    failure_count += 1
                    if k == 'year':
                        self._get_year_from_media_info(filepath)
                    else:
                        logger.warning(f"Failed to load {k} for {filepath}: {str(e)}")
                        if failure_count >= max_failures:
                            logger.warning(f"Too many tag failures ({failure_count}) for {filepath}, falling back to MediaInfo")
                            self._try_media_info_fallback(filepath)
                            return

        if self.title is None and self.tracktitle is not None:
            self.title = str(self.tracktitle)
        if self.artist is None and self.albumartist is not None:
            self.artist = str(self.albumartist)
        try:
            length_value = music_tag_wrapper["#length"].first
            if length_value is not None:
                self.length = float(length_value)
        except Exception as e:
            logger.warning(f"Failed to load length for {filepath}: {str(e)}")

    def __init__(self, filepath, parent_filepath=None):
        self.filepath = filepath
        self.parent_filepath = parent_filepath # for split track parts
        self.tracktitle = None
        self.artist = None
        self.album = None
        self.albumartist = None
        self.composer = None
        self.tracknumber = -1
        self.totaltracks = -1
        self.discnumber = -1
        self.totaldiscs = -1
        self.genre = None
        self.year = None
        self.compilation = False
        self.compilation_name = None  # Will be set when compilation is identified
        self.mean_volume = -9999.0
        self.max_volume = -9999.0
        self.length = -1.0
        self.artwork = None
        self.form = None
        self.instrument = None

        # Unused tags:
        # bitrate : 128000
        # codec : mp4a.40.2
        # channels : 2
        # bitspersample : 16
        # samplerate : 44100

        self.searchable_title = None
        self.searchable_album = None
        self.searchable_artist = None
        self.searchable_composer = None
        self.searchable_genre = None
        self._is_extended = False
        self.is_video = None

        if self.filepath is not None and self.filepath != "":
            self.basename = os.path.basename(filepath)
            dirpath1 = os.path.dirname(os.path.abspath(filepath))
            dirpath2 = os.path.dirname(os.path.abspath(dirpath1))
            self.album = os.path.basename(dirpath1)
            if not config.matches_master_directory(dirpath1) and not config.matches_master_directory(dirpath2):
                self.artist = os.path.basename(dirpath2)
            self.title, self.ext = os.path.splitext(self.basename)
            # NOTE there are cases where a group of artists are combined in a single album or a single artist name, and
            # it may be possible to extract the specific artistic name given properties of the track relative to others
            # in the same album
            self.set_track_index()
            self.clean_track_values()

            self._try_music_tag_load(filepath)

            if self.title is not None:
                self.searchable_title = Utils.ascii_normalize(self.title.lower())
            if self.artist is not None:
                self.searchable_artist = Utils.ascii_normalize(self.artist.lower())
            if self.album is not None:
                self.searchable_album = Utils.ascii_normalize(self.album.lower())
            if self.composer is None:
                try:
                    composers = composers_data.get_composers(self)
                    if len(composers) > 0:
                        self.composer = ", ".join(composers)
                except Exception:
                    pass
            if self.composer is not None:
                self.searchable_composer = Utils.ascii_normalize(self.composer.lower())
            if self.genre is not None:
                self.searchable_genre = Utils.ascii_normalize(self.genre.lower())
        else:
            self.basename = None
            self.album = None
            self.artist = None
            self.title = None
            self.ext = None

    def get_parent_filepath(self):
        return self.filepath if self.parent_filepath is None else self.parent_filepath

    def clean_track_values(self):
        self.title = self.clean_track_value(self.title)
        if self.album is not None:
            self.album = self.clean_track_value(self.album)
        if self.artist is not None:
            self.artist = self.clean_track_value(self.artist)

    def clean_track_value(self, track_value):
        cleaned = re.sub(re.compile(" ?\\[[A-Za-z0-9_\\-]*\\]"), "", track_value)  # remove ID strings
        cleaned = re.sub(re.compile("([^_])_ "), "\\1: ", track_value) # Replacing colons in filepaths where they are not allowed
        return cleaned

    def readable_title(self):
        prepped = MediaTrack._prep_track_text(self.title)
        if prepped.strip() == "":
            return _("Unknown title")
        return prepped

    def readable_album(self):
        prepped = MediaTrack._prep_track_text(self.album)
        if prepped.strip() == "":
            return _("Unknown album")
        return prepped

    def readable_artist(self):
        prepped = MediaTrack._prep_track_text(self.artist)
        if prepped.strip() == "":
            return  _("Unknown artist")
        return prepped

    def is_invalid(self):
        if self.basename is None:
            return True
        if not os.path.isfile(self.filepath):
            # Maybe this file is located on an external or network drive and the connection is
            # not stable, so try to check a few times just to be sure.
            attempts = 0
            while attempts < 10:
                sleep(0.2)
                if os.path.isfile(self.filepath):
                    return False
                logger.debug("Could not find song file path: " + self.filepath)
                attempts += 1
            raise Exception("Could not find song file path: " + self.filepath)
        return False

    def set_is_extended(self, is_extended=True):
        self._is_extended = is_extended

    def set_track_index(self):
        # NOTE there may be some cases where the track index is actually a number in the title, need a better way to handle these
        if self.title is not None and len(self.title) > 0 and self.title[0].isdigit():
            maybe_album_index, maybe_track_index, maybe_title = MediaTrack.extract_ints_from_start(self.title)
            if maybe_album_index is not None and maybe_album_index > 0 and maybe_album_index < 15:
                self.discnumber = maybe_album_index
            if maybe_track_index is not None and maybe_track_index > 0 and maybe_track_index < 40:
                self.tracknumber = maybe_track_index
                self.title = maybe_title

    def get_volume(self):
        if self.mean_volume < -200:
            try:
                self.mean_volume, self.max_volume = FFmpegHandler.get_volume(self.filepath)
            except Exception as e:
                if "emoji characters" in str(e):
                    logger.warning(f"Skipping volume analysis for file with special characters: {self.filepath}")
                else:
                    raise # FFMPEG should be catching the other errors
        return self.mean_volume, self.max_volume

    def open_track_location(self):
        Utils.open_file_location(self.filepath)

    def detect_silence_times(self, noise_threshold=0.001, duration=2):
        # TODO double check that parts at the end aren't being missed (they probably are)
        return FFmpegHandler.detect_silence_times(self.filepath, noise_threshold, duration)

    def extract_non_silent_track_parts(self, select_random_track_part=True):
        # TODO pass parent track properties to the split track MediaTrack objects
        track_paths = FFmpegHandler.extract_non_silent_track_parts(
            filepath=self.filepath,
            title=self.title,
            ext=self.ext,
            select_random_track_part=select_random_track_part
        )
        
        # Convert paths to MediaTrack objects, preserving parent filepath
        return [MediaTrack(path, parent_filepath=self.filepath) for path in track_paths] if track_paths else None

    def set_track_length(self, length_seconds=None):
        if length_seconds is not None:
            self.length = float(length_seconds)
            return self.length
        duration = FFmpegHandler.get_duration(self.filepath)
        if duration is not None:
            self.length = duration
        return self.length

    def get_track_length(self):
        if self.length == -1.0:
            length = self.set_track_length()
            logger.info(f"Track length set: {length} seconds - {self}")
        return self.length

    def get_track_text_file(self):
        if self.basename is None:
            return None
        track_basename = self.basename.lower()
        # TODO search in specific dir based on the composer, artist, topic etc.
        dirname = os.path.dirname(self.filepath)
        txt_files = glob.glob(os.path.join(dirname, "*.txt"))
        txt_basenames = []
        for f in txt_files:
            basename = os.path.basename(f).lower()
            if track_basename.startswith(basename):
                return f
            txt_basenames.append(basename)
        for basename in txt_basenames:
            if basename[:-4] in track_basename:
                return os.path.join(dirname,  basename)
        string_distance_dict = {}
        song_basename_no_ext = os.path.splitext(track_basename)[0]
        logger.info(f"Track basename no ext: {song_basename_no_ext}")
        min_string_distance = (999999999, None)
        for basename in txt_basenames:
            basename_no_ext = os.path.splitext(basename)[0]
            string_distance = Utils.string_distance(song_basename_no_ext,  basename_no_ext)
            string_distance_dict[basename] = string_distance
            logger.info(f"Txt basename no ext: {basename_no_ext}, string distance: {string_distance}")
            if min_string_distance[0] > string_distance:
                min_string_distance = (string_distance, basename)
        if min_string_distance[1] is not None and min_string_distance[0] < 30:
            return os.path.join(dirname,  min_string_distance[1])
        raise Exception(f"No matching text file found for track: {self.title}")

    def get_track_details(self):
        if self.album is not None and self.album.strip() != "":
            if self.artist is not None and self.artist.strip() != "":
                return f"{self.readable_title()} - {self.readable_album()} - {self.readable_artist()}"
            return f"{self.readable_title()} - {self.readable_album()}"            
        return self.readable_title()

    def get_is_video(self):
        if self.is_video is None:
            self.is_video = has_video_stream(self.filepath)
        return self.is_video

    def get_album_artwork(self, filename="image"):
        # music-tags libary may have already set this attribute
        if self.artwork is None:
            if self.get_is_video():
                return None
            # mutagen for special cases
            try:
                _file = File(self.filepath) # mutagen
                for k, v in _file.tags.items():
                    if type(v) == list and type(v[0]) == MP4Cover:
                        self.artwork = bytes(v[0])
                        logger.info("found artwork in MP4Cover mutagen tag type.")
                        break
                if self.artwork is None:
                    self.artwork = _file.tags['APIC:'].data
                    logger.info("found artwork by accessing APIC frame")
            except Exception as e:
                logger.warning(f"Album artwork not found: {e}")
            if self.artwork is None:
                return None
        try:
            # write artwork to new image
            if "." not in filename:
                filename += ".jpg" # TODO figure out actual image format
            return TempDir.get().add_file(filename, file_content=self.artwork, write_flags='wb')
        except Exception as e:
            logger.error(f"Could not write album artwork to temp file: {e}")
            return None

    def get_genre(self):
        # TODO - get genre from file somehow
        return None

    def get_form(self):
        if self.form is None:
            # For now, just save the first form found
            forms = forms_data.get_forms(self)
            if len(forms) > 0:
                self.form = forms[0]
            else:
                self.form = ""
        return self.form

    def get_instrument(self):
        if self.instrument is None:
            # For now, just save the first instrument found
            instruments = instruments_data.get_instruments(self)
            if len(instruments) > 0:
                self.instrument = instruments[0]
            else:
                self.instrument = ""
        return self.instrument

    @staticmethod
    def _prep_track_text(text):
        # TODO i18n to detect track language context
        text = re.sub(re.compile(" No. ?([0-9])"), _("Number \\1"), text)
        text = re.sub(re.compile("Nr. ?([0-9])"),  _("Number \\1"), text)
        text = re.sub(re.compile("( |^)TTS( |$)"),   _("\\1text to speech\\2"), text)
        text = re.sub(re.compile("( o| ?O)p. ([0-9])"), _(" Opus \\2"), text)
        # TODO replace foreign-language quotes that the TTS model can't handle with normal quotes
        # NOTE if there is a bracket, it's probably a specific kind of title
        return Utils.remove_ids(text, in_brackets=("[" in text))

    @staticmethod
    def extract_ints_from_start(s):
        maybe_track_index = ""
        counter = 0
        has_seen_space = False
        for c in s:
            if c.isdigit() and not has_seen_space:
                maybe_track_index += c
                counter += 1
            elif c.isalpha() and not has_seen_space:
                # i.e. 3rd Symphony, etc
                maybe_track_index = ""
                counter = 0
                break
            elif counter > 0 and (c == " " or c == "\n" or c == "\t" or c == ":" or c == "_"):
                counter += 1
                has_seen_space = True
            else:
                break

        if counter >= len(s) or len(maybe_track_index) == 0:
            return -1, -1, s

        if (s[counter] == "/" or s[counter] == "-") and len(s) > counter + 2 and s[counter+1].isdigit():
            # Track name form: 1-03 Track three from first CD
            maybe_album_index = int(maybe_track_index)
            _, maybe_track_index, maybe_title = MediaTrack.extract_ints_from_start(s[counter+1:])
            if len(maybe_title) > 0:
                return maybe_album_index, maybe_track_index, maybe_title

        return -1, int(maybe_track_index), str(s[counter:])

    def __str__(self) -> str:
        return str(self.title)

    def __eq__(self, value: object) -> bool:
        return isinstance(value, MediaTrack) and self.filepath == value.filepath

    def __hash__(self):
        return hash(self.filepath)

    def update_metadata(self, metadata):
        """
        Update the track's metadata using music_tag library.
        
        Args:
            metadata (dict): Dictionary containing the metadata to update.
                           Keys should match music_tag's field names.
        
        Returns:
            bool: True if update was successful, False otherwise
        """
        if not MUSIC_TAG_AVAILABLE:
            logger.warning("Cannot update metadata: music_tag library not available")
            return False

        if self.get_is_video():
            logger.warning("Cannot update metadata: track is a video file")
            return False

        try:
            # Validate numeric fields
            year = metadata.get('year')
            if year and not isinstance(year, int):
                try:
                    year = int(year)
                    if year < 0 or year > 9999:
                        logger.warning(f"Invalid year value: {year}")
                        return False
                except ValueError:
                    logger.warning(f"Invalid year format: {year}")
                    return False

            track_number = metadata.get('tracknumber')
            if track_number and not isinstance(track_number, int):
                try:
                    track_number = int(track_number)
                    if track_number < 0:
                        logger.warning(f"Invalid track number: {track_number}")
                        return False
                except ValueError:
                    logger.warning(f"Invalid track number format: {track_number}")
                    return False

            # Load the file with music_tag
            mfile = music_tag.load_file(self.filepath)

            # Handle artwork update if present
            if 'artwork' in metadata:
                try:
                    mfile['artwork'] = metadata['artwork']
                    self.artwork = metadata['artwork']  # Update local cache
                except Exception as e:
                    logger.warning(f"Failed to update artwork: {str(e)}")
                    return False

            # Map our metadata keys to music_tag keys
            tag_mapping = {
                'title': 'tracktitle',
                'album': 'album',
                'artist': 'artist',
                'albumartist': 'albumartist',
                'composer': 'composer',
                'genre': 'genre',
                'year': 'year',
                'tracknumber': 'tracknumber',
                'totaltracks': 'totaltracks',
                'discnumber': 'discnumber',
                'totaldiscs': 'totaldiscs',
                'lyrics': 'lyrics',
                'comment': 'comment'
            }

            # Update each field if it exists in the metadata
            for our_key, tag_key in tag_mapping.items():
                if our_key in metadata and metadata[our_key] is not None:
                    value = metadata[our_key]
                    if value == "" or value == -1:  # Handle empty strings and default numeric values
                        continue
                    try:
                        mfile[tag_key] = value
                    except Exception as e:
                        logger.warning(f"Failed to update {tag_key}: {str(e)}")

            # Save the changes
            mfile.save()

            # Update our local object with the new values
            for our_key, value in metadata.items():
                if hasattr(self, our_key) and value is not None:
                    if value != "" and value != -1:  # Only update if not empty/default
                        setattr(self, our_key, value)

            logger.info(f"Successfully updated metadata for {self.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to update track metadata: {str(e)}")
            return False


