

class AppActions:
    def __init__(self, track_details_callback, update_progress_callback):
        self.track_details_callback = track_details_callback
        self.update_progress_callback = update_progress_callback