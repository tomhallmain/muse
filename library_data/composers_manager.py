
from copy import deepcopy
import json
import math
import os


from library_data.life_dates import LifeDates
from utils.name_ops import NameOps
from utils.utils import Utils


def do_print(f, s):
    f.write(s + "\n")
    print(s)


class ComposersManager:
    COMPOSRERS_DICT_LOCATION = os.path.join(os.path.abspath(os.path.dirname(__file__)), "data", "composers.json")

    @staticmethod
    def get_composers_dict():
        with open(ComposersManager.COMPOSRERS_DICT_LOCATION, "r") as f:
            composers = json.load(f)
            return composers

    @staticmethod
    def get_composer_data(composers, id):
        for composer, data in composers.items():
            if id == data["id"]:
                return data
        raise Exception("No composer found with ID {0}".format(id))

    @staticmethod
    def quality_check():
        composers = ComposersManager.get_composers_dict()

        all_composer_indicators = {}
        all_composer_dates = {}
        duplicate_composer_indicators = {}

        for composer, data in composers.items():
            composer_id = data["id"]
            composer_name = data["name"]
            indicators = data["indicators"]
            if composer_name.strip() == "" or "\t" in composer_name or composer_name.startswith(" ") or composer_name.endswith(" "):
                print(f"Composer ID contains invalid space in name: {composer_id} ({composer})")
            if len(indicators) == 0:
                print(f"Composer ID {composer_id} ({composer}) has no indicators")
            if composer_name != composer or composer_name != indicators[0]:
                print(f"Composer ID {composer_id} has different name and indicators: {composer}")
            start_date = data["start_date"]
            end_date = data["end_date"]
            if start_date is None or end_date is None:
                print(f"Composer ID {composer_id} ({composer}) has no date values")
            elif end_date > 0 and start_date > end_date:
                print(f"Composer ID {composer_id} ({composer}) has invalid start and end dates. Start date ({start_date}) is after end date ({end_date})")
            elif start_date > 2024 or end_date > 2024:
                print(f"Composer ID {composer_id} ({composer}) has invalid date values")
            elif start_date > -1:
                dates = (start_date, end_date)
                if dates in all_composer_dates:
                    all_composer_dates[dates].append(composer_id)
                else:
                    all_composer_dates[(start_date, end_date)] = [composer_id]
            for indicator in indicators:
                if indicator in all_composer_indicators:
                    if indicator in duplicate_composer_indicators:
                        duplicate_composer_indicators[indicator].append(composer_id)
                    else:
                        duplicate_composer_indicators[indicator] = [all_composer_indicators[indicator], composer_id]
                else:
                    all_composer_indicators[indicator] = composer_id

        print(f"{len(composers)} composers")
        print(f"{len(all_composer_indicators)} all composer indicators")

        if len(duplicate_composer_indicators) > 0:
            print("Duplicate indicators found:")
            for indicator, composers in duplicate_composer_indicators.items():
                composer_names = ", ".join([ComposersManager.get_composer_data(composers, composer)["name"] for composer in composers])
                print(f"{indicator}: {composer_names}")


        matching_date_composers = dict(filter((lambda date_composers: len(date_composers[1]) > 1), all_composer_dates.items()))
        matching_date_composers = Utils.sort_dictionary(matching_date_composers, key=lambda dates: dates[0])

        print("Matching date composers:")
        for dates, composer_ids in matching_date_composers.items():
            possible_duplicates = set()
            for i in range(0, len(composer_ids)):
                for j in range(i+1, len(composer_ids)):
                    if i >= j: continue
                    id_i = composer_ids[i]
                    id_j = composer_ids[j]
                    data_i = ComposersManager.get_composer_data(composers, id_i)
                    data_j = ComposersManager.get_composer_data(composers, id_j)
                    name_i = data_i["name"]
                    name_j = data_j["name"]
                    if name_i[0] == name_j[0]:
                        possible_duplicates.add((name_i, name_j))

            if len(possible_duplicates) > 0:
                print(f"{dates}")
                all_names = set()
                for name_i, name_j in possible_duplicates:
                    all_names.add(name_i)
                    all_names.add(name_j)
                
                print(", ".join(sorted(list(all_names))))

            # composer_names = ", ".join([ComposersManager.get_composer_data(composers, composer)["name"] for composer in composer_ids])
            # print(f"{dates} - {composer_names}")

        # all_composers_data_list = list(composers.values())
        # all_composers_data_list.sort(key=lambda composer: composer["start_date"] if composer["start_date"] else -1)

        # for i in range(len(all_composers_data_list)):
        #     data_i = all_composers_data_list[i]
        #     upper_bound = min(len(all_composers_data_list), i + 20)
        #     if i == upper_bound or i-1 == upper_bound: break
        #     name_i = data_i["name"]
        #     id_i = data_i["id"]

        #     for j in range(i+1, upper_bound):
        #         if i >= j: continue
        #         data_j = all_composers_data_list[j]
        #         id_j = data_j["id"]

        #         if id_i == id_j: continue
        #         name_j = data_j["name"]

        #         if Utils.is_similar_strings(name_i, name_j):
        #             possible_duplicates.add((id_i, id_j))

        # all_composer_indicators_list = list(all_composer_indicators.keys())
        # all_composer_indicators_list.sort()
        # possible_duplicates = set()

        # for i in range(len(all_composer_indicators_list)):
        #     indicator_i = all_composer_indicators_list[i]
        #     upper_bound = min(len(all_composer_indicators), i + 20)
        #     if i == upper_bound or i-1 == upper_bound: break
        #     for j in range(i+1, upper_bound):
        #         if i >= j: continue
        #         indicator_j = all_composer_indicators_list[j]
        #         composer_id_i = all_composer_indicators[indicator_i]
        #         composer_id_j = all_composer_indicators[indicator_j]
        #         if composer_id_i == composer_id_j: continue

        #         if Utils.is_similar_strings(indicator_i, indicator_j):
        #             possible_duplicates.add((composer_id_i, composer_id_j))

        # all_composer_indicators_list.sort(key=lambda n: NameOps.get_name_sort_key(n))
        # for i in range(len(all_composer_indicators_list)):
        #     indicator_i = all_composer_indicators_list[i]
        #     upper_bound = min(len(all_composer_indicators), i + 20)
        #     if i == upper_bound or i-1 == upper_bound: break
        #     for j in range(i+1, upper_bound):
        #         if i <= j: continue
        #         indicator_j = all_composer_indicators_list[j]
        #         composer_id_i = all_composer_indicators[indicator_i]
        #         composer_id_j = all_composer_indicators[indicator_j]
        #         if composer_id_i == composer_id_j: continue

        #         if Utils.is_similar_strings(indicator_i, indicator_j):
        #             possible_duplicates.add((composer_id_i, composer_id_j))

        possible_duplicates_list = []
        for (composer_id_i, composer_id_j) in possible_duplicates:
            composer_data_i = ComposersManager.get_composer_data(composers, composer_id_i)
            composer_data_j = ComposersManager.get_composer_data(composers, composer_id_j)
            possible_duplicates_list.append((composer_data_i, composer_data_j))

        possible_duplicates_list.sort(key=lambda x: x[0]["name"])

        friederich_wilhelms = []
        giovanni_battistas = []
        jean_baptistes = []
        johanns = []

        print("Possible duplicates found:")
        for (composer_data_i, composer_data_j) in possible_duplicates_list:
            composer_id_i = composer_data_i["id"]
            composer_id_j = composer_data_j["id"]
            name_i = composer_data_i["name"]
            name_j = composer_data_j["name"]
            composer_start_i = composer_data_i["start_date"]
            composer_start_j = composer_data_j["start_date"]
            is_close_dates = ""
            if composer_start_i is not None and composer_start_j is not None:
                is_close_dates = " (dates are not close)"
                if composer_start_i != -1 and composer_start_j != -1:
                    if abs(composer_start_i - composer_start_j) < 20:
                        is_close_dates = ""
            if name_i.startswith("Giovanni Battista"):
                giovanni_battistas.append((composer_data_i, composer_data_j))
            elif name_i.startswith("Friedrich Wilhelm"):
                friederich_wilhelms.append((composer_data_i, composer_data_j))
            elif name_i.startswith("<Jean-Baptiste>"):
                jean_baptistes.append((composer_data_i, composer_data_j))
            elif name_i.startswith("Johann"):
                johanns.append((composer_data_i, composer_data_j))
            else:
                print(f"{composer_id_i}: {name_i} <> {composer_id_j}: {name_j}{is_close_dates}")

        print("\n\n--------------------------------------\n\n")
        print("Friedrich Wilhelm close matches found:")
        for (composer_data, composer_data2) in friederich_wilhelms:
            print(f"{composer_data['name']}  <>  {composer_data2['name']}")

        print("\n\n--------------------------------------\n\n")
        print("Giovanni Battista / Jean-Baptiste / Johann close matches found:")
        for (composer_data, composer_data2) in giovanni_battistas:
            print(f"{composer_data['name']}  <>  {composer_data2['name']}")
        for (composer_data, composer_data2) in jean_baptistes:
            print(f"{composer_data['name']}  <>  {composer_data2['name']}")
        for (composer_data, composer_data2) in johanns:
            print(f"{composer_data['name']}  <>  {composer_data2['name']}")

    @staticmethod
    def get_max_index(composers_dict):
        m = -1
        for data in composers_dict.values():
            idx = data["id"]
            if idx > m:
                m = idx
        return m

    @staticmethod
    def is_in_dict(composers_dict, value):
        matches = []
        for composer_name, data in composers_dict.items():
            if value in composer_name:
                matches.append(data)
                continue
            for indicator in data["indicators"]:
                if value in indicator or indicator in value:
                    matches.append(data)
                    break
        return matches

    @staticmethod
    def print_shared_indexes(composers_dict):
        indexes = {}
        for data in composers_dict.values():
            idx = data["id"]
            if idx in indexes:
                indexes[idx].append(data)
            else:
                indexes[idx] = [data]
        for idx, datas in indexes.items():
            if len(datas) > 1:
                names = [data["name"] for data in datas]
                print(names)

    @staticmethod
    def default_composer_date_func(composer_date_string):
        if composer_date_string.strip() == "":
            return None, None
        composer = composer_date_string.strip()
        if not " (" in composer or not ")" in composer:
            print("Dates not found: " + composer)
            return None, None
        line_parts = composer.split(" (")
        name = line_parts[0].strip()
        dates_string = line_parts[-1].replace(")", "").strip()
        try:
            dates = LifeDates(dates_string)
            return name, dates
        except Exception as e:
            print(f"{name} - {e}")
            return None, None

    @staticmethod
    def get_composers_with_dates(more_composers_file_loc, composer_date_func=default_composer_date_func):
        composers_with_dates = {}
        with open(more_composers_file_loc, "r", encoding="utf-8") as f:
            more_possible_composers = json.load(f)

        for composer in more_possible_composers:
            name, dates = composer_date_func(composer)
            if name is None:
                continue
            composers_with_dates[name] = dates
 
        return composers_with_dates

    @staticmethod
    def get_full_name_and_no_space_composers(composers_with_dates):
        full_name_composers = {}
        no_space_composers = []

        for composer in composers_with_dates:
            if " " in composer:
                name_parts = composer.split(" ")
                last_name = name_parts[-1].strip()
                full_name_composers[composer] = last_name
            else:
                no_space_composers.append(composer)
                print("No space in composer: " + composer)

        return full_name_composers, no_space_composers

    @staticmethod
    def get_found_and_not_composers(composers_dict, composers_with_dates, full_name_composers, no_space_composers):
        found = {}
        maybe_false_positives = {}
        composers_not_found = []
        for full_name, last_name in full_name_composers.items():
            data = ComposersManager.is_in_dict(composers_dict, full_name)
            if len(data) == 1:
                found[full_name] = data[0]
            elif len(data) > 1:
                maybe_false_positives[full_name] = data
            else:
                data = ComposersManager.is_in_dict(composers_dict, last_name)
                if len(data) > 0:
                    maybe_false_positives[full_name] = data
                else:
                    composers_not_found.append(full_name)

        for name in no_space_composers:
            data = ComposersManager.is_in_dict(composers_dict, name)
            if len(data) == 1:
                found[name] = data[0]
            elif len(data) > 1:
                maybe_false_positives[name] = data
            else:
                composers_not_found.append(name)

        composers_not_found_ii = {}

        with open("temp_output.txt", "w", encoding="utf-8") as f:
            # def get_composer_names(last_name_val=None, ordered_name_val=None):
            #     found_names = []
            #     for full_name, names in full_name_composers.items():
            #         last_name = names[0]
            #         if last_name_val is not None:
            #             if last_name == last_name_val:
            #                 found_names.append(ordered_name)
            #         elif ordered_name_val is not None:
            #             if ordered_name_val == ordered_name:
            #                 found_names.append(full_name)
            #     if len(found_names) > 0:
            #         return found_names
            #     return [last_name_val]

            do_print(f, "\n\nComposers Not Found:\n")
            for composer in composers_not_found:
                try:
                    dates = composers_with_dates[composer]
                    composers_not_found_ii[composer] = (composer, dates)
                    do_print(f, f"{composer} - {dates}")
                except Exception as e:
                    do_print(f, f"{composer} - ERROR {e}")

            do_print(f, "\n\nMaybe False Positives:\n")
            for name, data in maybe_false_positives.items():
                found_composer_names = [d["name"] for d in data]
                if len(found_composer_names) > 8:
                    found_composer_names = found_composer_names[:8] + ["..."]
                composer_names = ", ".join(found_composer_names)
                dates = composers_with_dates[name]
                do_print(f, f"{name} - {dates} - {composer_names}")
                composers_not_found_ii[name] = (name, dates)

            do_print(f, "\n\nFound:\n")
            for name, data in found.items():
                found_composer_name = data["name"]
                do_print(f, f"{name} - {found_composer_name}")
        
        return found, maybe_false_positives, composers_not_found_ii

    @staticmethod
    def add_composers(composers_with_dates={}, print_shared_indexes=False,
                      add_to_new_dict=False, new_genres=[], new_notes={}):
        composers_dict = ComposersManager.get_composers_dict()
        full_name_composers, no_space_composers = ComposersManager.get_full_name_and_no_space_composers(composers_with_dates)
        found, maybe_false_positives, composers_not_found = ComposersManager.get_found_and_not_composers(
            composers_dict, composers_with_dates, full_name_composers, no_space_composers)

        composers_list = []
        composers_list.extend(list(composers_not_found.keys()))
        composers_list.extend(list(composers_dict.keys()))
        composers_list.sort(key=lambda c: NameOps.get_name_sort_key(c))

        if print_shared_indexes:
            print("\n\nShared indexes:")
            ComposersManager.print_shared_indexes(composers_dict)
            print("\n")

        max_index = ComposersManager.get_max_index(composers_dict)
        print(f"\nMax index: {max_index}")
        print(f"Found: {len(found)}")
        print(f"Not Found: {len(composers_not_found)}")

        if add_to_new_dict:
            ComposersManager.add_to_new_dict(composers_dict, composers_list, composers_with_dates,
                                             found, composers_not_found, new_genres, new_notes)



    @staticmethod
    def add_to_new_dict(composers_dict, composers_list, composers_with_dates,
                        found, composers_not_found, new_genres=[], new_notes={}):

        # NOTE remember to add the fix - if composer dates already exist, set
        # dates_are_lifespan to true and dates_uncertain to false.

        # NOTE grab the parenthetical extra names from the wikilist as separate indicators

        # Also, go back over previously entered composers from before 1600 to
        # MAYBE set dates_uncertain to True.

        def get_composer_dates_from_found(composers_dict_name):
            for name, data in found.items():
                found_composer_name = data["name"]
                if found_composer_name == composers_dict_name:
                    dates = composers_with_dates[name]
                    print(f"found original name: {name} - {dates}")
                    return dates, True
            return None, False

        new_composers_dict = {}

        id_count = ComposersManager.get_max_index(composers_dict) + 1
        for composer in composers_list:
            if composer in composers_dict:
                composer_data_orig = composers_dict[composer]
                if composer_data_orig["id"] is None or composer_data_orig["name"] is None or composer_data_orig["name"].strip() == "":
                    raise Exception("Invalid composer data: " + composer)
                dates, was_actually_found = get_composer_dates_from_found(composer)
                start_date = composer_data_orig["start_date"]
                end_date = composer_data_orig["end_date"]
                dates_are_lifespan = composer_data_orig["dates_are_lifespan"]
                dates_uncertain = composer_data_orig["dates_uncertain"]
                genres = composer_data_orig["genres"]
                notes = composer_data_orig["notes"]
                if dates is not None:
                    if start_date is not None or end_date is not None:
                        print(f"Maybe conflicting dates found for composer: {composer}")
                    else:
                        start_date = dates.get_start_date()
                        end_date = dates.get_end_date()
                        dates_are_lifespan = dates.is_lifetime()
                        dates_uncertain = dates.is_uncertain
                if was_actually_found:
                    if len(new_genres) > 0:
                        genres.extend(new_genres)
                        genres = sorted(list(set(genres)))
                    if len(new_notes) > 0:
                        notes = {**notes, **new_notes}
              
                composer_data = {
                    "id": composer_data_orig["id"],
                    "name": composer_data_orig["name"],
                    "indicators": composer_data_orig["indicators"],
                    "start_date": start_date,
                    "end_date": end_date,
                    "dates_are_lifespan": dates_are_lifespan,
                    "dates_uncertain": dates_uncertain,
                    "genres": genres,
                    "works": composer_data_orig['works'],
                    "notes": notes
                }
            else:
                composer_data_pre = composers_not_found[composer]
                original_name_from_poster_data = composer_data_pre[0]
                dates = composer_data_pre[1]
                indicators = [composer]
                if composer != original_name_from_poster_data:
                    indicators.append(original_name_from_poster_data)
                if dates is not None:
                    start_date = dates.get_start_date()
                    end_date = dates.get_end_date()
                    dates_are_lifespan = dates.is_lifetime()
                    dates_uncertain = dates.is_uncertain
                else:
                    start_date = None
                    end_date = None
                    dates_are_lifespan = True
                    dates_uncertain = False
                composer_data = {
                    "id": id_count,
                    "name": composer,
                    "indicators": indicators,
                    "start_date": start_date,
                    "end_date": end_date,
                    "dates_are_lifespan": dates_are_lifespan,
                    "dates_uncertain": dates_uncertain,
                    "genres": new_genres[:],
                    "works": [],
                    "notes": deepcopy(new_notes),
                }
                id_count += 1
            new_composers_dict[composer] = composer_data

        composers_swap_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), "data", "composers_swap.json")

        with open(composers_swap_file, "w", encoding="utf-8") as f:
            json.dump(new_composers_dict, f, indent=4)


