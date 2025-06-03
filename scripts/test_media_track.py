import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

from time import sleep

from library_data.media_track import MediaTrack

track_location = r"F:\iTunes Music\Academy of Ancient Music & Richard Egarr\Handel_ Concerti Grossi, Sonata a 5\24 Sonata a 5, HWV 288_ I. Andante.m4a"

track = MediaTrack(track_location)
print(track.get_track_artwork())

try:
    while True:
        sleep(10)
except KeyboardInterrupt as e:
    pass

