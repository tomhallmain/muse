

from library_data.work import Work

class Composer:
    def __init__(self, name, indicators=[], dob=-1, dod=-1, genres=[], works=[]):
        self.name = name
        self.indicators = indicators if len(indicators) > 0 else [name]
        self.dob = -1
        self.dod = -1
        self.genres = []
        self.works = []

        for work in works:
            self.add_work(work)

    def add_work(self, work):
        self.works.append(Work(work, self))

    @staticmethod
    def from_json(json):
        return Composer(**json)

