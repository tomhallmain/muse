#!/usr/bin/env python3
"""
Test script for compilation detection functionality.
Loads all tracks, clears compilation names, runs detection, and logs results.
"""

import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

from library_data.library_data import LibraryData
from utils.logging_setup import get_logger

logger = get_logger(__name__)

def main():
    # Initialize library data and load caches
    library = LibraryData()
    LibraryData.load_media_track_cache()
    
    # Get all tracks
    logger.info("Loading all tracks...")
    all_tracks = LibraryData.get_all_tracks()
    total_tracks = len(all_tracks)
    logger.info(f"Loaded {total_tracks} tracks")
    
    # Clear existing compilation names
    logger.info("Clearing existing compilation names...")
    for track in all_tracks:
        track.compilation_name = None
    
    # Run compilation detection on all tracks
    logger.info("Running compilation detection...")
    compilation_map = library.identify_compilation_tracks(all_tracks)
    
    # Find tracks where compilation_name != album
    true_compilations = []
    for track in all_tracks:
        if track.compilation_name and track.compilation_name != track.album:
            true_compilations.append(track)
    
    # Sort by compilation name then album name, etc.
    true_compilations.sort(key=lambda t: (t.compilation_name, t.album, t.tracknumber, t.tracktitle, t.title))
    
    # Log results
    logger.info("\nCompilation Detection Results:")
    logger.info("=" * 80)
    logger.info(f"Found {len(true_compilations)} tracks in compilations out of {total_tracks} total tracks")
    logger.info("=" * 80)
    
    current_compilation = None
    for track in true_compilations:
        if track.compilation_name != current_compilation:
            current_compilation = track.compilation_name
            logger.info(f"\nCompilation: {current_compilation}")
            logger.info("-" * 40)
        logger.info(track.get_track_details())

if __name__ == "__main__":
    main() 