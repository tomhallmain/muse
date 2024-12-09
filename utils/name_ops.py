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


