import unicodedata



class NameOps:
    probable_name_appendices = [
        "Junior",
        "Jr.",
        "Jr",
        "Senior",
        "Sr.",
        "Sr",
        "Esq",
        "I",
        "II",
        "III",
        "IIII",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
        "XI",
        "XII",
        "XIII",
        "XIV",
        "XV",
        "XVI",
        "XVII",
        "XVIII",
        "XIX",
        "XX"
    ]

    @staticmethod
    def get_name_sort_key(full_name):
        if not " " in full_name:
            return unicodedata.normalize('NFKD', full_name).lower()
        if "," in full_name: # NOTE assuming the name is already in form [First Names] [Last Names] so another comma means an irrelevant appendix
            full_name = full_name.split(",")[0]
        last_name_search_counter = 1
        name_parts = full_name.split(" ")
        first_last_name = name_parts[-last_name_search_counter]
        last_name = NameOps.get_capitalized_part_of_last_name(first_last_name)
        while last_name in NameOps.probable_name_appendices:
            last_name_search_counter += 1
            if last_name_search_counter > len(name_parts):
                last_name = first_last_name
                break
            last_name = name_parts[-last_name_search_counter]
            last_name = NameOps.get_capitalized_part_of_last_name(last_name)
        return unicodedata.normalize('NFKD', last_name).lower()

    @staticmethod
    def _is_word_char(ch):
        return ch.isalnum() or ch == "_"

    @staticmethod
    def contains_on_word_boundary(text, value):
        """True if value occurs in text delimited by non-word characters.

        Plain substring matching attaches an indicator to any text merely
        containing it, so "Bach" matches "Erbach" and "Bachschmid", and
        "Barth" matches "Bartholomäus". Requiring word boundaries keeps the
        genuine hits and drops those.

        Uses str.find rather than a regex: this runs for every indicator against
        every track, and find is the same C-level scan the plain `in` test used,
        so the common no-match case costs the same as before. It also means
        indicators containing regex metacharacters (`B.W.V.`, `Müller Sr.`) need
        no escaping.
        """
        if not value or not text:
            return False
        start = 0
        length = len(value)
        while True:
            idx = text.find(value, start)
            if idx == -1:
                return False
            after = idx + length
            if ((idx == 0 or not NameOps._is_word_char(text[idx - 1]))
                    and (after >= len(text) or not NameOps._is_word_char(text[after]))):
                return True
            start = idx + 1

    @staticmethod
    def get_full_name_sort_key(full_name):
        """Sort key ordering by last name, then by the whole name.

        get_name_sort_key resolves to the last name alone, so everyone sharing a
        surname collides and their relative order is decided by whatever order
        the caller happened to supply them in -- database row order, for one.
        Use this wherever full names are sorted for display or output, so the
        result is stable no matter where the names came from.
        """
        return (NameOps.get_name_sort_key(full_name),
                unicodedata.normalize('NFKD', full_name).lower())


    @staticmethod
    def get_capitalized_part_of_last_name(last_name):
        if len(last_name) == 0 or last_name.strip() == "":
            return last_name
        if "'" in last_name and last_name.index("'") < 3 and last_name.index("'") + 1 < len(last_name):
            # Example: French names like D'Indy
            return NameOps.get_capitalized_part_of_last_name(last_name[last_name.index("'")+1:])
        current_index = 0
        while not last_name[current_index].isalpha() and last_name[current_index] != last_name[current_index].upper():
            current_index += 1
            if current_index >= len(last_name):
                return last_name
        return last_name[current_index:]


