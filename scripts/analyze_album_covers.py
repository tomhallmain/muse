import os
from collections import defaultdict

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

from library_data.library_data import LibraryData
from utils.utils import Utils

def analyze_album_covers():
    """
    Analyzes album cover consistency across tracks in the library.
    Identifies albums where:
    1. Some tracks have valid covers while others don't
    2. Tracks have different versions/qualities of the same album cover
    """
    # Initialize library data
    library = LibraryData()
    
    # Get all tracks
    all_tracks = library.get_all_tracks(overwrite=False)
    
    # Group tracks by album
    albums = defaultdict(list)
    for track in all_tracks:
        if track.album:
            albums[track.album].append(track)
    
    # Analyze each album
    inconsistent_albums = []
    for album_name, tracks in albums.items():
        if len(tracks) < 2:  # Skip single-track albums
            continue
            
        # Check for artwork consistency
        has_artwork = []
        no_artwork = []
        
        for track in tracks:
            artwork = track.get_album_artwork()
            if artwork:
                has_artwork.append(track)
            else:
                no_artwork.append(track)
        
        # If some tracks have artwork and others don't
        if has_artwork and no_artwork:
            inconsistent_albums.append({
                'album': album_name,
                'type': 'missing_artwork',
                'tracks_with_artwork': has_artwork,
                'tracks_without_artwork': no_artwork
            })
            continue
            
        # If all tracks have artwork, check for consistency
        if has_artwork:
            # Get the first artwork as reference
            ref_artwork = has_artwork[0].artwork
            different_artwork = []
            
            for track in has_artwork[1:]:
                if track.artwork != ref_artwork:
                    different_artwork.append(track)
            
            if different_artwork:
                inconsistent_albums.append({
                    'album': album_name,
                    'type': 'different_artwork',
                    'reference_track': has_artwork[0],
                    'tracks_with_different_artwork': different_artwork
                })
    
    # Print results
    if not inconsistent_albums:
        print("No inconsistent album covers found!")
        return
        
    print(f"\nFound {len(inconsistent_albums)} albums with inconsistent covers:")
    for album in inconsistent_albums:
        print(f"\nAlbum: {album['album']}")
        if album['type'] == 'missing_artwork':
            print("  Some tracks are missing artwork:")
            print(f"  - {len(album['tracks_with_artwork'])} tracks have artwork")
            print(f"  - {len(album['tracks_without_artwork'])} tracks missing artwork")
            print("\n  Tracks missing artwork:")
            for track in album['tracks_without_artwork']:
                print(f"    - {track.title} ({track.filepath})")
        else:  # different_artwork
            print("  Tracks have different artwork versions:")
            print(f"  - Reference track: {album['reference_track'].title}")
            print("\n  Tracks with different artwork:")
            for track in album['tracks_with_different_artwork']:
                print(f"    - {track.title} ({track.filepath})")

if __name__ == "__main__":
    analyze_album_covers() 