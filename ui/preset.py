
from utils.globals import PlaylistSortType

class Preset:
    def __init__(self, name, playlist_sort_types, searches) -> None:
        self.name = name
        self.playlist_sort_types = []
        self.searches = searches
        for _type in playlist_sort_types:
            self.playlist_sort_types.append(_type if isinstance(_type, PlaylistSortType) else PlaylistSortType[_type])
        if len(self.playlist_sort_types) != len(self.searches):
            raise ValueError("Playlist sort types and searches must be the same length")

    def is_valid(self):
        return len(self.searches) > 0 and len(self.playlist_sort_types) == len(self.searches)

    def readable_str(self):
        search_map = ""
        for i in range(len(self.searches)):
            if i > 0:
                search_map += ", "
            search_map += self.playlist_sort_types[i].get_translation()
            search_map += ": " + str(self.searches[i])
        return f"{self.name}: {search_map}"

    def __str__(self):
        return self.readable_str()

    def __eq__(self, other):
        if not isinstance(other, Preset):
            return False
        return tuple(self.playlist_sort_types) == tuple(other.playlist_sort_types) \
            and tuple(self.searches) == tuple(other.searches)

    def __hash__(self):
        return hash((tuple(self.playlist_sort_types), tuple(self.searches)))

    def to_dict(self):
        playlist_sort_type_names = [_type.name for _type in self.playlist_sort_types]
        return {
            'name': self.name,
            'playlist_sort_types': playlist_sort_type_names,
            'searches': self.searches
            }
    
    @classmethod
    def from_dict(cls, dict_data: dict) -> 'Preset':
        return cls(**dict_data)

    @staticmethod
    def from_runner_app_config(name, runner_app_config) -> 'Preset':
        return Preset(name, runner_app_config.prompter_config.prompt_mode, runner_app_config.positive_tags, runner_app_config.negative_tags)