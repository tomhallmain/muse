import argparse
from copy import deepcopy
import time
import traceback

from library_data.library_data import LibraryData
from muse.muse import Muse
from muse.playback import Playback
from muse.playback_config import PlaybackConfig
from muse.run_config import RunConfig
from muse.workflow import WorkflowPrompt
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class Run:
    def __init__(self, args, callbacks=None):
        self.id = str(time.time())
        self.is_complete = False
        self.is_cancelled = False
        self.args = args
        self.editing = False
        self.switching_params = False
        self.last_config = None
        self.callbacks = callbacks
        self.playback = None
        self.muse = Muse(self.args)
        self.library_data = LibraryData(callbacks)

    def is_infinite(self):
        return self.args.total == -1

    def next(self):
        self.playback.next()

    def pause(self):
        self.playback.pause()

    def switch_extension(self):
        if self.args.extend:
            self.library_data.reset_extension()

    def run(self, playback_config):
        if config.enable_library_extender and self.args.extend:
            self.library_data.start_extensions_thread()
        Utils.log(playback_config)
        self.switching_params = False
        if self.last_config and playback_config == self.last_config:
            Utils.log("\n\nConfig matches last config. Please modify it or quit.")
            return

        try:
            self.playback.run()
        except Exception as e:
            self.library_data.reset_extension()
            raise e

        self.last_config = deepcopy(self.playback._playback_config)


    def do_workflow(self, workflow):
        playback_config = PlaybackConfig(self.args)
        self.playback = Playback(playback_config, self.callbacks, self)
        self.editing = False
        self.switching_params = False
        self.last_config = None

        try:
            self.run(playback_config)
        except KeyboardInterrupt:
            pass


    def load_and_run(self):
        # if self.args.auto_run:
        #     Utils.log("Auto-run mode set.")
        # Utils.log("Running prompt mode: " + str(self.args.prompter_config.prompt_mode))

        workflow_tags = self.args.workflow_tag.split(",")
        for workflow_tag in workflow_tags:
            if self.is_cancelled:
                break
            workflow = WorkflowPrompt.setup_workflow(workflow_tag)
            try:
                self.do_workflow(workflow)
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
        self.playback.next()

    def open_text(self):
        assert self.playback is not None
        song_text_filepath = self.playback.get_track_text_file()
        Utils.open_file(song_text_filepath)

def main(args):
    run = Run(args)
    run.execute()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--auto-run", action="store_true")
    parser.add_argument("-t", "--total", type=int, default=100)
    args = parser.parse_args()
    main(RunConfig(args))
