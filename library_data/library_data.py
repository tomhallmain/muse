from enum import Enum
import os
import random
import subprocess

from extensions.library_extender import LibraryExtender
from library_data.composer import composers_data
from muse.playback_config import PlaybackConfig
from muse.run_config import RunConfig
from utils.config import config
from utils.job_queue import JobQueue
from utils.utils import Utils


libary_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
configs_dir = os.path.join(os.path.dirname(libary_dir), 'configs')



def get_playback_config():
    run_config = RunConfig()
    run_config.workflow_tag = "SEQUENCE"
    run_config.directories = list(config.get_subdirectories().keys())
    PlaybackConfig.load_directory_cache()
    return PlaybackConfig(run_config)


class LibraryDataSearch:
    def __init__(self, all, title, artist, composer, album, genre, max_results=200):
        self.all = all
        self.title = title
        self.artist = artist
        self.composer = composer
        self.album = album
        self.genre = genre
        self.max_results = max_results

        self.results = []

    def is_valid(self):
        for field in [self.all, self.title, self.artist, self.composer, self.album, self.genre]:
            if field is not None and len(field) > 0 and field.strip()!= "":
                return True
        return False

    def test(self, audio_track):
        if len(self.results) > self.max_results:
            return None
        if len(self.all) > 0:
            for field in [audio_track.searchable_title, audio_track.searchable_artist, audio_track.searchable_composer, audio_track.searchable_album]:
                if field is not None and self.all in field:
                    self.results.append(audio_track)
                    return True
        if len(self.title) > 0 and audio_track.searchable_title is not None and self.title in audio_track.searchable_title:
            self.results.append(audio_track)
            return True
        if len(self.artist) > 0 and audio_track.searchable_artist is not None and self.artist in audio_track.searchable_artist:
            self.results.append(audio_track)
            return True
        if len(self.composer) > 0 and audio_track.searchable_composer is not None and self.composer in audio_track.searchable_composer:
            self.results.append(audio_track)
            return True
        if len(self.album) > 0 and audio_track.searchable_album is not None and self.album in audio_track.searchable_album:
            self.results.append(audio_track)
            return True
        if len(self.genre) > 0 and audio_track.searchable_genre is not None and self.genre in audio_track.searchable_genre:
            self.results.append(audio_track)
            return True
        return False

    def get_results(self):
        return self.results


class TrackAttribute(Enum):
    TITLE = "title"
    ALBUM = "album"
    ARTIST = "artist"
    COMPOSER = "composer"
    GENRE = "genre"


class LibraryData:
    EXTENSION_QUEUE = JobQueue("Extension queue")

    def __init__(self):
        self.playback_config = get_playback_config()
        self.audio_track_cache = self.playback_config.get_audio_track_list()
        self.composers = composers_data

    def do_search(self, library_data_search):
        if not isinstance(library_data_search, LibraryDataSearch):
            raise TypeError('Library data search must be of type LibraryDataSearch')
        if not library_data_search.is_valid():
            Utils.log_yellow('Invalid search query')
            return library_data_search

        for audio_track in self.audio_track_cache:
            if library_data_search.test(audio_track) is None:
                break

        return library_data_search


    def start_extensions_thread(self):
        Utils.log('Starting extensions thread')
        Utils.start_thread(self._run_extensions, use_asyncio=False)

    def _run_extensions(self):
        Utils.long_sleep(random.randint(200, 1200), "extension thread")
        while True:
            self._extend_by_random_composer()
            sleep_time_minutes = random.randint(40, 80)
            Utils.long_sleep(sleep_time_minutes * 60, "extension thread")

    def _extend_randomly(self):
        Utils.log('Extending randomly')
        pass

    def _extend_by_random_composer(self):
        composer = random.choice(composers_data.get_composer_names())
        Utils.log('Extending by random composer: ' + composer)
        self.extend(value=composer, attr=TrackAttribute.COMPOSER)

    def _extend(self, value="", attr=None, strict=False):
        if attr == TrackAttribute.TITLE:
            self.extend_by_title(value, strict=strict)
        if attr == TrackAttribute.ALBUM:
            self.extend_by_album(value, strict=strict)
        if attr == TrackAttribute.ARTIST:
            self.extend_by_artist(value, strict=strict)
        if attr == TrackAttribute.COMPOSER:
            self.extend_by_composer(value)
        if attr == TrackAttribute.GENRE:
            self.extend_by_genre(value, strict=strict)
        next_job_args = self.EXTENSION_QUEUE.take()
        if next_job_args is not None:
            Utils.long_sleep(300, "extension thread job wait")
            Utils.start_thread(self._extend, use_asyncio=False, args=next_job_args)
        else:
            self.EXTENSION_QUEUE.job_running = False

    def extend(self, value="", attr=None, strict=False):
        args=(value, attr, strict)
        if self.EXTENSION_QUEUE.has_pending() or self.EXTENSION_QUEUE.job_running:
            self.EXTENSION_QUEUE.add(args)
        else:
            self.EXTENSION_QUEUE.job_running = True
            Utils.start_thread(self._extend, use_asyncio=False, args=args)

    def extend_by_title(self, title, strict=False):
        self._simple(title, attr=TrackAttribute.TITLE, strict=None)

    def extend_by_album(self, album, strict=False):
        self._simple(album, attr=TrackAttribute.ALBUM, strict=None)

    def extend_by_artist(self, artist, strict=False):
        # TODO
        self._simple("music by " + artist, attr=TrackAttribute.ARTIST, strict=None)

    def extend_by_composer(self, composer_name):
        composer = composers_data.get_data(composer_name)
        # TODO
        self._simple("music by " + composer_name, attr=TrackAttribute.COMPOSER, strict=composer)

    def extend_by_genre(self, genre, strict=False):
        # TODO
        self._simple("music from the genre " + genre, attr=TrackAttribute.GENRE, strict=None)

    def _simple(self, q, m=6, depth=0, attr=None, strict=None):
        r = self.s(q, m)
        if r is not None and r.i():
            a = r.o()
            b = random.choice(a)
            counter = 0
            failed = False
            for i in a:
                Utils.log("Extension option: " + i.name + " " + i.x())
            while b is None or b.y or (strict and self._strict_test(b, attr, strict)):
                counter += 1
                b = random.choice(a)
                if counter > 10:
                    failed = True
                    break
            if failed:
                if depth > 4:
                    raise Exception(f"Unable to find valid results: {q}")
                self._simple(q, m=m*2, depth=depth+1)
                return
            Utils.log("Selected option: " + b.name + " " + b.x())
            Utils.start_thread(self._delayed, use_asyncio=False, args=(b,))
        else:
            if r is None:
                Utils.log_yellow("Tracking too many requests.")
            else:
                Utils.log_yellow(f'No results found for "{q}"')

    def _strict_test(self, b, attr, strict):
        if attr is None or strict is None:
            raise Exception("No strict test attribute specified")
        if attr == TrackAttribute.COMPOSER:
            for indicator in strict.indicators:
                if indicator.lower() in b.name.lower() or indicator.lower() in b.d.lower():
                    return False
        return True

    def _delayed(self, b):
        Utils.long_sleep(random.randint(1000, 2000), "Extension thread delay wait")
        a = b.da(g=config.directories[0])
        e1 = " Destination: "
        Utils.log(f"extending delayed: {a}")
        e = "[download]"
        p = subprocess.Popen(a, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        o, _ = p.communicate()
        f = "[ffmpeg]"
        _e = None
        _f = None
        for line in o.split("\n"):
            if line.startswith(e + e1):
                _e = line[len(e + e1):]
            if line.startswith(f + e1):
                _f = line[len(f + e1):]
        if _f is None or not os.path.exists(_f):
            Utils.log_yellow("F was not found" if _f is None else "F was found but invalid: " + _f)
            if _e is None or not os.path.exists(_e):
                Utils.log_yellow("E was not found" if _e is None else "E was found but invalid: " + _e)
                raise Exception(f"No output found {b}")
            else:
                _f = _e
        PlaybackConfig.force_extension(_f)

    def s(self, q, x=1):
        Utils.log(f"s: {q}")
        return LibraryExtender.isyMOLB_(q, m=x)

