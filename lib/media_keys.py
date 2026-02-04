"""
Media key handling for keyboard media control buttons (previous, play/pause, next).

Supports both Tkinter and PySide6/Qt applications on Windows, macOS, and Linux.
"""

import platform
from typing import Callable, Optional
from utils.logging_setup import get_logger

logger = get_logger(__name__)


class MediaKeyHandler:
    """Unified handler for media keys across different UI frameworks."""
    
    # Windows media key virtual key codes
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PLAY_PAUSE = 0xB3
    
    # macOS media key virtual key codes (NSEvent key codes)
    # These are approximate and may vary; pynput is more reliable on macOS
    MACOS_MEDIA_PREV_TRACK = 0x7E  # NX_KEYTYPE_PREVIOUS
    MACOS_MEDIA_NEXT_TRACK = 0x7F  # NX_KEYTYPE_NEXT
    MACOS_MEDIA_PLAY_PAUSE = 0x7C  # NX_KEYTYPE_PLAY
    
    # Linux X11 key codes (XF86 keys)
    # These vary by system; pynput is more reliable on Linux
    LINUX_MEDIA_PREV_TRACK = 0x1008FF16  # XF86AudioPrev
    LINUX_MEDIA_NEXT_TRACK = 0x1008FF17  # XF86AudioNext
    LINUX_MEDIA_PLAY_PAUSE = 0x1008FF14  # XF86AudioPlay
    
    def __init__(
        self,
        previous_callback: Callable,
        next_callback: Callable,
        play_pause_callback: Callable,
    ):
        """
        Initialize media key handler.
        
        Args:
            previous_callback: Function to call when previous track key is pressed
            next_callback: Function to call when next track key is pressed
            play_pause_callback: Function to call when play/pause key is pressed
        """
        self.previous_callback = previous_callback
        self.next_callback = next_callback
        self.play_pause_callback = play_pause_callback
        self._listener = None
        
    def setup_tkinter(self, master):
        """
        Set up media key handling for Tkinter applications.
        
        Uses pynput for cross-platform media key detection.
        Works on Windows, macOS, and Linux.
        
        Args:
            master: The Tkinter root window
            
        Returns:
            True if setup was successful, False otherwise
        """
        try:
            from pynput import keyboard
            
            def on_media_key(key):
                try:
                    if hasattr(key, 'name'):
                        if key.name == 'media_previous':
                            self.previous_callback()
                        elif key.name == 'media_next':
                            self.next_callback()
                        elif key.name == 'media_play_pause':
                            self.play_pause_callback()
                except Exception as e:
                    logger.debug(f"Error handling media key: {e}")
            
            # Set up global listener for media keys
            # This will work even when the window doesn't have focus
            self._listener = keyboard.Listener(on_press=on_media_key)
            self._listener.start()
            system_name = platform.system()
            logger.info(f"Media key support enabled for {system_name} (using pynput)")
            return True
        except ImportError:
            logger.warning("Media key support requires pynput library.")
            logger.warning("Install with: pip install pynput")
            logger.warning("Media keys will not work until pynput is installed.")
            return False
        except Exception as e:
            logger.warning(f"Failed to set up media key listener: {e}")
            return False
    
    def setup_qt(self, window):
        """
        Set up media key handling for PySide6/Qt applications.
        
        On all platforms, we try to use pynput for global hotkey detection
        (works even when window doesn't have focus). If pynput is not available,
        Windows falls back to native Qt key detection via keyPressEvent override.
        
        Args:
            window: The Qt main window
            
        Returns:
            True if setup was successful, False otherwise
        """
        system = platform.system()
        
        # Try to use pynput for global hotkey detection on all platforms
        try:
            from pynput import keyboard
            
            def on_media_key(key):
                try:
                    if hasattr(key, 'name'):
                        if key.name == 'media_previous':
                            self.previous_callback()
                        elif key.name == 'media_next':
                            self.next_callback()
                        elif key.name == 'media_play_pause':
                            self.play_pause_callback()
                except Exception as e:
                    logger.debug(f"Error handling media key: {e}")
            
            # Set up global listener for media keys
            # This will work even when the window doesn't have focus
            self._listener = keyboard.Listener(on_press=on_media_key)
            self._listener.start()
            logger.info(f"Qt media key support enabled for {system} (using pynput - works globally)")
            return True
        except ImportError:
            # Fallback: On Windows, use native Qt key detection (requires window focus)
            if system == "Windows":
                logger.debug("pynput not available, falling back to native Qt key detection (requires window focus)")
                logger.debug("Install pynput for global media key support: pip install pynput")
                logger.debug("Qt media key handling ready (use handle_qt_key_event in keyPressEvent)")
                return True
            else:
                logger.warning(f"Media key support on {system} requires pynput library.")
                logger.warning("Install with: pip install pynput")
                logger.warning("Media keys will not work until pynput is installed.")
                return False
        except Exception as e:
            logger.warning(f"Failed to set up media key listener: {e}")
            # On Windows, still allow fallback to native Qt detection
            if system == "Windows":
                logger.debug("Falling back to native Qt key detection (requires window focus)")
                return True
            return False
    
    def handle_qt_key_event(self, native_virtual_key: int) -> bool:
        """
        Handle a Qt key event for media keys.
        
        Call this from your QMainWindow.keyPressEvent() method.
        This is used as a fallback when pynput is not available (primarily Windows).
        When pynput is installed, media keys are handled globally via setup_qt().
        
        Args:
            native_virtual_key: The native virtual key code from event.nativeVirtualKey()
            
        Returns:
            True if the key was handled (a media key), False otherwise
        """
        # If pynput listener is active, don't handle here (to avoid double handling)
        if self._listener is not None:
            return False
        
        system = platform.system()
        
        if system == "Windows":
            if native_virtual_key == self.VK_MEDIA_PREV_TRACK:
                self.previous_callback()
                return True
            elif native_virtual_key == self.VK_MEDIA_NEXT_TRACK:
                self.next_callback()
                return True
            elif native_virtual_key == self.VK_MEDIA_PLAY_PAUSE:
                self.play_pause_callback()
                return True
        elif system == "Darwin":  # macOS
            # Try macOS key codes (may vary by system)
            if native_virtual_key == self.MACOS_MEDIA_PREV_TRACK:
                self.previous_callback()
                return True
            elif native_virtual_key == self.MACOS_MEDIA_NEXT_TRACK:
                self.next_callback()
                return True
            elif native_virtual_key == self.MACOS_MEDIA_PLAY_PAUSE:
                self.play_pause_callback()
                return True
        elif system == "Linux":
            # Try Linux X11 key codes (may vary by system)
            if native_virtual_key == self.LINUX_MEDIA_PREV_TRACK:
                self.previous_callback()
                return True
            elif native_virtual_key == self.LINUX_MEDIA_NEXT_TRACK:
                self.next_callback()
                return True
            elif native_virtual_key == self.LINUX_MEDIA_PLAY_PAUSE:
                self.play_pause_callback()
                return True
        
        return False
    
    def stop(self):
        """
        Stop listening for media keys.
        
        This stops the pynput listener if it was started (used for Tkinter
        on all platforms, and Qt on macOS/Linux).
        """
        if self._listener is not None:
            try:
                self._listener.stop()
                self._listener = None
            except Exception as e:
                logger.debug(f"Error stopping media key listener: {e}")
