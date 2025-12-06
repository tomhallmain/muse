"""
Audio Device Manager for Windows

This module provides functionality to manage audio output devices on Windows,
including listing available devices, switching between them, and automatic
time-based switching for day/night usage patterns.

Dependencies:
    - pycaw: Python bindings for Windows Core Audio APIs
    - comtypes: For COM interface handling

Usage:
    from utils.audio_device_manager import AudioDeviceManager
    
    manager = AudioDeviceManager()
    devices = manager.list_devices()
    manager.switch_to_device("Headphones")
    manager.set_day_night_schedule()
"""

import time
from datetime import datetime, time as dt_time
from typing import List, Dict, Optional, Tuple
import threading

from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._

try:
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import CLSID_MMDeviceEnumerator
    import comtypes
    import comtypes.client
    
    # Try to import AudioEndpointVolume - it might be in a different location
    try:
        from pycaw.pycaw import AudioEndpointVolume
    except ImportError:
        try:
            from pycaw import AudioEndpointVolume
        except ImportError:
            # For newer versions, AudioEndpointVolume might be accessed differently
            AudioEndpointVolume = None
    
    # Try to import AudioEndpointVolumeCallback
    try:
        from pycaw.utils import AudioEndpointVolumeCallback
    except ImportError:
        AudioEndpointVolumeCallback = None
        
except ImportError as e:
    logger.warning(f"pycaw not available: {e}. Audio device management will be limited.")
    AudioUtilities = None
    AudioEndpointVolume = None
    CLSID_MMDeviceEnumerator = None
    AudioEndpointVolumeCallback = None
    comtypes = None
    comtypes_client = None

# Try to import sounddevice for more reliable device detection
try:
    import sounddevice as sd
    sounddevice_available = True
except ImportError:
    sounddevice_available = False
    logger.debug("sounddevice not available. Install with: pip install sounddevice")


class AudioDeviceManager:
    """
    Manages audio output devices on Windows systems.
    
    Provides functionality to:
    - List available audio output devices
    - Switch between audio devices
    - Set up automatic day/night switching
    - Monitor device changes
    """
    
    # Class variables for cached settings
    _cached_day_device = None
    _cached_night_device = None
    _cached_day_start_time = None
    _cached_night_start_time = None
    _cached_monitoring_enabled = False
    
    def __init__(self):
        """Initialize the audio device manager."""
        self._devices_cache = {}
        self._current_device = None
        
        # Initialize with cached settings or defaults
        self._day_device = AudioDeviceManager._cached_day_device
        self._night_device = AudioDeviceManager._cached_night_device
        self._day_start_time = AudioDeviceManager._cached_day_start_time or dt_time(7, 0)  # 7:00 AM
        self._night_start_time = AudioDeviceManager._cached_night_start_time or dt_time(22, 0)  # 10:00 PM
        
        self._monitoring_thread = None
        self._stop_monitoring = threading.Event()
        
        if AudioUtilities is None:
            logger.error("pycaw library not available. Install with: pip install pycaw")
            raise ImportError("pycaw library is required for audio device management")
    
    def list_devices(self, refresh: bool = False) -> List[Dict[str, str]]:
        """
        List all available audio output devices, filtered and prioritized.
        
        Args:
            refresh: If True, refresh the device cache
            
        Returns:
            List of dictionaries containing device information, filtered and sorted
        """
        if not refresh and self._devices_cache:
            return list(self._devices_cache.values())
        
        devices = []
        try:
            # Get all audio devices
            audio_devices = AudioUtilities.GetAllDevices()
            
            for device in audio_devices:
                # Check if this is an output device
                # Try different ways to access dataFlow depending on pycaw version
                is_output_device = False
                
                try:
                    # Try the old way first
                    if hasattr(device, 'dataFlow'):
                        is_output_device = device.dataFlow == 0  # eRender (output devices)
                    else:
                        # Try alternative ways to determine if it's an output device
                        device_name = getattr(device, 'FriendlyName', '') or getattr(device, 'name', '')
                        device_description = getattr(device, 'Description', '') or ''
                        
                        # Check if it's clearly an input device
                        if self._is_input_device(device_name, device_description):
                            is_output_device = False
                        elif device_name:
                            # If we can't determine from dataFlow, use name-based detection
                            is_output_device = self._is_output_device_by_name(device_name, device_description)
                        else:
                            is_output_device = False
                except Exception as attr_error:
                    logger.debug(f"Could not determine device type: {attr_error}")
                    # Default to excluding if we can't determine
                    is_output_device = False
                
                if is_output_device:
                    try:
                        device_info = {
                            'id': getattr(device, 'id', 'unknown'),
                            'name': getattr(device, 'FriendlyName', '') or getattr(device, 'name', 'Unknown Device'),
                            'description': getattr(device, 'Description', '') or getattr(device, 'name', ''),
                            'state': getattr(device, 'State', 0),
                            'is_default': False  # We'll determine this separately
                        }
                        
                        # Filter out unwanted devices
                        if self._should_include_device(device_info):
                            devices.append(device_info)
                            self._devices_cache[device_info['id']] = device_info
                    except Exception as info_error:
                        logger.warning(f"Could not extract device info: {info_error}")
                        # Create a basic device info entry
                        device_info = {
                            'id': str(id(device)),
                            'name': 'Unknown Device',
                            'description': 'Device info unavailable',
                            'state': 0,
                            'is_default': False
                        }
                        if self._should_include_device(device_info):
                            devices.append(device_info)
                            self._devices_cache[device_info['id']] = device_info
            
            # Sort devices by priority
            devices = self._sort_devices_by_priority(devices)
            
            logger.info(f"Found {len(devices)} filtered audio output devices")
            
        except Exception as e:
            logger.error(f"Error listing audio devices: {e}")
            
        return devices
    
    def _is_input_device(self, device_name: str, device_description: str) -> bool:
        """
        Check if a device is clearly an input device.
        
        Args:
            device_name: Device name
            device_description: Device description
            
        Returns:
            True if it's an input device, False otherwise
        """
        name_lower = device_name.lower()
        desc_lower = device_description.lower()
        
        input_keywords = [
            'microphone', 'mic', 'input', 'line in', 'aux in', 'cd in',
            'stereo mix', 'what u hear', 'wave out mix', 'recording',
            'capture', 'audio input', 'sound input', 'voice', 'speech',
            'hands-free', 'hands free', 'headset mic', 'headphone mic',
            'usb mic', 'bluetooth mic', 'wireless mic', 'gaming mic',
            'studio mic', 'professional mic', 'condenser', 'dynamic',
            'lavalier', 'clip-on', 'desktop mic', 'webcam mic',
            'camera mic', 'built-in mic', 'internal mic'
        ]
        
        for keyword in input_keywords:
            if keyword in name_lower or keyword in desc_lower:
                logger.debug(f"Identified input device: {device_name} (keyword: {keyword})")
                return True
        
        return False
    
    def _is_output_device_by_name(self, device_name: str, device_description: str) -> bool:
        """
        Determine if a device is an output device based on its name and description.
        
        Args:
            device_name: Device name
            device_description: Device description
            
        Returns:
            True if it's likely an output device, False otherwise
        """
        name_lower = device_name.lower()
        desc_lower = device_description.lower()
        
        output_keywords = [
            'speaker', 'headphone', 'headset', 'monitor', 'audio out',
            'line out', 'aux out', 'sound out', 'playback', 'output',
            'usb audio', 'bluetooth audio', 'wireless audio', 'gaming audio',
            'studio monitor', 'professional audio', 'high definition audio',
            'realtek audio', 'intel audio', 'amd audio', 'nvidia audio',
            'hdmi audio', 'displayport audio', 'spdif', 'optical',
            'analog out', 'digital out', 'stereo out', 'surround',
            '5.1', '7.1', 'dolby', 'dts', 'thx'
        ]
        
        for keyword in output_keywords:
            if keyword in name_lower or keyword in desc_lower:
                logger.debug(f"Identified output device: {device_name} (keyword: {keyword})")
                return True
        
        # If we can't determine, be conservative and exclude it
        logger.debug(f"Could not determine device type for: {device_name}")
        return False
    
    def list_all_devices(self, refresh: bool = False) -> List[Dict[str, str]]:
        """
        List all available audio output devices without filtering.
        
        Args:
            refresh: If True, refresh the device cache
            
        Returns:
            List of dictionaries containing all device information
        """
        devices = []
        try:
            # Get all audio devices
            audio_devices = AudioUtilities.GetAllDevices()
            
            for device in audio_devices:
                # Check if this is an output device
                is_output_device = False
                
                try:
                    if hasattr(device, 'dataFlow'):
                        is_output_device = device.dataFlow == 0  # eRender (output devices)
                    else:
                        device_name = getattr(device, 'FriendlyName', '') or getattr(device, 'name', '')
                        device_description = getattr(device, 'Description', '') or ''
                        
                        # Check if it's clearly an input device
                        if self._is_input_device(device_name, device_description):
                            is_output_device = False
                        elif device_name:
                            # If we can't determine from dataFlow, use name-based detection
                            is_output_device = self._is_output_device_by_name(device_name, device_description)
                        else:
                            is_output_device = False
                except Exception:
                    is_output_device = False
                
                if is_output_device:
                    try:
                        device_info = {
                            'id': getattr(device, 'id', 'unknown'),
                            'name': getattr(device, 'FriendlyName', '') or getattr(device, 'name', 'Unknown Device'),
                            'description': getattr(device, 'Description', '') or getattr(device, 'name', ''),
                            'state': getattr(device, 'State', 0),
                            'is_default': getattr(device, 'isDefault', False)
                        }
                        devices.append(device_info)
                    except Exception:
                        device_info = {
                            'id': str(id(device)),
                            'name': 'Unknown Device',
                            'description': 'Device info unavailable',
                            'state': 0,
                            'is_default': False
                        }
                        devices.append(device_info)
            
            logger.info(f"Found {len(devices)} total audio output devices (unfiltered)")
            
        except Exception as e:
            logger.error(f"Error listing all audio devices: {e}")
            
        return devices
    
    def _should_include_device(self, device_info: Dict[str, str]) -> bool:
        """
        Determine if a device should be included in the filtered list.
        
        Args:
            device_info: Dictionary containing device information
            
        Returns:
            True if device should be included, False otherwise
        """
        device_name = device_info.get('name', '').lower()
        device_description = device_info.get('description', '').lower()
        
        # Special handling for numbered devices (professional audio interfaces) - CHECK FIRST
        if device_name and device_name[0].isdigit():
            # Check if it's an input device first
            if self._is_input_device(device_name, device_description):
                logger.debug(f"Excluding numbered input device: '{device_info['name']}'")
                return False
            else:
                logger.debug(f"Including numbered output device: '{device_info['name']}'")
                return True
        
        # Filter out virtual/graphics audio devices and input devices
        exclude_keywords = [
            'nvidia', 'amd', 'intel hd', 'intel graphics', 'realtek hd',
            'virtual', 'voicemeeter', 'vb-audio', 'obs', 'streamlabs',
            'discord', 'zoom', 'teams', 'skype', 'steam', 'origin',
            'bluetooth', 'hands-free', 'hands free', 'a2dp',
            'microsoft', 'generic', 'default', 'communications',
            'stereo mix', 'what u hear', 'wave out mix',
            # Realtek virtual endpoints (not actual speakers)
            'realtek audio', 'realtek high definition', 'realtek hd audio',
            'realtek alc', 'realtek codec', 'realtek driver', 'realtek usb',
            # Input device keywords
            'microphone', 'mic', 'input', 'line in', 'aux in', 'cd in',
            'recording', 'capture', 'audio input', 'sound input', 'voice',
            'headset mic', 'headphone mic', 'usb mic', 'bluetooth mic',
            'wireless mic', 'gaming mic', 'studio mic', 'professional mic',
            'condenser', 'dynamic', 'lavalier', 'clip-on', 'desktop mic',
            'webcam mic', 'camera mic', 'built-in mic', 'internal mic'
        ]
        
        # Check if device name or description contains exclude keywords
        for keyword in exclude_keywords:
            if keyword in device_name or keyword in device_description:
                logger.debug(f"Excluding device '{device_info['name']}' due to keyword '{keyword}'")
                return False
        
        # Filter out devices with very generic names
        generic_names = [
            'speakers', 'headphones', 'microphone', 'line out', 'line in',
            'aux', 'analog', 'digital', 'spdif', 'hdmi', 'displayport'
        ]
        
        # Only exclude if it's just a generic name without additional context
        if device_name in generic_names and len(device_name) < 15:
            logger.debug(f"Excluding generic device '{device_info['name']}'")
            return False
        
        # Include devices that are likely real audio output hardware
        include_keywords = [
            'speaker', 'headphone', 'headset', 'monitor', 'audio out',
            'line out', 'aux out', 'sound out', 'playback', 'output',
            'usb audio', 'bluetooth audio', 'wireless audio', 'gaming audio',
            'studio monitor', 'professional audio', 'high definition audio',
            'hdmi audio', 'displayport audio', 'spdif', 'optical',
            'analog out', 'digital out', 'stereo out', 'surround',
            '5.1', '7.1', 'dolby', 'dts', 'thx',
            # Only include Realtek when connected to actual speakers
            'realtek speakers', 'realtek headphone', 'realtek headset',
            'realtek monitor', 'realtek hdmi', 'realtek optical'
        ]
        
        # Special handling for Realtek devices
        if 'realtek' in device_name:
            # Only include Realtek if it's clearly connected to actual speakers/headphones
            realtek_speaker_keywords = ['speaker', 'headphone', 'headset', 'monitor', 'hdmi', 'optical', 'spdif']
            if any(keyword in device_name for keyword in realtek_speaker_keywords):
                logger.debug(f"Including Realtek device with actual speakers: '{device_info['name']}'")
                return True
            else:
                logger.debug(f"Excluding generic Realtek device: '{device_info['name']}'")
                return False
        
        # If it contains include keywords, it's likely a real device
        for keyword in include_keywords:
            if keyword in device_name or keyword in device_description:
                return True
        
        # If we can't determine, exclude it to be safe
        logger.debug(f"Excluding uncertain device '{device_info['name']}'")
        return False
    
    def _sort_devices_by_priority(self, devices: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Sort devices by priority (most useful first).
        
        Args:
            devices: List of device dictionaries
            
        Returns:
            Sorted list of devices
        """
        def device_priority(device):
            """Calculate priority score for a device (lower = higher priority)."""
            name = device.get('name', '').lower()
            is_default = device.get('is_default', False)
            
            # Default device gets highest priority
            if is_default:
                return 0
            
            # Priority order for device types
            priority_keywords = [
                ('headphone', 1),
                ('headset', 2),
                ('speaker', 3),
                ('monitor', 4),
                ('usb', 5),
                ('bluetooth', 6),
                ('wireless', 7),
                ('gaming', 8),
                ('studio', 9),
                ('professional', 10)
            ]
            
            # Find the first matching keyword
            for keyword, priority in priority_keywords:
                if keyword in name:
                    return priority
            
            # Unknown devices get lower priority
            return 50
        
        # Sort by priority, then by name for consistent ordering
        sorted_devices = sorted(devices, key=lambda d: (device_priority(d), d.get('name', '').lower()))
        
        logger.debug(f"Sorted {len(sorted_devices)} devices by priority")
        return sorted_devices
    
    def get_recently_used_devices(self, limit: int = 5) -> List[Dict[str, str]]:
        """
        Get recently used audio devices (if Windows tracks this information).
        
        Args:
            limit: Maximum number of recent devices to return
            
        Returns:
            List of recently used devices
        """
        try:
            # Try to get device usage information from Windows registry
            # This is a simplified approach - Windows doesn't directly expose
            # "recently used" audio devices through the Core Audio API
            
            # For now, we'll prioritize devices that are currently active
            # and have been used recently based on their state
            devices = self.list_devices()
            
            # Sort by device state (active devices first)
            active_devices = []
            inactive_devices = []
            
            for device in devices:
                state = device.get('state', 0)
                if state == 1:  # DeviceStateActive
                    active_devices.append(device)
                else:
                    inactive_devices.append(device)
            
            # Combine active devices first, then inactive
            recent_devices = active_devices + inactive_devices
            
            # Limit the results
            return recent_devices[:limit]
            
        except Exception as e:
            logger.warning(f"Could not get recently used devices: {e}")
            # Fallback to just returning the first few devices
            devices = self.list_devices()
            return devices[:limit]
    
    def get_current_device(self) -> Optional[Dict[str, str]]:
        """
        Get the current active audio output device (not a placeholder).
        
        This method attempts to find the actual device that is currently being used,
        filtering out generic "Default Device" placeholders that Windows may return.
        
        Returns:
            Dictionary containing current device information, or None if not found
        """
        # Helper function to check if a device name is a placeholder
        def is_placeholder_name(name: str) -> bool:
            """Check if a device name is a generic placeholder."""
            if not name:
                return True
            name_lower = name.lower().strip()
            placeholder_names = ['default device', 'default audio device', 'default', 'unknown device']
            return name_lower in placeholder_names or len(name_lower) < 3
        
        try:
            # Method 1: Try using AudioUtilities.GetSpeakers() - this is the correct method
            if hasattr(AudioUtilities, 'GetSpeakers'):
                default_device = AudioUtilities.GetSpeakers()
                if default_device:
                    device_id = getattr(default_device, 'id', None)
                    device_name = getattr(default_device, 'FriendlyName', '') or getattr(default_device, 'name', '')
                    
                    # Even if name is a placeholder, try to match by device ID first
                    if device_id:
                        devices = self.list_devices()
                        # Try to match by device ID (most reliable)
                        for device in devices:
                            if device['id'] == device_id:
                                device['is_default'] = True
                                logger.debug(f"Found current device via GetSpeakers (matched by ID): {device['name']}")
                                self._current_device = device
                                return device
                        
                        # If not found by ID, try matching by name (if name is not a placeholder)
                        if not is_placeholder_name(device_name):
                            for device in devices:
                                if device['name'] == device_name:
                                    device['is_default'] = True
                                    logger.debug(f"Found current device via GetSpeakers (matched by name): {device['name']}")
                                    self._current_device = device
                                    return device
                            
                            # If not in filtered list but has a real name, return it
                            device_info = {
                                'id': device_id,
                                'name': device_name,
                                'description': getattr(default_device, 'Description', '') or device_name,
                                'state': getattr(default_device, 'State', 0),
                                'is_default': True
                            }
                            logger.debug(f"Found current device via GetSpeakers: {device_info['name']}")
                            self._current_device = device_info
                            return device_info
                        else:
                            logger.debug(f"GetSpeakers returned placeholder name but device ID {device_id[:50]}... - will try other methods")
                    else:
                        logger.debug(f"Skipping device from GetSpeakers: no device ID available")
            else:
                logger.debug("GetSpeakers not available in this pycaw version")
        except Exception as e:
            logger.debug(f"Could not get current device via GetSpeakers: {e}")
        
        # Method 2: Try GetDefaultAudioEndpoint if available
        try:
            if hasattr(AudioUtilities, 'GetDefaultAudioEndpoint'):
                default_device = AudioUtilities.GetDefaultAudioEndpoint(0, 0)  # eRender, eConsole
                if default_device:
                    device_id = getattr(default_device, 'id', None)
                    device_name = getattr(default_device, 'FriendlyName', '') or getattr(default_device, 'name', '')
                    
                    # Even if name is a placeholder, try to match by device ID first
                    if device_id:
                        devices = self.list_devices()
                        # Try to match by device ID (most reliable)
                        for device in devices:
                            if device['id'] == device_id:
                                device['is_default'] = True
                                logger.debug(f"Found current device via GetDefaultAudioEndpoint (matched by ID): {device['name']}")
                                self._current_device = device
                                return device
                        
                        # If not found by ID, try matching by name (if name is not a placeholder)
                        if not is_placeholder_name(device_name):
                            for device in devices:
                                if device['name'] == device_name:
                                    device['is_default'] = True
                                    logger.debug(f"Found current device via GetDefaultAudioEndpoint (matched by name): {device['name']}")
                                    self._current_device = device
                                    return device
                            
                            # If not in filtered list but has a real name, return it
                            device_info = {
                                'id': device_id,
                                'name': device_name,
                                'description': getattr(default_device, 'Description', '') or device_name,
                                'state': getattr(default_device, 'State', 0),
                                'is_default': True
                            }
                            logger.debug(f"Found current device via GetDefaultAudioEndpoint: {device_info['name']}")
                            self._current_device = device_info
                            return device_info
                        else:
                            logger.debug(f"GetDefaultAudioEndpoint returned placeholder name but device ID {device_id[:50]}... - will try other methods")
                    else:
                        logger.debug(f"Skipping device from GetDefaultAudioEndpoint: no device ID available")
        except Exception as e:
            logger.debug(f"Could not get current device via GetDefaultAudioEndpoint: {e}")
        
        # Method 3: Try using Windows Registry to get the default audio device
        try:
            import winreg
            
            # Try to read the default audio device from Windows Registry
            try:
                # Open the audio registry key
                audio_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
                )
                
                # Look for the default device
                try:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(audio_key, i)
                            subkey = winreg.OpenKey(audio_key, subkey_name)
                            
                            # Check if this is the default device
                            try:
                                default_value = winreg.QueryValueEx(subkey, "{0.0.0.00000000}.{e06d8033-0db7-4b9f-bc56-5c2ce654c4d0}")
                                if default_value[0] == 1:  # This is the default device
                                    # Get the device name
                                    device_name = None
                                    try:
                                        device_name_value = winreg.QueryValueEx(subkey, "FriendlyName")
                                        device_name = device_name_value[0]
                                    except FileNotFoundError:
                                        pass  # FriendlyName not found, continue
                                    
                                    # Try to match by device ID first (subkey_name contains the device ID)
                                    devices = self.list_devices()
                                    for device in devices:
                                        # Try matching by ID (subkey_name might match device ID)
                                        if device['id'] == subkey_name or (device_name and device['name'] == device_name):
                                            device['is_default'] = True
                                            logger.debug(f"Found current device via Registry (matched by {'ID' if device['id'] == subkey_name else 'name'}): {device['name']}")
                                            self._current_device = device
                                            return device
                                    
                                    # If not found in our list but has a real name, create a device info entry
                                    if device_name and not is_placeholder_name(device_name):
                                        device_info = {
                                            'id': subkey_name,
                                            'name': device_name,
                                            'description': device_name,
                                            'state': 1,  # Assume active
                                            'is_default': True
                                        }
                                        logger.debug(f"Found current device via Registry: {device_info['name']}")
                                        self._current_device = device_info
                                        return device_info
                                    elif device_name:
                                        logger.debug(f"Registry found default device but name is placeholder: {device_name}")
                                    else:
                                        logger.debug(f"Registry found default device but no FriendlyName available (ID: {subkey_name[:50]}...)")
                                        
                            except FileNotFoundError:
                                pass  # Default value not found, continue
                                
                            winreg.CloseKey(subkey)
                            i += 1
                            
                        except OSError:
                            break  # No more subkeys
                            
                finally:
                    winreg.CloseKey(audio_key)
                    
            except FileNotFoundError:
                logger.debug("Audio registry key not found")
                
        except Exception as e:
            logger.debug(f"Error in Registry fallback: {e}")
        
        # Method 4: Try to match device ID from GetSpeakers with our filtered list
        # This handles the case where GetSpeakers returns a placeholder name but valid ID
        try:
            if hasattr(AudioUtilities, 'GetSpeakers'):
                default_device = AudioUtilities.GetSpeakers()
                if default_device:
                    device_id = getattr(default_device, 'id', None)
                    if device_id:
                        devices = self.list_devices()
                        # Try to find the device by matching the ID with GetAllDevices
                        all_devices = AudioUtilities.GetAllDevices()
                        for api_device in all_devices:
                            try:
                                api_device_id = getattr(api_device, 'id', None)
                                if api_device_id == device_id:
                                    # Found the matching device in GetAllDevices, now match with filtered list
                                    api_device_name = getattr(api_device, 'FriendlyName', '') or getattr(api_device, 'name', '')
                                    if not is_placeholder_name(api_device_name):
                                        # Try to match by name with our filtered devices
                                        for device in devices:
                                            if device['name'] == api_device_name:
                                                logger.debug(f"Found current device via GetSpeakers ID matching: {device['name']}")
                                                device['is_default'] = True
                                                self._current_device = device
                                                return device
                                        
                                        # Try matching by ID
                                        for device in devices:
                                            if device['id'] == device_id:
                                                logger.debug(f"Found current device via GetSpeakers ID matching (by ID): {device['name']}")
                                                device['is_default'] = True
                                                self._current_device = device
                                                return device
                                    break
                            except Exception:
                                continue
        except Exception as e:
            logger.debug(f"Error in GetSpeakers ID matching: {e}")
        
        # Method 5: Try to find the active device from our filtered list
        try:
            devices = self.list_devices()
            logger.debug(f"Checking {len(devices)} devices to find current device")
            
            # First, try to find devices that are active (State == 1)
            active_devices = [d for d in devices if d.get('state', 0) == 1]
            if active_devices:
                # Prefer devices that are not placeholders
                for device in active_devices:
                    if not is_placeholder_name(device.get('name', '')):
                        logger.debug(f"Found current active device: {device['name']}")
                        device['is_default'] = True
                        self._current_device = device
                        return device
                
                # If all active devices are placeholders, return the first active one
                if active_devices:
                    logger.debug(f"Using first active device (may be placeholder): {active_devices[0]['name']}")
                    active_devices[0]['is_default'] = True
                    self._current_device = active_devices[0]
                    return active_devices[0]
            
            # If no active devices, try to match with devices from GetAllDevices
            all_devices = AudioUtilities.GetAllDevices()
            for device in all_devices:
                try:
                    device_id = getattr(device, 'id', None)
                    device_name = getattr(device, 'FriendlyName', '') or getattr(device, 'name', '')
                    device_state = getattr(device, 'State', 0)
                    
                    # Skip placeholders and inactive devices
                    if is_placeholder_name(device_name) or device_state != 1:
                        continue
                    
                    # Try to match with our filtered devices
                    for our_device in devices:
                        if our_device['id'] == device_id or our_device['name'] == device_name:
                            logger.debug(f"Found current device via enumeration: {our_device['name']}")
                            our_device['is_default'] = True
                            self._current_device = our_device
                            return our_device
                            
                except Exception as device_error:
                    logger.debug(f"Error checking device: {device_error}")
                    continue
                    
        except Exception as e:
            logger.debug(f"Error in device enumeration: {e}")
        
        # Method 6: Try using sounddevice library (more reliable for device detection)
        if sounddevice_available:
            try:
                default_output_id = sd.default.device['output']
                if default_output_id is not None:
                    device_info = sd.query_devices(default_output_id)
                    device_name = device_info.get('name', '')
                    
                    if device_name and not is_placeholder_name(device_name):
                        logger.debug(f"Found current device via sounddevice: {device_name}")
                        
                        # Try to match with our filtered device list
                        devices = self.list_devices()
                        for device in devices:
                            # Try exact name match first
                            if device['name'] == device_name:
                                device['is_default'] = True
                                logger.debug(f"Matched sounddevice device with filtered list: {device['name']}")
                                self._current_device = device
                                return device
                            
                            # Try partial name match (device names might vary slightly)
                            if device_name.lower() in device['name'].lower() or device['name'].lower() in device_name.lower():
                                device['is_default'] = True
                                logger.debug(f"Matched sounddevice device (partial match): {device['name']}")
                                self._current_device = device
                                return device
                        
                        # If not found in filtered list, create device info entry
                        device_info_dict = {
                            'id': str(default_output_id),
                            'name': device_name,
                            'description': device_info.get('name', ''),
                            'state': 1,  # Assume active if it's the default
                            'is_default': True
                        }
                        logger.debug(f"Found current device via sounddevice (not in filtered list): {device_info_dict['name']}")
                        self._current_device = device_info_dict
                        return device_info_dict
                    else:
                        logger.debug(f"sounddevice returned placeholder device: {device_name}")
            except Exception as e:
                logger.debug(f"Error using sounddevice: {e}")
        
        # Final fallback: return None if we can't determine the current device
        logger.warning("Could not determine the current audio device using any method")
        return None
    
    def switch_to_device(self, device_name: str) -> bool:
        """
        Switch to a specific audio output device by name.
        
        Args:
            device_name: Name of the device to switch to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            devices = self.list_devices()
            target_device = None
            
            # Find device by name (case-insensitive)
            for device in devices:
                if device_name.lower() in device['name'].lower():
                    target_device = device
                    break
            
            if not target_device:
                logger.error(f"Device '{device_name}' not found")
                return False
            
            # Get the device object
            audio_devices = AudioUtilities.GetAllDevices()
            device_obj = None
            
            for device in audio_devices:
                if device.id == target_device['id']:
                    device_obj = device
                    break
            
            if not device_obj:
                logger.error(f"Could not get device object for '{device_name}'")
                return False
            
            # Proceed with device switching (no admin privileges required with PowerShell)
            logger.info(f"Switching to device: {target_device['name']}")
            self._current_device = target_device
            
            # Try Windows Registry-based device switching (no admin privileges required)
            success = self._switch_device_with_registry(target_device['name'])
            if success:
                logger.info(f"Successfully switched to device: {target_device['name']}")
                return True
            
            # Fallback: Try PowerShell AudioDevice module
            success = self._switch_device_with_powershell(target_device['name'])
            if success:
                logger.info(f"Successfully switched to device: {target_device['name']}")
                return True
            
            # Final fallback: Log the attempt
            logger.warning(f"Could not switch to device: {target_device['name']}. Audio device switching may require manual intervention.")
            return False
                
        except Exception as e:
            logger.error(f"Error switching to device '{device_name}': {e}")
            return False
    
    def _switch_device_with_registry(self, device_name: str) -> bool:
        """
        Switch audio device using Windows Registry manipulation.
        This approach modifies the default audio device in the registry.
        
        Args:
            device_name: Name of the device to switch to
            
        Returns:
            True if successful, False otherwise
        """
        # TODO: Registry modification disabled until thoroughly validated
        # Registry modifications can potentially cause system instability
        # and should be thoroughly tested before enabling
        logger.warning("Registry-based audio device switching is disabled for safety")
        logger.warning("TODO: Enable registry method after thorough validation and testing")
        return False
        
        # DISABLED CODE BELOW - DO NOT ENABLE WITHOUT THOROUGH TESTING
        """
        try:
            import platform
            if platform.system() != "Windows":
                logger.debug("Registry-based switching only available on Windows")
                return False
            
            import winreg
            
            # Registry path for audio devices
            audio_key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
            
            try:
                # Open the audio registry key
                audio_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    audio_key_path,
                    0,
                    winreg.KEY_READ
                )
                
                # Look for the target device
                target_device_id = None
                try:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(audio_key, i)
                            subkey = winreg.OpenKey(audio_key, subkey_name)
                            
                            # Get the device name
                            try:
                                device_name_value = winreg.QueryValueEx(subkey, "FriendlyName")
                                device_friendly_name = device_name_value[0]
                                
                                if device_name.lower() in device_friendly_name.lower():
                                    target_device_id = subkey_name
                                    logger.debug(f"Found target device: {device_friendly_name} (ID: {target_device_id})")
                                    break
                                    
                            except FileNotFoundError:
                                pass  # FriendlyName not found, continue
                                
                            winreg.CloseKey(subkey)
                            i += 1
                            
                        except OSError:
                            break  # No more subkeys
                            
                finally:
                    winreg.CloseKey(audio_key)
                
                if not target_device_id:
                    logger.debug(f"Device '{device_name}' not found in registry")
                    return False
                
                # Set as default device by modifying the registry
                # This requires write access to the registry
                try:
                    # Open the audio key with write access
                    audio_key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        audio_key_path,
                        0,
                        winreg.KEY_WRITE
                    )
                    
                    # Set the default device
                    default_key = winreg.OpenKey(audio_key, target_device_id, 0, winreg.KEY_WRITE)
                    
                    # Set the default device property
                    winreg.SetValueEx(default_key, "{0.0.0.00000000}.{e06d8033-0db7-4b9f-bc56-5c2ce654c4d0}", 0, winreg.REG_DWORD, 1)
                    
                    winreg.CloseKey(default_key)
                    winreg.CloseKey(audio_key)
                    
                    logger.info(f"Successfully set '{device_name}' as default device via registry")
                    return True
                    
                except PermissionError:
                    logger.debug("Registry write access denied - may require administrator privileges")
                    return False
                except Exception as reg_error:
                    logger.debug(f"Registry modification error: {reg_error}")
                    return False
                    
            except FileNotFoundError:
                logger.debug("Audio registry key not found")
                return False
                
        except Exception as e:
            logger.debug(f"Error with registry-based switching: {e}")
            return False
        """
    
    def _switch_device_with_powershell(self, device_name: str) -> bool:
        """
        Switch audio device using PowerShell AudioDevice module.
        
        Args:
            device_name: Name of the device to switch to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import subprocess
            import platform
            
            if platform.system() != "Windows":
                logger.debug("PowerShell AudioDevice module only available on Windows")
                return False
            
            # PowerShell command to install AudioDevice module if needed and switch audio device
            ps_command = f"""
            try {{
                # Try to import the AudioDevice module
                Import-Module AudioDevice -ErrorAction Stop
                Write-Output "MODULE_LOADED: AudioDevice module already available"
            }} catch {{
                Write-Output "MODULE_NOT_FOUND: AudioDevice module not installed, attempting to install..."
                try {{
                    # First, ensure NuGet provider is available
                    $nugetProvider = Get-PackageProvider -Name NuGet -ErrorAction SilentlyContinue
                    if (-not $nugetProvider -or $nugetProvider.Version -lt [Version]"2.8.5.201") {{
                        Write-Output "INSTALLING_NUGET: Installing NuGet provider..."
                        Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope CurrentUser -ErrorAction Stop
                        Write-Output "NUGET_INSTALLED: NuGet provider installed successfully"
                    }}
                    
                    # Install the AudioDevice module
                    Install-Module -Name AudioDevice -Force -Scope CurrentUser -ErrorAction Stop
                    Write-Output "MODULE_INSTALLED: AudioDevice module installed successfully"
                    
                    # Import the newly installed module
                    Import-Module AudioDevice -ErrorAction Stop
                    Write-Output "MODULE_LOADED: AudioDevice module loaded successfully"
                }} catch {{
                    Write-Output "MODULE_INSTALL_FAILED: $($_.Exception.Message)"
                    exit 1
                }}
            }}
            
            try {{
                # Get all audio devices
                $devices = Get-AudioDevice -List
                
                # Find the target device (case-insensitive)
                $targetDevice = $devices | Where-Object {{ $_.Name -like "*{device_name}*" }}
                
                if ($targetDevice) {{
                    # Set as default device
                    Set-AudioDevice -Index $targetDevice.Index
                    Write-Output "SUCCESS: Switched to $($targetDevice.Name)"
                }} else {{
                    Write-Output "DEVICE_NOT_FOUND: No device matching '{device_name}'"
                    Write-Output "AVAILABLE_DEVICES: $($devices.Name -join '; ')"
                }}
            }} catch {{
                Write-Output "ERROR: $($_.Exception.Message)"
            }}
            """
            
            logger.debug(f"Executing PowerShell command for device: {device_name}")
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=60  # Increased timeout for module installation
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                logger.debug(f"PowerShell output: {output}")
                
                if "SUCCESS:" in output:
                    logger.info(f"Successfully switched to '{device_name}' using PowerShell AudioDevice module")
                    return True
                elif "MODULE_INSTALLED:" in output:
                    logger.info("AudioDevice module installed successfully")
                    # Continue processing - the module should now be available
                    if "SUCCESS:" in output:
                        logger.info(f"Successfully switched to '{device_name}' using newly installed PowerShell AudioDevice module")
                        return True
                    elif "DEVICE_NOT_FOUND:" in output:
                        logger.debug(f"Device '{device_name}' not found in PowerShell")
                        return False
                elif "NUGET_INSTALLED:" in output:
                    logger.info("NuGet provider installed successfully")
                    # Continue processing
                    if "SUCCESS:" in output:
                        logger.info(f"Successfully switched to '{device_name}' using PowerShell AudioDevice module")
                        return True
                    elif "DEVICE_NOT_FOUND:" in output:
                        logger.debug(f"Device '{device_name}' not found in PowerShell")
                        return False
                elif "MODULE_LOADED:" in output:
                    logger.debug("AudioDevice module loaded successfully")
                    # Continue processing
                    if "SUCCESS:" in output:
                        logger.info(f"Successfully switched to '{device_name}' using PowerShell AudioDevice module")
                        return True
                    elif "DEVICE_NOT_FOUND:" in output:
                        logger.debug(f"Device '{device_name}' not found in PowerShell")
                        return False
                elif "MODULE_INSTALL_FAILED:" in output:
                    logger.warning(f"Failed to install AudioDevice module: {output}")
                    return False
                elif "DEVICE_NOT_FOUND:" in output:
                    logger.debug(f"Device '{device_name}' not found in PowerShell")
                    # Log available devices for debugging
                    if "AVAILABLE_DEVICES:" in output:
                        available_devices = output.split("AVAILABLE_DEVICES: ")[1] if "AVAILABLE_DEVICES:" in output else "Unknown"
                        logger.debug(f"Available devices: {available_devices}")
                    return False
                elif "ERROR:" in output:
                    logger.debug(f"PowerShell command error: {output}")
                    return False
                else:
                    logger.debug(f"Unexpected PowerShell output: {output}")
                    return False
            else:
                logger.debug(f"PowerShell command failed with return code {result.returncode}: {result.stderr}")
                return False
            
        except subprocess.TimeoutExpired:
            logger.debug("PowerShell command timed out")
            return False
        except Exception as e:
            logger.debug(f"Error using PowerShell: {e}")
            return False
    
    def _switch_device_with_wasapi(self, device_name: str) -> bool:
        """
        Route audio to specific device using Windows Audio Session API (per-application).
        This doesn't change the system default, but routes this application's audio.
        
        Args:
            device_name: Name of the device to route audio to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import platform
            if platform.system() != "Windows":
                logger.debug("WASAPI only available on Windows")
                return False
            
            # Try to use pycaw for per-application audio routing
            try:
                from pycaw.pycaw import AudioUtilities, AudioSession
                
                # Get all audio devices
                devices = AudioUtilities.GetAllDevices()
                target_device = None
                
                # Find the target device
                for device in devices:
                    device_name_attr = getattr(device, 'FriendlyName', '') or getattr(device, 'name', '')
                    if device_name.lower() in device_name_attr.lower():
                        target_device = device
                        break
                
                if not target_device:
                    logger.debug(f"Device '{device_name}' not found for per-application routing")
                    return False
                
                # Get the audio session for this application
                sessions = AudioUtilities.GetAllSessions()
                current_session = None
                
                # Find the current application's audio session
                import os
                current_pid = os.getpid()
                for session in sessions:
                    if hasattr(session, 'ProcessId') and session.ProcessId == current_pid:
                        current_session = session
                        break
                
                if current_session:
                    # Set the audio endpoint for this session
                    # Note: This is a simplified approach - actual implementation may vary
                    logger.info(f"Routing application audio to '{device_name}' (per-application)")
                    logger.info("Note: This only affects this application's audio, not system-wide default")
                    
                    # Store the target device for this session
                    self._current_device = {
                        'id': getattr(target_device, 'id', 'unknown'),
                        'name': device_name,
                        'description': getattr(target_device, 'Description', '') or device_name,
                        'state': getattr(target_device, 'State', 0),
                        'is_default': False,
                        'per_application': True
                    }
                    
                    return True
                else:
                    logger.debug("Could not find current application's audio session")
                    return False
                    
            except ImportError:
                logger.debug("pycaw not available for per-application audio routing")
                return False
            except Exception as e:
                logger.debug(f"Error with WASAPI per-application routing: {e}")
                return False
            
        except Exception as e:
            logger.debug(f"Error with WASAPI routing: {e}")
            return False
    
    def set_day_night_schedule(self, 
                             day_device: str = None, 
                             night_device: str = None,
                             day_start: dt_time = None,
                             night_start: dt_time = None) -> bool:
        """
        Set up automatic day/night device switching.
        
        Args:
            day_device: Name of device to use during day
            night_device: Name of device to use at night
            day_start: Time to switch to day device (default: 7:00 AM)
            night_start: Time to switch to night device (default: 10:00 PM)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if day_device:
                self._day_device = day_device
                AudioDeviceManager._cached_day_device = day_device
            if night_device:
                self._night_device = night_device
                AudioDeviceManager._cached_night_device = night_device
            if day_start:
                self._day_start_time = day_start
                AudioDeviceManager._cached_day_start_time = day_start
            if night_start:
                self._night_start_time = night_start
                AudioDeviceManager._cached_night_start_time = night_start
            
            # Validate devices exist
            devices = self.list_devices()
            device_names = [d['name'] for d in devices]
            
            if self._day_device and self._day_device not in device_names:
                logger.error(f"Day device '{self._day_device}' not found")
                return False
            
            if self._night_device and self._night_device not in device_names:
                logger.error(f"Night device '{self._night_device}' not found")
                return False
            
            logger.info(f"Day/night schedule set: Day={self._day_device} ({self._day_start_time}), "
                       f"Night={self._night_device} ({self._night_start_time})")
            
            # Store settings to cache
            AudioDeviceManager.store_settings()
            
            return True
            
        except Exception as e:
            logger.error(f"Error setting day/night schedule: {e}")
            return False
    
    def start_monitoring(self) -> bool:
        """
        Start monitoring for automatic day/night switching.
        
        Returns:
            True if monitoring started successfully
        """
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Monitoring is already running")
            return True
        
        if not self._day_device or not self._night_device:
            logger.error("Day and night devices must be set before starting monitoring")
            return False
        
        self._stop_monitoring.clear()
        self._monitoring_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitoring_thread.start()
        
        # Update class variable
        AudioDeviceManager._cached_monitoring_enabled = True
        
        logger.info("Started audio device monitoring")
        return True
    
    def stop_monitoring(self):
        """Stop the monitoring thread."""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._stop_monitoring.set()
            self._monitoring_thread.join(timeout=5)
            
            # Update class variable
            AudioDeviceManager._cached_monitoring_enabled = False
            
            logger.info("Stopped audio device monitoring")
    
    def _monitor_loop(self):
        """Internal monitoring loop for day/night switching."""
        while not self._stop_monitoring.is_set():
            try:
                current_time = datetime.now().time()
                
                # Determine which device should be active
                if self._is_night_time(current_time):
                    target_device = self._night_device
                else:
                    target_device = self._day_device
                
                # Switch if needed
                if target_device and self._current_device:
                    if target_device.lower() not in self._current_device['name'].lower():
                        logger.info(f"Auto-switching to {target_device} (time: {current_time})")
                        self.switch_to_device(target_device)
                
                # Check every minute
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)
    
    def _is_night_time(self, current_time: dt_time) -> bool:
        """
        Determine if current time is night time.
        
        Args:
            current_time: Current time
            
        Returns:
            True if it's night time, False otherwise
        """
        if self._night_start_time > self._day_start_time:
            # Normal case: night starts after day (e.g., 22:00 to 07:00)
            return current_time >= self._night_start_time or current_time < self._day_start_time
        else:
            # Edge case: night starts before day (e.g., 07:00 to 22:00)
            return self._night_start_time <= current_time < self._day_start_time
    
    def get_device_volume(self, device_name: str) -> Optional[float]:
        """
        Get the volume level of a specific device.
        
        Args:
            device_name: Name of the device
            
        Returns:
            Volume level (0.0 to 1.0), or None if not found
        """
        if AudioEndpointVolume is None:
            logger.warning("AudioEndpointVolume not available - volume control disabled")
            return None
            
        try:
            devices = self.list_devices()
            target_device = None
            
            for device in devices:
                if device_name.lower() in device['name'].lower():
                    target_device = device
                    break
            
            if not target_device:
                return None
            
            # Get device object and volume
            audio_devices = AudioUtilities.GetAllDevices()
            device_obj = None
            
            for device in audio_devices:
                if device.id == target_device['id']:
                    device_obj = device
                    break
            
            if device_obj:
                # Get volume interface
                volume = device_obj.Activate(AudioEndpointVolume._iid_, 0, None)
                return volume.GetMasterScalarVolume()
            
        except Exception as e:
            logger.error(f"Error getting volume for device '{device_name}': {e}")
        
        return None
    
    def set_device_volume(self, device_name: str, volume: float) -> bool:
        """
        Set the volume level of a specific device.
        
        Args:
            device_name: Name of the device
            volume: Volume level (0.0 to 1.0)
            
        Returns:
            True if successful, False otherwise
        """
        if AudioEndpointVolume is None:
            logger.warning("AudioEndpointVolume not available - volume control disabled")
            return False
            
        try:
            volume = max(0.0, min(1.0, volume))  # Clamp to valid range
            
            devices = self.list_devices()
            target_device = None
            
            for device in devices:
                if device_name.lower() in device['name'].lower():
                    target_device = device
                    break
            
            if not target_device:
                logger.error(f"Device '{device_name}' not found")
                return False
            
            # Get device object and set volume
            audio_devices = AudioUtilities.GetAllDevices()
            device_obj = None
            
            for device in audio_devices:
                if device.id == target_device['id']:
                    device_obj = device
                    break
            
            if device_obj:
                # Get volume interface and set volume
                volume_interface = device_obj.Activate(AudioEndpointVolume._iid_, 0, None)
                volume_interface.SetMasterScalarVolume(volume, None)
                logger.info(f"Set volume for '{device_name}' to {volume:.2f}")
                return True
            
        except Exception as e:
            logger.error(f"Error setting volume for device '{device_name}': {e}")
        
        return False
    
    def check_and_apply_settings(self, app_actions=None):
        """
        Check and apply audio device settings based on current time and schedule.
        Alerts the user if there's a device mismatch.
        
        Args:
            app_actions: Optional AppActions instance for showing alerts and toasts
        """
        try:
            # Check if we have day/night devices configured
            if not self.day_device or not self.night_device:
                logger.debug("No day/night devices configured, skipping audio device check")
                return
            
            logger.info("Checking audio device settings based on current time")
            
            # Get current time and determine if we should switch devices
            import datetime
            now = datetime.datetime.now()
            current_hour = now.hour
            
            # Determine if it's day or night based on the schedule
            day_start = self.day_start_hour
            night_start = self.night_start_hour
            
            is_day_time = False
            if day_start <= night_start:
                # Normal case: day_start < night_start (e.g., 6 AM to 10 PM)
                is_day_time = day_start <= current_hour < night_start
            else:
                # Overnight case: day_start > night_start (e.g., 10 PM to 6 AM)
                is_day_time = current_hour >= day_start or current_hour < night_start
            
            # Get the target device for current time
            target_device = self.day_device if is_day_time else self.night_device
            time_period = 'day' if is_day_time else 'night'
            
            if target_device:
                # Check if we need to switch devices
                current_default = self.get_current_device()
                current_device_name = current_default.get('name') if current_default else None
                
                logger.info(f"Current device: {current_device_name or 'Could not detect'}")
                logger.info(f"Target device for {time_period} time: {target_device}")
                
                # Check for mismatch (case-insensitive comparison)
                mismatch = False
                device_detection_failed = False
                
                if current_device_name and target_device:
                    # Use case-insensitive comparison since device names might vary in casing
                    mismatch = current_device_name.lower() != target_device.lower()
                elif not current_device_name and target_device:
                    # Device detection failed but we have a target device - this is also a problem
                    device_detection_failed = True
                    mismatch = True  # Treat as mismatch so user gets warned
                
                if mismatch:
                    if device_detection_failed:
                        logger.warning(f"Could not detect current audio device. Expected device for {time_period} time: {target_device}")
                        
                        # Alert user if app_actions is available
                        if app_actions and hasattr(app_actions, 'alert'):
                            message = _("Audio Device Detection Failed") + "\n\n"
                            message += _("Could not detect the current audio output device.") + "\n"
                            message += _("Expected device for {0} time: {1}").format(time_period, target_device) + "\n\n"
                            message += _("Please verify that your audio device is connected and turned on, and switch to the expected device manually if needed.")
                            
                            app_actions.alert(
                                _("Audio Device Warning"),
                                message,
                                kind="warning"
                            )
                    else:
                        logger.warning(f"Audio device mismatch: Current='{current_device_name}', Expected='{target_device}' for {time_period} time")
                        
                        # Alert user if app_actions is available
                        if app_actions and hasattr(app_actions, 'alert'):
                            message = _("Audio Device Mismatch") + "\n\n"
                            message += _("Current device: {0}").format(current_device_name or 'Unknown') + "\n"
                            message += _("Expected device for {0} time: {1}").format(time_period, target_device) + "\n\n"
                            message += _("Please switch to the expected device manually if needed.")
                            
                            app_actions.alert(
                                _("Audio Device Warning"),
                                message,
                                kind="warning"
                            )
                    
                    # TODO: Audio device switching disabled until safe methods are validated
                    # Device switching methods need thorough testing before enabling
                    # to avoid potential system instability or unexpected behavior
                    logger.warning("TODO: Audio device switching is disabled for safety - Enable device switching after validating safe methods")
                    
                    # DISABLED CODE BELOW - DO NOT ENABLE WITHOUT THOROUGH TESTING
                    # success = self.switch_to_device(target_device)
                    # if success:
                    #     logger.info(f"Successfully switched to audio device: {target_device}")
                    #     if app_actions and hasattr(app_actions, 'toast'):
                    #         app_actions.toast(f"Switched to {target_device} for {time_period} time")
                    # else:
                    #     logger.warning(f"Failed to switch to audio device: {target_device}")
                else:
                    logger.debug(f"Audio device already set correctly: {target_device}")
            else:
                logger.warning(f"No target device configured for {time_period} time")
                
        except Exception as e:
            logger.error(f"Error checking audio device settings: {e}")
            # Don't raise the exception to avoid breaking playback

    @property
    def day_device(self) -> Optional[str]:
        """Get the day device name."""
        return self._day_device

    @property
    def night_device(self) -> Optional[str]:
        """Get the night device name."""
        return self._night_device

    @property
    def day_start_hour(self) -> int:
        """Get the day start hour."""
        return self._day_start_time.hour

    @property
    def night_start_hour(self) -> int:
        """Get the night start hour."""
        return self._night_start_time.hour

    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active."""
        return self._monitoring_thread is not None and self._monitoring_thread.is_alive()

    @staticmethod
    def store_settings():
        """Store audio device settings to persistent cache."""
        try:
            from utils.app_info_cache import app_info_cache
            
            settings = {
                'day_device': AudioDeviceManager._cached_day_device,
                'night_device': AudioDeviceManager._cached_night_device,
                'day_start_hour': AudioDeviceManager._cached_day_start_time.hour if AudioDeviceManager._cached_day_start_time else 7,
                'day_start_minute': AudioDeviceManager._cached_day_start_time.minute if AudioDeviceManager._cached_day_start_time else 0,
                'night_start_hour': AudioDeviceManager._cached_night_start_time.hour if AudioDeviceManager._cached_night_start_time else 22,
                'night_start_minute': AudioDeviceManager._cached_night_start_time.minute if AudioDeviceManager._cached_night_start_time else 0,
                'monitoring_enabled': AudioDeviceManager._cached_monitoring_enabled
            }
            
            app_info_cache.set('audio_device_settings', settings)
            logger.info("Stored audio device settings to cache")
            
        except Exception as e:
            logger.error(f"Error storing audio device settings: {e}")

    @staticmethod
    def load_settings():
        """Load audio device settings from persistent cache."""
        try:
            from utils.app_info_cache import app_info_cache
            
            settings = app_info_cache.get('audio_device_settings', {})
            
            if settings:
                # Store settings in a class variable for instances to access
                AudioDeviceManager._cached_day_device = settings.get('day_device')
                AudioDeviceManager._cached_night_device = settings.get('night_device')
                
                # Restore time settings
                day_hour = settings.get('day_start_hour', 7)
                day_minute = settings.get('day_start_minute', 0)
                night_hour = settings.get('night_start_hour', 22)
                night_minute = settings.get('night_start_minute', 0)
                
                AudioDeviceManager._cached_day_start_time = dt_time(day_hour, day_minute)
                AudioDeviceManager._cached_night_start_time = dt_time(night_hour, night_minute)
                AudioDeviceManager._cached_monitoring_enabled = settings.get('monitoring_enabled', False)
                
                logger.info(f"Loaded audio device settings: Day={AudioDeviceManager._cached_day_device} ({AudioDeviceManager._cached_day_start_time}), "
                           f"Night={AudioDeviceManager._cached_night_device} ({AudioDeviceManager._cached_night_start_time}), "
                           f"Monitoring={AudioDeviceManager._cached_monitoring_enabled}")
                
                return True
            else:
                logger.debug("No audio device settings found in cache")
                return False
                
        except Exception as e:
            logger.error(f"Error loading audio device settings: {e}")
            return False

    def __del__(self):
        """Cleanup when object is destroyed."""
        self.stop_monitoring()


# Convenience functions for easy integration
def create_audio_manager() -> AudioDeviceManager:
    """Create and return a new AudioDeviceManager instance."""
    return AudioDeviceManager()


def quick_device_switch(device_name: str) -> bool:
    """
    Quick function to switch to a specific device.
    
    Args:
        device_name: Name of the device to switch to
        
    Returns:
        True if successful, False otherwise
    """
    manager = AudioDeviceManager()
    return manager.switch_to_device(device_name)


def setup_day_night_switching(day_device: str, night_device: str) -> bool:
    """
    Quick setup for day/night device switching.
    
    Args:
        day_device: Device name for daytime use
        night_device: Device name for nighttime use
        
    Returns:
        True if successful, False otherwise
    """
    manager = AudioDeviceManager()
    success = manager.set_day_night_schedule(day_device, night_device)
    if success:
        manager.start_monitoring()
    return success


if __name__ == "__main__":
    # Example usage
    import logging
    logging.basicConfig(level=logging.INFO)
    
    manager = AudioDeviceManager()
    
    # List all devices
    print("Available audio devices:")
    devices = manager.list_devices()
    for device in devices:
        print(f"  - {device['name']} ({'Default' if device['is_default'] else 'Available'})")
    
    # Get current device
    current = manager.get_current_device()
    if current:
        print(f"\nCurrent device: {current['name']}")
    
    # Example: Set up day/night switching
    # manager.set_day_night_schedule("Speakers", "Headphones")
    # manager.start_monitoring()
