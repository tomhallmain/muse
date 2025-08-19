import threading
import time
import logging

from muse.playback import Playback

logger = logging.getLogger(__name__)

class Timer:
    """
    A singleton timer class that runs in a separate thread and controls volume via playback.py
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Timer, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # Timer state
        self._duration_seconds = 0
        self._remaining_seconds = 0
        self._is_running = False
        self._is_paused = False
        self._is_completed = False
        self._volume_reduced = False
        self._reduced_volume = 20  # Volume level when timer expires
        self._beep_interval = 1.0  # Seconds between beeps
        
        # Threading
        self._timer_thread = None
        self._beep_thread = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        
        # Playback control
        self._playback_instance = None
        
        logger.info("Timer singleton initialized")
    
    def set_playback_instance(self, playback_instance: Playback) -> None:
        """Set the playback instance for volume control"""
        self._playback_instance = playback_instance
        logger.info("Playback instance set for timer")
    
    def start_timer(self, duration_seconds: int) -> None:
        """Start the timer with the specified duration in seconds"""
        if self._is_running:
            logger.warning("Timer is already running")
            return
        
        self._duration_seconds = duration_seconds
        self._remaining_seconds = duration_seconds
        self._is_running = True
        self._is_paused = False
        self._is_completed = False
        self._volume_reduced = False
        self._stop_event.clear()
        self._pause_event.clear()
        
        self._timer_thread = threading.Thread(target=self._timer_worker, daemon=True)
        self._timer_thread.start()
        
        logger.info(f"Timer started for {duration_seconds} seconds")
    
    def pause_timer(self) -> None:
        """Pause the timer"""
        if not self._is_running or self._is_completed:
            return
        
        self._is_paused = True
        self._pause_event.set()
        logger.info("Timer paused")
    
    def resume_timer(self) -> None:
        """Resume the timer"""
        if not self._is_running or self._is_completed:
            return
        
        self._is_paused = False
        self._pause_event.clear()
        logger.info("Timer resumed")
    
    def stop_timer(self) -> None:
        """Stop the timer and restore volume"""
        if not self._is_running and not self._is_completed:
            return
        
        self._stop_event.set()
        self._is_running = False
        self._is_paused = False
        
        # Restore volume if it was reduced
        if self._volume_reduced:
            self._restore_volume()
        
        # Stop beeping if active
        if self._beep_thread and self._beep_thread.is_alive():
            self._stop_event.set()
        
        logger.info("Timer stopped")
    
    def _timer_worker(self) -> None:
        """Main timer worker thread"""
        seconds_since_last_log = 0  # Track seconds since last log
        
        while not self._stop_event.is_set() and self._remaining_seconds > 0:
            if not self._pause_event.is_set():
                time.sleep(1)
                self._remaining_seconds -= 1
                seconds_since_last_log += 1
                
                # Log remaining time every 10 seconds
                if seconds_since_last_log >= 10:
                    logger.info(f"Timer running: {self._remaining_seconds} seconds remaining")
                    seconds_since_last_log = 0
            else:
                time.sleep(0.1)  # Shorter sleep when paused
        
        if not self._stop_event.is_set() and self._remaining_seconds <= 0:
            self._timer_expired()
    
    def _timer_expired(self) -> None:
        """Handle timer expiration"""
        self._is_completed = True
        self._is_running = False
        logger.info("Timer expired")
        
        # Reduce volume and start beeping
        self._reduce_volume()
        self._start_beeping()
    
    def _reduce_volume(self) -> None:
        """Reduce volume via playback.py flag"""
        if self._playback_instance and not self._volume_reduced:
            # Set a flag in playback.py to override volume
            if hasattr(self._playback_instance, 'set_timer_volume_override'):
                self._playback_instance.set_timer_volume_override(True, self._reduced_volume)
                self._volume_reduced = True
                logger.info(f"Volume reduced to {self._reduced_volume} via playback override")
            else:
                logger.warning("Playback instance does not have timer volume override method")
    
    def _restore_volume(self) -> None:
        """Restore normal volume via playback.py flag"""
        if self._playback_instance and self._volume_reduced:
            if hasattr(self._playback_instance, 'set_timer_volume_override'):
                self._playback_instance.set_timer_volume_override(False, None)
                self._volume_reduced = False
                logger.info("Volume restored via playback override")
    
    def _start_beeping(self) -> None:
        """Start the beeping sound in a separate thread"""
        if self._beep_thread and self._beep_thread.is_alive():
            return
        
        self._beep_thread = threading.Thread(target=self._beep_worker, daemon=True)
        self._beep_thread.start()
    
    def _beep_worker(self) -> None:
        """Beep worker thread"""
        while not self._stop_event.is_set():
            self._play_beep_sound()
            time.sleep(self._beep_interval)
    
    def _play_beep_sound(self) -> None:
        """Play the beep sound (placeholder for actual implementation)"""
        # TODO: Implement actual beep sound
        # For now, just log that a beep should play
        logger.info("BEEP! Timer expired!")
        pass
    
    def get_progress(self) -> float:
        """Get timer progress as a percentage (0.0 to 1.0)"""
        if self._duration_seconds == 0:
            return 0.0
        return max(0.0, min(1.0, (self._duration_seconds - self._remaining_seconds) / self._duration_seconds))
    
    def get_remaining_time(self) -> int:
        """Get remaining time in seconds"""
        return max(0, self._remaining_seconds)
    
    def get_status(self) -> str:
        """Get current timer status"""
        if self._is_completed:
            return "completed"
        elif self._is_paused:
            return "paused"
        elif self._is_running:
            return "running"
        else:
            return "stopped"
    
    def is_running(self) -> bool:
        """Check if timer is running"""
        return self._is_running
    
    def is_paused(self) -> bool:
        """Check if timer is paused"""
        return self._is_paused
    
    def is_completed(self) -> bool:
        """Check if timer is completed"""
        return self._is_completed
    
    def cleanup(self) -> None:
        """Clean up resources"""
        self.stop_timer()
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=1.0)
        if self._beep_thread and self._beep_thread.is_alive():
            self._beep_thread.join(timeout=1.0)
