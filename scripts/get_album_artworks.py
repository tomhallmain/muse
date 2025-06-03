import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

import hashlib

from library_data.library_data import LibraryData
from utils.utils import Utils

def _calculate_hash(filepath):
    with open(filepath, 'rb') as f:
        sha256 = hashlib.sha256()
        while True:
            data = f.read(65536)
            if not data:
                break
            sha256.update(f.read())
    return sha256.hexdigest()


if __name__ == "__main__":
    target_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Album_Art")
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)
    LibraryData.load_directory_cache()
    LibraryData.load_media_track_cache()
    library_data = LibraryData()
    known_hashes = []
    total_tracks_count = 0
    count = 0
    for track in library_data.get_all_tracks():
        total_tracks_count += 1
        basename = f"{track.title}_{count}"
        actual_basename = f"{track.album}"
        artwork_path = track.get_album_artwork(filename=actual_basename)
        if artwork_path is not None:
            print(track, artwork_path)
            count += 1
            hash = _calculate_hash(artwork_path)
            if hash not in known_hashes:
                known_hashes.append(hash)
                print(Utils.move_file(artwork_path, os.path.join(target_dir, actual_basename)))
    print(f"Got album artworks for {count} tracks out of {total_tracks_count}, total of {len(known_hashes)} unique hashes")

