import argparse
from copy import deepcopy
import time
import traceback

from utils.globals import Globals # must import first
from ops.muse import Muse
from ops.playback import Playback
from ops.playback_config import PlaybackConfig
from ops.run_config import RunConfig
from ops.workflow import WorkflowPrompt
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

prompt_list = [
]


class Run:
    def __init__(self, args, song_text_callback=None):
        self.id = str(time.time())
        self.is_complete = False
        self.is_cancelled = False
        self.args = args
        self.editing = False
        self.switching_params = False
        self.last_config = None
        self.song_text_callback = song_text_callback
        self.playback = None
        self.muse = Muse(self.args)

    def is_infinite(self):
        return self.args.total == -1

    def next(self):
        self.playback.next()

    def pause(self):
        self.playback.pause()

    def run(self, config):
        print(config)
        # confirm_text = f"\n\nPrompt: \"{config.positive}\" (y/n/r/m/n/e/s/[space to quit]): "
        confirm = "y" # if Globals.SKIP_CONFIRMATIONS else input(confirm_text)
        self.switching_params = False

        if confirm.lower() == " ": # go to next workflow / redo file
            return None
        elif confirm.lower() != "y":
            return

        if self.last_config and config == self.last_config:
            print("\n\nConfig matches last config. Please modify it or quit.")
            # if Globals.SKIP_CONFIRMATIONS:
            #     raise Exception("Invalid state - must select an auto-modifiable config option if using auto run.")
            # else:
            return

#        if config.prompts_match(self.last_config) or config.validate():
        self.playback.run()

        self.last_config = deepcopy(self.playback._playback_config)


    def do_workflow(self, workflow):
        config = PlaybackConfig(self.args)
        self.playback = Playback(config, self.song_text_callback, self)
        self.editing = False
        self.switching_params = False
        self.last_config = None
        count = 0

        try:
            while not self.is_cancelled:
                self.run(config)
                if self.last_config is None:
                    return
                count += 1
                if self.args.total:
                    if self.args.total > -1 and count == self.args.total:
                        print(f"Reached maximum requested iterations: {self.args.total}")
                        if self.song_text_callback is not None:
                            self.song_text_callback(count, self.args.total)
                        return
                    else:
                        if self.args.total == -1:
                            print("Running until cancelled or total iterations reached")
                        else:
                            print(f"On iteration {count} of {self.args.total} - continuing.")
                        if self.song_text_callback is not None:
                            self.song_text_callback(count, self.args.total)
                if True: # self.args.auto_run:
                    sleep_time = config.maximum_plays()
                    sleep_time *= Globals.DELAY_TIME_SECONDS
                    print(f"Sleeping for {sleep_time} seconds.")
                    while sleep_time > 0 and not self.is_cancelled:
                        sleep_time -= 1
                        time.sleep(1)
        except KeyboardInterrupt:
            pass


    def load_and_run(self):
        # if self.args.auto_run:
        #     print("Auto-run mode set.")
        # print("Running prompt mode: " + str(self.args.prompter_config.prompt_mode))

        workflow_tags = self.args.workflow_tag.split(",")
        for workflow_tag in workflow_tags:
            if self.is_cancelled:
                break
            workflow = WorkflowPrompt.setup_workflow(workflow_tag)
            try:
                self.do_workflow(workflow)
            except Exception as e:
                print(e)
                traceback.print_exc()

    def execute(self):
        self.is_complete = False
        self.is_cancelled = False
        # Globals.SKIP_CONFIRMATIONS = self.args.auto_run
        self.load_and_run()
        self.is_complete = True

    def cancel(self):
        print("Canceling...")
        self.is_cancelled = True
        self.playback.next()

    def open_text(self):
        assert self.playback is not None
        song_text_filepath = self.playback.get_song_text_file()
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
