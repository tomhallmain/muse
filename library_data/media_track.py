import glob
import os
import random
import re
import subprocess
from time import sleep

# from ops.artists import Artists
from library_data.composer import composers_data
from library_data.form import forms_data
from library_data.instrument import instruments_data
from utils.config import config
from utils.temp_dir import TempDir
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

has_imported_music_tag = False
try:
    import music_tag
    has_imported_music_tag = True
except ImportError as e:
    Utils.log_yellow("No music tag support: %s" % str(e))

has_imported_mutagen = False
try:
    from mutagen import File
    from mutagen.mp4 import MP4Cover
    has_imported_mutagen = True
except ImportError as e:
    Utils.log_yellow("No mutagen (album artwork) support: %s" % str(e))

from pymediainfo import MediaInfo

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

            try:
                music_tag_wrapper = music_tag.load_file(filepath)
                for k in music_tag_wrapper.__dict__["tag_map"].keys():
                    if not k in MediaTrack.music_tag_ignored_tags and not k.startswith("#"):
                        value = music_tag_wrapper[k].first
                        if value is not None:
                            try:
                                setattr(self, k, value)
                            except Exception:
                                pass
                if self.title is None and self.tracktitle is not None:
                    self.title = str(self.tracktitle)
                if self.artist is None and self.albumartist is not None:
                    self.artist = str(self.albumartist)
                length_value = music_tag_wrapper["#length"].first
                if length_value is not None:
                    self.length = float(length_value)
            except Exception as e:
                pass
                # Utils.log(f"Failed to gather track details for track {self.title}")

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
                Utils.log_debug("Could not find song file path: " + self.filepath)
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
        if self.mean_volume < 200:
            args = ["ffmpeg", "-i", self.filepath, "-af", "volumedetect", "-f", "null", "/dev/null"]
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output, _ = process.communicate()
            mean_volume_tag = "] mean_volume: "
            max_volume_tag = "] max_volume: "
            for line in output.decode("utf-8", errors="ignore").split("\n"):
                if mean_volume_tag in line:
                    self.mean_volume = float(line[line.index(mean_volume_tag)+len(mean_volume_tag):-3].strip())
                if max_volume_tag in line:
                    self.max_volume = float(line[line.index(max_volume_tag)+len(max_volume_tag):-3].strip())
        return self.mean_volume, self.max_volume

    def open_track_location(self):
        Utils.open_file_location(self.filepath)

    def detect_silence_times(self, noise_threshold=0.001, duration=2):
        # TODO double check that parts at the end aren't being missed (they probably are)
        silence_times = []
        args  = ["ffmpeg", "-i", self.filepath, "-af", f"silencedetect=n={noise_threshold}:d={duration}", "-f", "null", "/dev/null"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output, _ = process.communicate()
        silence_interval = [0.0]
        for line in output.split("\n"):
            # print(line)
            if "silencedetect @" in line and "] " in line:
                # print("found silence")
                if len(silence_interval) == 0 or (len(silence_interval) == 1 and silence_interval[0] == 0.0):
                    if "silence_start: " in line:
                        _, text = line.split("] ")
                        value = float(re.sub(MediaTrack.non_numeric_chars, "", text[len("silence_start: "):]))
                        if len(silence_interval) == 0 or value > 0.5:
                            silence_interval.append(value)
                            if len(silence_interval) == 2:
                                # Grab the part from the start of track to the first detected
                                # the duration of the first part should be equal to the first detected silence.
                                silence_interval.append(silence_interval[1])
                                silence_times.append(list(silence_interval))
                                silence_interval.clear()
                                # set up the next interval
                                silence_interval.append(value)
                elif "silence_end: " in line:
                    # print("found silence end")
                    _, text = line.split("] ")
                    if " | " in line:
                        end_text, duration_text = text.split(" | ")
                    else:
                        end_text = text
                        duration_text = ""
                    end_value = re.sub(MediaTrack.non_numeric_chars, "", end_text[len("silence_end: "):])
                    silence_interval.append(float(end_value))
                    if duration_text != "":
                        duration_value = re.sub(MediaTrack.non_numeric_chars, "", duration_text[len("silence_duration: "):])
                        silence_interval.append(float(duration_value))
                    silence_times.append(list(silence_interval))
                    print(silence_times)
                    silence_interval.clear()
        return silence_times

    def extract_non_silent_track_parts(self, select_random_track_part=True):
        # TODO pass parent track properties to the split track MediaTrack objects
        silence_times = self.detect_silence_times()
        if len(silence_times) == 0:
            Utils.log_yellow("No silence detected, returning original track")
            return None
        Utils.log(f"Silence times: {silence_times}")
        track_paths = []
        if select_random_track_part:
            idx = random.randint(1, len(silence_times))
            track_anchors = silence_times[idx-1]
            track_path = self.get_track_part_path(start=track_anchors[0], end=track_anchors[1], idx=idx, total=len(silence_times))
            track_paths.append(MediaTrack(track_path, parent_filepath=self.filepath))
        else:
            for idx in range(len(silence_times)):
                track_anchors = silence_times[idx]
                track_path = self.get_track_part_path(start=track_anchors[0], end=track_anchors[1], idx=idx+1, total=len(silence_times))
                track_paths.append(MediaTrack(track_path, parent_filepath=self.filepath))
        return track_paths

    def get_track_part_path(self, start=-1, end=-1, idx=-1, total=-1):
        if start == -1 or end == -1 or start > end:
            raise Exception(f"Invalid start and end values provided for get_track_part_path: {start}, {end}")
        if idx == -1 or total == -1:
            temp_basename = f"{self.title} part.{self.ext}"
        else:
            temp_basename = f"{self.title} ({idx}-{total}){self.ext}"
        start_time_str = Utils.get_sexagesimal_time_str(start)
        end_time_str = Utils.get_sexagesimal_time_str(end)
        Utils.log(f"Creating track part {idx} out of {total} with anchors start={start}, end={end}")
        temp_filepath = TempDir.get().get_filepath(temp_basename)
        args  = ["ffmpeg", "-i", self.filepath, "-ss", start_time_str, "-to", end_time_str, "-c:a", "copy", temp_filepath]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output, _ = process.communicate()
        # for line in output.split("\n"):
        #     print(line)
        return temp_filepath

    def set_track_length(self, length_seconds=None):
        if length_seconds is not None:
            self.length = float(length_seconds)
            return self.length
        # TODO ff-executables can't handle special characters in filepaths
        if MediaTrack.ffprobe_available is None:
            MediaTrack.ffprobe_available = Utils.executable_available("ffprobe")
        if MediaTrack.ffprobe_available:
            args = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", self.filepath]
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output, _ = process.communicate()
            try:
                for line in output.split("\n"):
                    self.length = float(line[:-1])
                    return self.length
            except Exception as e:
                print(e)
        else:
            args = ["ffmpeg", "-i", self.filepath]
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = p.communicate()
            try:
                for line in stderr.split("\n"):
                    if "Duration: " in line and ", start:" in line:
                        duration_value = line[line.find("Duration: ") + len("Duration: "):line.find(", start:")]
                        sexagesimal_time_vals = duration_value.split(":")
                        duration_seconds = int(sexagesimal_time_vals[0]) * 3600 + int(sexagesimal_time_vals[1]) * 60 + float(sexagesimal_time_vals[2])
                        self.length = duration_seconds
                        return self.length
            except Exception as e:
                print(e)
        Utils.log_red(f"Failed to get track length: {self.filepath}")
        return self.length

    def get_track_length(self):
        if self.length == -1.0:
            length = self.set_track_length()
            Utils.log(f"Track length set: {length} seconds - {self}")
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
        Utils.log(f"Track basename no ext: {song_basename_no_ext}")
        min_string_distance = (999999999, None)
        for basename in txt_basenames:
            basename_no_ext = os.path.splitext(basename)[0]
            string_distance = Utils.string_distance(song_basename_no_ext,  basename_no_ext)
            string_distance_dict[basename] = string_distance
            Utils.log(f"Txt basename no ext: {basename_no_ext}, string distance: {string_distance}")
            if min_string_distance[0] > string_distance:
                min_string_distance = (string_distance, basename)
        if min_string_distance[1] is not None and min_string_distance[0] < 30:
            return os.path.join(dirname,  min_string_distance[1])
        raise Exception(f"No matching text file found for track: {self.title}")

    def get_track_details(self):
        if self.album is not None and self.album.strip() != "":
            if self.artist is not None and self.artist.strip() != "":
                return f"{self.readable_artist()} - {self.readable_title()} - {self.readable_album()}"
            return f"{self.readable_title()} - {self.readable_album()}"            
        return self.readable_title()

    def get_is_video(self):
        if self.is_video is None:
            self.is_video = has_video_stream(self.filepath)
        return self.is_video

    def get_album_artwork(self):
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
                        Utils.log("found artwork in MP4Cover mutagen tag type.")
                        break
                if self.artwork is None:
                    self.artwork = _file.tags['APIC:'].data
                    Utils.log("found artwork by accessing APIC frame")
            except Exception as e:
                Utils.log_yellow(f"Album artwork not found: {e}")
            if self.artwork is None:
                return None
        try:
            # write artwork to new image
            return TempDir.get().add_file('image.jpg', file_content=self.artwork, write_flags='wb')
        except Exception as e:
            Utils.log_red(f"Could not write album artwork to temp file: {e}")
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


