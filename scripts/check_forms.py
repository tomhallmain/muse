import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

from library_data.form import forms_data
from library_data.library_data import LibraryData

if __name__ == "__main__":
    library_data = LibraryData()
    no_forms_tracks = []
    for track in library_data.audio_track_cache:
        forms = forms_data.get_forms(track)
        if len(forms) == 0:
            no_forms_tracks.append(track)

    for track in sorted(no_forms_tracks, key=lambda track: track.filepath):
        print(track.get_track_details())

