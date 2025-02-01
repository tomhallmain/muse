

class AppActions:
    def __init__(self,
                 track_details_callback,
                 update_next_up_callback,
                 update_prior_track_callback,
                 update_spot_profile_topics_text,
                 update_progress_callback,
                 update_extension_status_callback,
                 update_album_artwork,
                 get_media_frame_handle,
                 shutdown_callback,
                 start_play_callback,
                 ):
        self.track_details_callback = track_details_callback
        self.update_next_up_callback = update_next_up_callback
        self.update_prior_track_callback = update_prior_track_callback
        self.update_spot_profile_topics_text = update_spot_profile_topics_text
        self.update_progress_callback = update_progress_callback
        self.update_extension_status = update_extension_status_callback
        self.update_album_artwork = update_album_artwork
        self.get_media_frame_handle = get_media_frame_handle
        self.shutdown_callback = shutdown_callback
        self.start_play_callback = start_play_callback

