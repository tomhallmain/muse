import argparse
from copy import deepcopy
import time
import traceback
from typing import Optional, Any

from utils.globals import PlaybackMasterStrategy

from library_data.library_data import LibraryData
from muse.muse import Muse
from muse.playback import Playback
from muse.playback_config import PlaybackConfig
from muse.playback_config_master import PlaybackConfigMaster
from muse.playback_state import PlaybackStateManager
from muse.run_config import RunConfig
from muse.run_context import RunContext, UserAction
from muse.schedules_manager import ScheduledShutdownException
from ui.app_actions import AppActions
from utils.config import config
from utils.ffmpeg_handler import FFmpegHandler
from utils.logging_setup import get_logger
from utils.temp_dir import TempDir
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._
logger = get_logger(__name__)


class Run:
    def __init__(self, args: RunConfig, app_actions: Optional[AppActions] = None) -> None:
        self.id: str = str(time.time())
        self.is_started: bool = False
        self.is_complete: bool = False
        self.args: RunConfig = args
        self.last_config: Optional[PlaybackConfigMaster] = None
        self.app_actions: Optional[AppActions] = app_actions
        self.library_data: Optional[LibraryData] = None if args.placeholder else LibraryData(app_actions)
        self._run_context: RunContext = RunContext()
        self.muse: Muse = Muse(self.args, self.library_data, self._run_context, ui_callbacks=app_actions)
        self._playback: Optional[Playback] = None

    def is_infinite(self) -> bool:
        return self.args.total == -1

    def is_placeholder(self) -> bool:
        return self.args.placeholder

    def next(self) -> None:
        """Skip to the next track."""
        self._run_context.update_action(UserAction.SKIP_TRACK)
        self.get_playback().stop()

    def next_grouping(self) -> None:
        """Skip to the next grouping."""
        self._run_context.update_action(UserAction.SKIP_GROUPING)
        self.get_playback().stop()

    def pause(self) -> None:
        """Pause playback."""
        self._run_context.update_action(UserAction.PAUSE)
        self.get_playback().pause()
    
    def get_playback(self) -> Playback:
        if self._playback is None:
            raise RuntimeError("Playback not initialized")
        return self._playback

    def get_library_data(self) -> LibraryData:
        if self.library_data is None:
            self.library_data = LibraryData(self.app_actions)
        return self.library_data

    def switch_extension(self) -> None:
        if self.args.extend:
            self.get_library_data().reset_extension()

    def run(self, playback_config: PlaybackConfigMaster) -> None:
        # Handle extension thread based on extension setting
        if config.enable_library_extender:
            if self.args.extend:
                self.muse.start_extensions_thread(initial_sleep=True, overwrite_cache=self.args.overwrite)
            else:
                # Close and don't restart extension thread if it's running and extension is disabled
                self.get_library_data().reset_extension(restart_thread=False)
        
        logger.info(playback_config)
        if self.last_config and playback_config == self.last_config:
            logger.info("\n\nConfig matches last config. Please modify it or quit.")
            return

        try:
            self.is_started = True
            # Set the current config in the state manager
            PlaybackStateManager.set_active_config(playback_config)
            self.get_playback().run()
            FFmpegHandler.cleanup_cache()
            TempDir.cleanup()
        except ScheduledShutdownException as e:
            FFmpegHandler.cleanup_cache()
            TempDir.cleanup()
            if self.app_actions is not None:
                logger.warning(f"\n{'='*50}\nSCHEDULED SHUTDOWN: {str(e)}\n{'='*50}\n")
                print("Shutting down main thread! Good-bye.")
                self.app_actions.shutdown_callback()
        except Exception as e:
            FFmpegHandler.cleanup_cache()
            TempDir.cleanup()
            self.get_library_data().reset_extension()
            raise e
        finally:
            # Clear the current config when done
            PlaybackStateManager.clear_active_config()

        self.last_config = deepcopy(self.get_playback()._playback_config)

    def do_workflow(self) -> None:
        if self.args.playback_master_strategy == PlaybackMasterStrategy.PLAYLIST_CONFIG:
            master_config = PlaybackStateManager.get_master_config()
            if master_config and master_config.playback_configs:
                playback_config = master_config
            else:
                raise ValueError(
                    "PLAYLIST_CONFIG strategy selected but no master config set"
                )
        else:
            playback_config = PlaybackConfigMaster(
                playback_configs=[PlaybackConfig(
                    args=self.args,
                    data_callbacks=self.get_library_data().data_callbacks,
                )]
            )

        self._playback = Playback(playback_config, self.app_actions, self)
        self.last_config = None

        try:
            self.run(playback_config)
        except KeyboardInterrupt:
            pass

    def load_and_run(self) -> None:
        try:
            self.do_workflow()
        except Exception as e:
            logger.info(e)
            traceback.print_exc()

    def execute(self) -> None:
        self.is_complete = False
        self._run_context.reset()  # Reset context at start of execution
        self.load_and_run()
        self.is_complete = True

    def cancel(self) -> None:
        """Cancel all operations."""
        logger.info("Canceling...")
        self._run_context.update_action(UserAction.CANCEL)
        self.get_playback().stop()

    def open_text(self) -> None:
        song_text_filepath = self.get_playback().get_track_text_file()
        Utils.open_file(song_text_filepath)

    def get_current_track(self) -> Optional[Any]:
        return self.get_playback().track

    def get_current_track_artwork(self) -> Optional[str]:
        return self.get_playback().get_current_track_artwork()

    def get_run_context(self) -> RunContext:
        """Get the current run context."""
        return self._run_context

    def reset_run_context(self) -> None:
        """Reset the run context to its default state."""
        self._run_context.reset()

    def is_cancelled(self) -> bool:
        """Check if the run has been cancelled.
        
        Returns:
            bool: True if a CANCEL action exists in the run context, False otherwise
        """
        return self._run_context.was_cancelled()


def main(args: RunConfig) -> None:
    run = Run(args)
    run.execute()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--auto-run", action="store_true")
    parser.add_argument("-t", "--total", type=int, default=100)
    args = parser.parse_args()
    main(RunConfig(args))
