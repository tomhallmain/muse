
import json
import os

from muse.audio_track import AudioTrack
from muse.playback_config import PlaybackConfig
from muse.run_config import RunConfig
from utils.config import config

libary_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
configs_dir = os.path.join(os.path.dirname(libary_dir), 'configs')

run_config = RunConfig()
run_config.workflow_tag = "SEQUENCE"
run_config.directories = list(config.get_subdirectories().keys())
PlaybackConfig.load_directory_cache()

class EntityExtractor:
    def __init__(self):
        self.playback_config = PlaybackConfig(run_config)
        print(self.playback_config.type)
        self.known_entities = {}

        with open(os.path.join(configs_dir,'composers_dict.json'), 'r', encoding="utf-8") as f:
            self.known_entities = json.load(f)
        
        self.known_entities_found = {}

    def extract(self, audio_track):
        # Parse the attributes of the audio track (title, artist, album, etc.)
        # to find any matches with the known list of entities, and add any found
        # unknown entities to the staging list to be labeled

        # TODO some way to avoid clashes between minimized and full names
        # TODO check for word inside spaces / at start or end

        if audio_track.artist is None or audio_track.title is None:
            return {}

        # Find the entities that match the audio track's title and artist
        matches = []
        for entity, values in self.known_entities.items():
            for value in values:
                if value in audio_track.title or value in audio_track.album or value in audio_track.artist:
                    matches += [entity]

        if len(matches) > 0:
            for match in matches:
                if match not in self.known_entities_found:
                    self.known_entities_found[match] = []
                self.known_entities_found[match].append(audio_track)
            # print(audio_track.filepath)
            # print("Found matches: {}".format(matches))
        else:
            print(audio_track.album + " - " + audio_track.title + " - No matches found")

        return {}

    def run(self):
        # TODO try with new audio track properties

        for song_filepath in self.playback_config.get_list():
            self.extract(AudioTrack(song_filepath))

        entities_not_found = list(self.known_entities.keys())
        files = os.listdir(os.path.join(libary_dir, "wiki"))
        not_found_files = []

        print("\n\n-------------------------------------------------------------------------------\n\nFound entities:\n")
        for entity in sorted(self.known_entities_found):
            print(entity + " - " + str(len(self.known_entities_found[entity])))
            found_file = False
            for f in files:
                if entity in f:
                    print("  - " + os.path.basename(f))
                    found_file = True
                    break
            if not found_file:
                not_found_files.append(entity)
            entities_not_found.remove(entity)

        print("\n\n-------------------------------------------------------------------------------\n\nEntities not found:\n")

        for entity in sorted(entities_not_found):
            print(entity)
            found_file = False
            for f in files:
                if entity in f:
                    print("  - " + os.path.basename(f))
                    found_file = True
                    break
            if not found_file:
                not_found_files.append(entity)

        print("\n\n-------------------------------------------------------------------------------\n\nEntities not found in files:\n")

        print("[")
        for entity in sorted(not_found_files):
            print(f"\t\"{entity}\"")
        print("]")

