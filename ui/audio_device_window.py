from datetime import datetime, time as dt_time

from tkinter import Toplevel, Frame, Label, Checkbutton, BooleanVar, StringVar, messagebox, Listbox, Scrollbar
from tkinter.ttk import Button, Entry, OptionMenu, Separator
from tkinter.constants import W, BOTH, YES, END, SINGLE

from ui.app_style import AppStyle
from ui.base_window import BaseWindow
from utils.translations import I18N
from utils.audio_device_manager import AudioDeviceManager
from utils.logging_setup import get_logger

_ = I18N._
logger = get_logger(__name__)


class AudioDeviceWindow(BaseWindow):
    """Window for managing audio device settings and day/night switching."""
    
    top_level = None

    def __init__(self, master, app_actions):
        super().__init__()
        
        # Create and configure top level window
        AudioDeviceWindow.top_level = Toplevel(master)
        AudioDeviceWindow.top_level.title(_("Audio Device Management"))
        AudioDeviceWindow.top_level.geometry("800x600")
        AudioDeviceWindow.top_level.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.master = AudioDeviceWindow.top_level
        self.app_actions = app_actions
        
        # Initialize audio device manager
        try:
            self.audio_manager = AudioDeviceManager()
            self.audio_available = True
            logger.info("Audio device manager initialized successfully")
        except ImportError as e:
            self.audio_manager = None
            self.audio_available = False
            logger.warning(f"Audio device manager not available: {e}")
        
        # Create main frame
        self.main_frame = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.main_frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # Initialize variables
        self.devices = []
        self.show_all_devices_var = BooleanVar(value=False)
        self.day_device_var = StringVar()
        self.night_device_var = StringVar()
        self.day_start_hour_var = StringVar(value="7")
        self.day_start_minute_var = StringVar(value="0")
        self.night_start_hour_var = StringVar(value="22")
        self.night_start_minute_var = StringVar(value="0")
        self.monitoring_enabled_var = BooleanVar(value=False)
        
        # Create UI elements
        self.create_device_list_section()
        self.create_day_night_section()
        self.create_controls_section()
        
        # Load current settings and refresh devices list
        self.load_current_settings()
        self.refresh_devices()

    def load_current_settings(self):
        """Load current audio device settings into the UI"""
        if not self.audio_available:
            return
        
        try:
            # Load day/night device settings from class variables
            if AudioDeviceManager._cached_day_device:
                self.day_device_var.set(AudioDeviceManager._cached_day_device)
            
            if AudioDeviceManager._cached_night_device:
                self.night_device_var.set(AudioDeviceManager._cached_night_device)
            
            # Load time settings from class variables
            if AudioDeviceManager._cached_day_start_time:
                self.day_start_hour_var.set(str(AudioDeviceManager._cached_day_start_time.hour))
                self.day_start_minute_var.set(str(AudioDeviceManager._cached_day_start_time.minute))
            
            if AudioDeviceManager._cached_night_start_time:
                self.night_start_hour_var.set(str(AudioDeviceManager._cached_night_start_time.hour))
                self.night_start_minute_var.set(str(AudioDeviceManager._cached_night_start_time.minute))
            
            # Load monitoring state
            self.monitoring_enabled_var.set(AudioDeviceManager._cached_monitoring_enabled)
            
            logger.info("Loaded current audio device settings into UI")
            
        except Exception as e:
            logger.error(f"Error loading current settings: {e}")

    def create_device_list_section(self):
        """Create the device list section"""
        # Device list frame
        device_frame = Frame(self.main_frame, bg=AppStyle.BG_COLOR)
        device_frame.pack(fill=BOTH, expand=YES, pady=(0, 10))
        
        # Title
        title_label = Label(device_frame, text=_("Available Audio Devices"), 
                          font=('Arial', 12, 'bold'), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        title_label.pack(pady=(0, 10))
        
        # Device list with scrollbar
        list_frame = Frame(device_frame, bg=AppStyle.BG_COLOR)
        list_frame.pack(fill=BOTH, expand=YES)
        
        self.device_listbox = Listbox(list_frame, selectmode=SINGLE, height=8)
        scrollbar = Scrollbar(list_frame, orient="vertical", command=self.device_listbox.yview)
        self.device_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.device_listbox.pack(side="left", fill=BOTH, expand=YES)
        scrollbar.pack(side="right", fill="y")
        
        # Control buttons frame
        control_frame = Frame(device_frame, bg=AppStyle.BG_COLOR)
        control_frame.pack(pady=(10, 0))
        
        # Refresh button
        refresh_button = Button(control_frame, text=_("Refresh Devices"), command=self.refresh_devices)
        refresh_button.pack(side="left", padx=(0, 10))
        
        # Show all devices checkbox
        show_all_checkbox = Checkbutton(control_frame, 
                                      text=_("Show all devices (including virtual)"),
                                      variable=self.show_all_devices_var,
                                      command=self.refresh_devices,
                                      bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR,
                                      selectcolor=AppStyle.BG_COLOR)
        show_all_checkbox.pack(side="left")

    def create_day_night_section(self):
        """Create the day/night switching section"""
        # Day/Night frame
        schedule_frame = Frame(self.main_frame, bg=AppStyle.BG_COLOR)
        schedule_frame.pack(fill="x", pady=(0, 10))
        
        # Title
        title_label = Label(schedule_frame, text=_("Day/Night Device Switching"), 
                          font=('Arial', 12, 'bold'), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        title_label.pack(pady=(0, 10))
        
        # Device selection frame
        device_selection_frame = Frame(schedule_frame, bg=AppStyle.BG_COLOR)
        device_selection_frame.pack(fill="x", pady=(0, 10))
        
        # Day device selection
        day_frame = Frame(device_selection_frame, bg=AppStyle.BG_COLOR)
        day_frame.pack(fill="x", pady=(0, 5))
        
        Label(day_frame, text=_("Day Device:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side="left")
        self.day_device_menu = OptionMenu(day_frame, self.day_device_var, "")
        self.day_device_menu.pack(side="left", padx=(10, 0))
        
        # Night device selection
        night_frame = Frame(device_selection_frame, bg=AppStyle.BG_COLOR)
        night_frame.pack(fill="x", pady=(0, 5))
        
        Label(night_frame, text=_("Night Device:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side="left")
        self.night_device_menu = OptionMenu(night_frame, self.night_device_var, "")
        self.night_device_menu.pack(side="left", padx=(10, 0))
        
        # Time settings frame
        time_frame = Frame(schedule_frame, bg=AppStyle.BG_COLOR)
        time_frame.pack(fill="x", pady=(0, 10))
        
        # Day start time
        day_time_frame = Frame(time_frame, bg=AppStyle.BG_COLOR)
        day_time_frame.pack(side="left", padx=(0, 20))
        
        Label(day_time_frame, text=_("Day Start:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side="left")
        
        self.day_hour_menu = OptionMenu(day_time_frame, self.day_start_hour_var, 
                                       *[str(i).zfill(2) for i in range(24)])
        self.day_hour_menu.pack(side="left", padx=(5, 2))
        
        Label(day_time_frame, text=":", bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side="left")
        
        self.day_minute_menu = OptionMenu(day_time_frame, self.day_start_minute_var, 
                                        *[str(i).zfill(2) for i in range(0, 60, 15)])
        self.day_minute_menu.pack(side="left", padx=(2, 0))
        
        # Night start time
        night_time_frame = Frame(time_frame, bg=AppStyle.BG_COLOR)
        night_time_frame.pack(side="left")
        
        Label(night_time_frame, text=_("Night Start:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side="left")
        
        self.night_hour_menu = OptionMenu(night_time_frame, self.night_start_hour_var, 
                                        *[str(i).zfill(2) for i in range(24)])
        self.night_hour_menu.pack(side="left", padx=(5, 2))
        
        Label(night_time_frame, text=":", bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).pack(side="left")
        
        self.night_minute_menu = OptionMenu(night_time_frame, self.night_start_minute_var, 
                                         *[str(i).zfill(2) for i in range(0, 60, 15)])
        self.night_minute_menu.pack(side="left", padx=(2, 0))
        
        # Monitoring status
        monitoring_frame = Frame(schedule_frame, bg=AppStyle.BG_COLOR)
        monitoring_frame.pack(fill="x", pady=(10, 0))
        
        self.monitoring_checkbox = Checkbutton(monitoring_frame, 
                                             text=_("Enable automatic day/night switching"),
                                             variable=self.monitoring_enabled_var,
                                             command=self.toggle_monitoring,
                                             bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR,
                                             selectcolor=AppStyle.BG_COLOR)
        self.monitoring_checkbox.pack(side="left")

    def create_controls_section(self):
        """Create the control buttons section"""
        # Controls frame
        controls_frame = Frame(self.main_frame, bg=AppStyle.BG_COLOR)
        controls_frame.pack(fill="x", pady=(10, 0))
        
        # Separator
        separator = Separator(controls_frame, orient='horizontal')
        separator.pack(fill="x", pady=(0, 10))
        
        # Buttons frame
        buttons_frame = Frame(controls_frame, bg=AppStyle.BG_COLOR)
        buttons_frame.pack(fill="x")
        
        # Apply settings button
        apply_button = Button(buttons_frame, text=_("Apply Settings"), command=self.apply_settings)
        apply_button.pack(side="left", padx=(0, 10))
        
        # Test day/night button
        test_button = Button(buttons_frame, text=_("Test Day/Night Switch"), command=self.test_day_night)
        test_button.pack(side="left", padx=(0, 10))
        
        # Close button
        close_button = Button(buttons_frame, text=_("Close"), command=self.on_closing)
        close_button.pack(side="right")

    def refresh_devices(self):
        """Refresh the list of available audio devices"""
        if not self.audio_available:
            self.device_listbox.delete(0, END)
            self.device_listbox.insert(END, _("Audio device management not available"))
            self.device_listbox.insert(END, _("Install pycaw and comtypes to enable this feature"))
            return
        
        try:
            # Get devices from audio manager (filtered or all based on checkbox)
            if self.show_all_devices_var.get():
                self.devices = self.audio_manager.list_all_devices(refresh=True)
                logger.info(f"Refreshed all audio devices, found {len(self.devices)} devices")
            else:
                self.devices = self.audio_manager.list_devices(refresh=True)
                logger.info(f"Refreshed filtered audio devices, found {len(self.devices)} devices")
            
            # Clear and populate listbox
            self.device_listbox.delete(0, END)
            
            if not self.devices:
                self.device_listbox.insert(END, _("No audio devices found"))
                logger.warning("No audio devices found")
                return
            
            # Populate device list
            device_names = []
            for i, device in enumerate(self.devices):
                status = " (Default)" if device.get('is_default', False) else ""
                state_info = ""
                
                # Add state information
                state = device.get('state', 0)
                if state == 1:  # DeviceStateActive
                    state_info = " [Active]"
                elif state == 2:  # DeviceStateDisabled
                    state_info = " [Disabled]"
                elif state == 4:  # DeviceStateNotPresent
                    state_info = " [Not Present]"
                
                device_text = f"{i+1}. {device['name']}{status}{state_info}"
                self.device_listbox.insert(END, device_text)
                device_names.append(device['name'])
            
            # Update device menus
            self.update_device_menus(device_names)
            
            # Add separator and show recently used devices
            self.device_listbox.insert(END, "")
            self.device_listbox.insert(END, "--- Recently Used Devices ---")
            
            recent_devices = self.audio_manager.get_recently_used_devices(limit=3)
            for i, device in enumerate(recent_devices):
                device_text = f"★ {device['name']}"
                self.device_listbox.insert(END, device_text)
            
            # Get current default device
            default_device = self.audio_manager.get_default_device()
            if default_device:
                self.device_listbox.insert(END, "")
                self.device_listbox.insert(END, f"Current Default: {default_device['name']}")
                logger.info(f"Current default device: {default_device['name']}")
            
        except Exception as e:
            logger.error(f"Error refreshing devices: {e}")
            self.device_listbox.delete(0, END)
            self.device_listbox.insert(END, f"Error loading devices: {str(e)}")

    def update_device_menus(self, device_names):
        """Update the device selection menus"""
        # Update day device menu
        self.day_device_menu['menu'].delete(0, END)
        for device_name in device_names:
            self.day_device_menu['menu'].add_command(label=device_name, 
                                                   command=lambda name=device_name: self.day_device_var.set(name))
        
        # Update night device menu
        self.night_device_menu['menu'].delete(0, END)
        for device_name in device_names:
            self.night_device_menu['menu'].add_command(label=device_name, 
                                                     command=lambda name=device_name: self.night_device_var.set(name))
        
        # Auto-select common devices if available
        for device_name in device_names:
            name_lower = device_name.lower()
            if 'speaker' in name_lower or 'monitor' in name_lower:
                if not self.day_device_var.get():
                    self.day_device_var.set(device_name)
            elif 'headphone' in name_lower or 'headset' in name_lower:
                if not self.night_device_var.get():
                    self.night_device_var.set(device_name)

    def toggle_monitoring(self):
        """Toggle automatic monitoring"""
        if not self.audio_available:
            self.app_actions.alert(_("Error"), _("Audio device management not available"), kind="error")
            return
        
        try:
            if self.monitoring_enabled_var.get():
                # Start monitoring
                success = self.audio_manager.start_monitoring()
                if success:
                    self.app_actions.toast(_("Audio device monitoring started"))
                    AudioDeviceManager.store_settings()
                else:
                    self.monitoring_enabled_var.set(False)
                    self.app_actions.alert(_("Error"), _("Failed to start monitoring"), kind="error")
            else:
                # Stop monitoring
                self.audio_manager.stop_monitoring()
                self.app_actions.toast(_("Audio device monitoring stopped"))
                AudioDeviceManager.store_settings()
        except Exception as e:
            self.monitoring_enabled_var.set(False)
            self.app_actions.alert(_("Error"), str(e), kind="error")

    def apply_settings(self):
        """Apply the current settings"""
        if not self.audio_available:
            self.app_actions.alert(_("Error"), _("Audio device management not available"), kind="error")
            return
        
        try:
            # Get selected devices
            day_device = self.day_device_var.get()
            night_device = self.night_device_var.get()
            
            if not day_device or not night_device:
                self.app_actions.alert(_("Error"), _("Please select both day and night devices"), kind="error")
                return
            
            # Get time settings
            day_hour = int(self.day_start_hour_var.get())
            day_minute = int(self.day_start_minute_var.get())
            night_hour = int(self.night_start_hour_var.get())
            night_minute = int(self.night_start_minute_var.get())
            
            day_start_time = dt_time(day_hour, day_minute)
            night_start_time = dt_time(night_hour, night_minute)
            
            # Apply day/night schedule
            success = self.audio_manager.set_day_night_schedule(
                day_device=day_device,
                night_device=night_device,
                day_start=day_start_time,
                night_start=night_start_time
            )
            
            if success:
                self.app_actions.toast(_("Audio device settings applied successfully"))
                
                # Start monitoring if enabled
                if self.monitoring_enabled_var.get():
                    self.audio_manager.start_monitoring()
            else:
                self.app_actions.alert(_("Error"), _("Failed to apply audio device settings"), kind="error")
                
        except Exception as e:
            self.app_actions.alert(_("Error"), str(e), kind="error")

    def test_day_night(self):
        """Test the day/night switching functionality"""
        if not self.audio_available:
            self.app_actions.alert(_("Error"), _("Audio device management not available"), kind="error")
            return
        
        try:
            # Get current time and determine which device should be active
            current_time = datetime.now().time()
            day_device = self.day_device_var.get()
            night_device = self.night_device_var.get()
            
            if not day_device or not night_device:
                self.app_actions.alert(_("Error"), _("Please select both day and night devices"), kind="error")
                return
            
            # Get time settings
            day_hour = int(self.day_start_hour_var.get())
            day_minute = int(self.day_start_minute_var.get())
            night_hour = int(self.night_start_hour_var.get())
            night_minute = int(self.night_start_minute_var.get())
            
            day_start_time = dt_time(day_hour, day_minute)
            night_start_time = dt_time(night_hour, night_minute)
            
            # Determine which device should be active
            if self.audio_manager._is_night_time(current_time):
                target_device = night_device
                time_period = "night"
            else:
                target_device = day_device
                time_period = "day"
            
            # Switch to the appropriate device
            success = self.audio_manager.switch_to_device(target_device)
            
            if success:
                self.app_actions.toast(_("Switched to {} device for {} time").format(target_device, time_period))
            else:
                self.app_actions.alert(_("Error"), _("Failed to switch audio device"), kind="error")
                
        except Exception as e:
            self.app_actions.alert(_("Error"), str(e), kind="error")

    def on_closing(self):
        """Handle window closing"""
        if self.audio_available and self.audio_manager:
            # Stop monitoring when window closes
            self.audio_manager.stop_monitoring()
        
        self.master.destroy()
        self.master = None
