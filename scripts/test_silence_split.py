import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

from library_data.media_track import MediaTrack

if __name__ == "__main__":
    track = MediaTrack(os.path.join(os.path.expanduser("~"), "audio", "Classical", "Charles Villiers Stanford - Symphony No. 7, Op. 124 (1911) [p9XSPJADeDA].m4a"))
    silence_times = track.detect_silence_times(noise_threshold=0.01, duration=2)
    print(f"Silence times:")
    for silence in silence_times:
        print(f"{silence}")
    track.extract_non_silent_track_parts(select_random_track=True)

