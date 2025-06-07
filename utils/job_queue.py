from utils.utils import Utils

class JobQueue:
    def __init__(self, name="JobQueue", max_size=50):
        self.name = name
        self.max_size = max_size
        self.pending_jobs = []
        self.job_running = False

    def has_pending(self):
        return self.job_running or len(self.pending_jobs) > 0

    def take(self):
        if len(self.pending_jobs) == 0:
            return None
        job_args = self.pending_jobs[0]
        del self.pending_jobs[0]
        return job_args

    def add(self, job_args):
        if len(self.pending_jobs) > self.max_size:
            raise Exception(f"Reached limit of pending runs: {self.max_size} - wait until current run has completed.")
        self.pending_jobs.append(job_args)
        Utils.log(f"JobQueue {self.name} - Added pending job: {job_args}")

    def cancel(self):
        """Clear all pending jobs from the queue and reset the job_running flag."""
        if self.pending_jobs:
            Utils.log(f"JobQueue {self.name} - Clearing {len(self.pending_jobs)} pending jobs")
            self.pending_jobs = []
        self.job_running = False

    def pending_text(self):
        if len(self.pending_jobs) == 0:
            return ""
        if self.name == "Playlist Runs":
            return _(" (Pending runs: {0})").format(len(self.pending_jobs))