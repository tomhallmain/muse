import argparse
from copy import deepcopy
import time
import traceback

from library_data.library_data import LibraryData
from muse.muse import Muse
from muse.playback import Playback
from muse.playback_config import PlaybackConfig
from muse.run_config import RunConfig
from muse.schedules_manager import ScheduledShutdownException
from utils.config import config
from utils.ffmpeg_handler import FFmpegHandler
from utils.temp_dir import TempDir
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class Run:
    def __init__(self, args, callbacks=None):
        self.id = str(time.time())
        self.is_started = False
        self.is_complete = False
        self.is_cancelled = False
        self.args = args
        self.last_config = None
        self.callbacks = callbacks
        self.playback = None
        self.library_data = None if args.placeholder else LibraryData(callbacks)
        self.muse = Muse(self.args, self.library_data)

    def is_infinite(self):
        return self.args.total == -1

    def is_placeholder(self):
        return self.args.placeholder

    def next(self):
        self.get_playback().next()

    def next_grouping(self):
        self.get_playback().next_grouping()

    def pause(self):
        self.get_playback().pause()
    
    def get_playback(self):
        if self.playback is None:
            raise Exception("Playback was not initalized.")
        return self.playback

    def get_library_data(self):
        if self.library_data is None:
            self.library_data = LibraryData(self.callbacks)
        return self.library_data

    def switch_extension(self):
        if self.args.extend:
            self.get_library_data().reset_extension()

    def run(self, playback_config):
        # Handle extension thread based on extension setting
        if config.enable_library_extender:
            if self.args.extend:
                self.muse.start_extensions_thread(initial_sleep=True, overwrite_cache=self.args.overwrite)
            else:
                # Close and don't restart extension thread if it's running and extension is disabled
                self.get_library_data().reset_extension(restart_thread=False)
        
        Utils.log(playback_config)
        if self.last_config and playback_config == self.last_config:
            Utils.log("\n\nConfig matches last config. Please modify it or quit.")
            return

        try:
            self.is_started = True
            self.get_playback().run()
            FFmpegHandler.cleanup_cache()
            TempDir.cleanup()
        except ScheduledShutdownException as e:
            FFmpegHandler.cleanup_cache()
            TempDir.cleanup()
            if self.callbacks is not None:
                print("Shutting down main thread! Good-bye.")
                self.callbacks.shutdown_callback()
        except Exception as e:
            FFmpegHandler.cleanup_cache()
            TempDir.cleanup()
            self.get_library_data().reset_extension()
            raise e

        self.last_config = deepcopy(self.get_playback()._playback_config)

    def do_workflow(self):
        playback_config = PlaybackConfig(args=self.args, data_callbacks=self.library_data.data_callbacks)
        self.playback = Playback(playback_config, self.callbacks, self)
        self.last_config = None

        try:
            self.run(playback_config)
        except KeyboardInterrupt:
            pass

    def load_and_run(self):
        try:
            self.do_workflow()
        except Exception as e:
            Utils.log(e)
            traceback.print_exc()

    def execute(self):
        self.is_complete = False
        self.is_cancelled = False
        self.load_and_run()
        self.is_complete = True

    def cancel(self):
        Utils.log("Canceling...")
        self.is_cancelled = True
        self.get_playback().next()

    def open_text(self):
        song_text_filepath = self.get_playback().get_track_text_file()
        Utils.open_file(song_text_filepath)

    def get_current_track(self):
        return self.get_playback().track

    def get_current_track_artwork(self):
        return self.get_playback().get_current_track_artwork()


def main(args):
    run = Run(args)
    run.execute()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--auto-run", action="store_true")
    parser.add_argument("-t", "--total", type=int, default=100)
    args = parser.parse_args()
    main(RunConfig(args))
