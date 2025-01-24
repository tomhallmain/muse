

class AppActions:
    def __init__(self,
                 update_status_callback,
                 track_details_callback,
                 update_muse_text,
                 update_progress_callback,
                 update_extension_status_callback,
                 update_album_artwork,
                 get_media_frame_handle,
                 shutdown_callback):
        self.update_status_callback = update_status_callback
        self.track_details_callback = track_details_callback
        self.update_muse_text = update_muse_text
        self.update_progress_callback = update_progress_callback
        self.update_extension_status = update_extension_status_callback
        self.update_album_artwork = update_album_artwork
        self.get_media_frame_handle = get_media_frame_handle
        self.shutdown_callback = shutdown_callback

