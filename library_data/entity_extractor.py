
import json
import os

from library_data.media_track import MediaTrack
from library_data.composer import Composer
from library_data.library_data import LibraryData, get_playback_config
from utils.utils import Utils

libary_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))

class EntityExtractor:
    def __init__(self):
        self.libary_data = LibraryData()
        self.playback_config = get_playback_config()
        Utils.log(self.playback_config.type)
        self.known_entities_found = {}

    def extract(self, audio_track):
        # Parse the attributes of the audio track (title, artist, album, etc.)
        # to find any matches with the known list of entities, and add any found
        # unknown entities to the staging list to be labeled

        # TODO some way to avoid clashes between minimized and full names
        # TODO check for word inside spaces / at start or end

        found_match = False

        if audio_track.artist is None or audio_track.title is None:
            return found_match

        # Find the entities that match the audio track's title and artist
        matches = self.libary_data.composers.get_composers(audio_track)

        if len(matches) > 0:
            found_match = True
            for match in matches:
                if match not in self.known_entities_found:
                    self.known_entities_found[match] = []
                self.known_entities_found[match].append(audio_track)
            # Utils.log(audio_track.filepath)
            # Utils.log("Found matches: {}".format(matches))
        else:
            Utils.log(audio_track.album + " - " + audio_track.title + " - No matches found")

        return found_match

    def run(self):
        # TODO try with new audio track properties

        tracks_with_no_matches = []

        for song_filepath in self.playback_config.get_list():
            if not self.extract(MediaTrack(song_filepath)):
                tracks_with_no_matches.append(song_filepath)

        entities_not_found = self.libary_data.composers.get_composer_names()
        files = os.listdir(os.path.join(libary_dir, "wiki"))
        not_found_files = []

        Utils.log("\n\n-------------------------------------------------------------------------------\n\nFound entities:\n")
        for entity in sorted(self.known_entities_found):
            Utils.log(entity + " - " + str(len(self.known_entities_found[entity])))
            found_file = False
            for f in files:
                if entity in f:
                    Utils.log("  - " + os.path.basename(f))
                    found_file = True
                    break
            if not found_file:
                not_found_files.append(entity)
            entities_not_found.remove(entity)

        Utils.log("\n\n-------------------------------------------------------------------------------\n\nEntities not found:\n")

        for entity in sorted(entities_not_found):
            Utils.log(entity)
            found_file = False
            for f in files:
                if entity in f:
                    Utils.log("  - " + os.path.basename(f))
                    found_file = True
                    break
            if not found_file:
                not_found_files.append(entity)

        Utils.log("\n\n-------------------------------------------------------------------------------\n\nEntities not found in files:\n")

        print("[")
        for entity in sorted(not_found_files):
            print(f"\t\"{entity}\"")
        print("]")
