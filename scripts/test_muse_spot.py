import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

# from time import sleep

from library_data.media_track import MediaTrack
from muse.run_config import RunConfig
from muse.muse import Muse, MuseSpotProfile


MULTI_MODEL = ("tts_models/multilingual/multi-dataset/xtts_v2", "Royston Min", "en")

if __name__ == '__main__':
    track = MediaTrack(r"F:\iTunes Music\conductor Evgeny Svetlanov\Symphony No. 3\03 5th Movement_ Lustig En Tempo Und.m4a")
    muse = Muse(RunConfig(), ui_callbacks=None)
    spot_profile = MuseSpotProfile(None, track, False, True)
    muse.teach_language(spot_profile)


