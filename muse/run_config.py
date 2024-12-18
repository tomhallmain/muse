
from utils.globals import Globals, WorkflowType # must import first

class RunConfig:

    def __init__(self, args=None):
        self.args = args
        self.workflow_tag = WorkflowType.RANDOM.name
        self.total = '-1'
        self.directories = self.get("directories")
        self.overwrite = False
        self.muse = True
        self.extend = True

    def get(self, name):
        if isinstance(self.args, dict):
            return self.args[name]
        elif not self.args:
            return None
        else:
            return getattr(self.args, name)

    def validate(self):
        return True

    def __str__(self):
        return str(self.__dict__)
