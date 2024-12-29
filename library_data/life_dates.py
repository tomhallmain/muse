import re

class LifeDates():
    non_numeric_chars = re.compile(r"[^0-9\-–]+")

    def __init__(self, dates_string):
        self.dates_string = dates_string
        self.dob = -1
        self.dod = -1
        self.active_start = -1
        self.active_end = -1
        self.is_uncertain = "c." in dates_string

        # "fl." indicates date of flourishing, i.e. active period

        if "-" in dates_string or "–" in dates_string:
            cleaned_dates = LifeDates.clean_string(dates_string)
            if cleaned_dates == "":
                return
            dates = cleaned_dates.split("–" if "–" in dates_string else "-")
            if len(dates) != 2:
                raise Exception("Invalid date string: " + dates_string)
            if "fl. " in dates_string:
                try:
                    self.active_start = int(dates[0])
                except Exception as e:
                    pass
                try:
                    self.active_end = int(dates[1])
                except Exception as e:
                    pass
                self.is_uncertain = True
            else:
                try:
                    self.dob = int(dates[0])
                except Exception as e:
                    pass
                try:
                    self.dod = int(dates[1])
                except Exception as e:
                    pass
        else:
            cleaned_dates = LifeDates.clean_string(dates_string, remove_dash=True)
            if cleaned_dates == "":
                return
            if "fl. " in dates_string:
                self.active_start = int(cleaned_dates)
                self.is_uncertain = True
            elif "d." in dates_string or "died" in dates_string:
                self.dod = int(cleaned_dates)
                self.is_uncertain = True
            else:
                self.dob = int(cleaned_dates)

    @staticmethod
    def clean_string(s, remove_dash=False):
        s = s.replace(" ", "")
        s = s.replace(".", "")
        if remove_dash:
            s = s.replace("-", "")
        s = re.sub(LifeDates.non_numeric_chars, "", s)
        while s.startswith("-"):
            s = s[1:]
        while s.endswith("-"):
            s = s[:-1]
        while s.startswith("–"):
            s = s[1:]
        while s.endswith("–"):
            s = s[:-1]
        return s

    def is_valid(self):
        if self.dob == -1 and self.dod == -1 and self.active_start == -1 and self.active_end == -1:
            return False
        return True

    def is_lifetime(self):
        return self.dob!= -1 or self.dod != -1

    def get_start_date(self):
        if self.dob is None:
            return self.active_start
        return self.dob

    def get_end_date(self):
        if self.dod is None:
            return self.active_end
        return self.dod

    def __str__(self) -> str:
        if self.is_valid():
            if self.is_lifetime():
                return f"Life: {self.dob} - {self.dod}"
            else:
                return f"Active: {self.active_start} - {self.active_end}"
        else:
            return f"(INVALID)"
