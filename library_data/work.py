class Work:
    def __init__(self, name, composer, date=None):
        self.name = name
        self.composer = composer
        self.date = date

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Work):
            return False
        return self.composer == value.composer and self.name == value.name

    def __hash__(self):
        return hash((self.composer, self.name))

