import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

from muse.muse import Muse, MuseSpotProfile
from muse.run import Run
from muse.run_config import RunConfig
from utils.config import config

if __name__ == "__main__":
    config.directories = ["C:\\Users\\tehal\\audio\\Classical"]
    MuseSpotProfile.chance_speak_about_other_topics = 1
    MuseSpotProfile.chance_speak_before_track = 0
    run_config = RunConfig()
    run_config.directories = list(config.get_subdirectories().keys())
    run_config.extend = False
    run = Run(run_config)
    run.execute()
