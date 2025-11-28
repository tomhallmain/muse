from tkinter import Frame, Label, Button, Entry, Scale, StringVar, IntVar, messagebox
from tkinter.ttk import Frame as TtkFrame, Label as TtkLabel, Button as TtkButton, Entry as TtkEntry, Progressbar, LabelFrame
from tkinter.constants import W, E, N, S, BOTH, YES, X, HORIZONTAL, DISABLED, NORMAL
import threading
import time

from lib.multi_display import SmartToplevel
from muse.timer import Timer
from ui.base_window import BaseWindow
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)

_ = I18N._

class TimerWindow(BaseWindow):
    def __init__(self, master, app_actions):
        super().__init__(master=master, app_actions=app_actions)
        
        # Try to get the current playback instance and set it for the timer
        try:
            # Get the app instance from the master
            app_instance = master.master if hasattr(master, 'master') else None
            if app_instance and hasattr(app_instance, 'current_run') and app_instance.current_run:
                playback_instance = app_instance.current_run.get_playback()
                if playback_instance:
                    Timer().set_playback_instance(playback_instance)
        except Exception as e:
            print(f"Warning: Could not set playback instance for timer: {e}")
        
        # Create and configure top level window
        self.top_level = SmartToplevel(persistent_parent=master, title="Timer", geometry="400x360", auto_position=False)
        self.top_level.resizable(True, True)
        
        # Configure grid weights
        self.top_level.grid_columnconfigure(0, weight=1)
        self.top_level.grid_rowconfigure(1, weight=1)
        
        # Create main frame
        self.main_frame = TtkFrame(self.top_level)
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # Timer input section
        self.create_timer_input_section()
        
        # Timer display section
        self.create_timer_display_section()
        
        # Control buttons section
        self.create_control_buttons_section()
        
        # Sync UI with current timer state
        self.sync_ui_with_timer()
        
        # Start update thread
        self.update_thread = threading.Thread(target=self.update_display, daemon=True)
        self._stop_update = False
        self.update_thread.start()
        
        # Bind window close event
        self.top_level.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Center the window
        self.center_window()
        
        # Make window modal
        self.top_level.transient(master)
        self.top_level.grab_set()
    
    def center_window(self):
        """Center the window on screen"""
        self.top_level.update_idletasks()
        width = self.top_level.winfo_width()
        height = self.top_level.winfo_height()
        x = (self.top_level.winfo_screenwidth() // 2) - (width // 2)
        y = (self.top_level.winfo_screenheight() // 2) - (height // 2)
        self.top_level.geometry(f'{width}x{height}+{x}+{y}')
    
    def sync_ui_with_timer(self):
        """Sync the UI with the current timer state"""
        timer = Timer()
        
        if timer.is_running() or timer.is_completed():
            # Timer is active, update the input fields with current duration
            remaining = timer.get_remaining_time()
            logger.info(f"Remaining time: {remaining}")
            
            # For completed timers, we'll show 0:00:00 since they're done
            if timer.is_completed():
                remaining = 0
            
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            
            self.hours_var.set(str(hours))
            self.minutes_var.set(str(minutes))
            self.seconds_var.set(str(seconds))
            
            # Update button states
            self.update_button_states()
            
            # Update progress and status
            if timer.is_running():
                self.status_label.config(text="Running...")
            elif timer.is_completed():
                self.status_label.config(text="Timer Complete!")
            elif timer.is_paused():
                self.status_label.config(text="Paused")
    
    def create_timer_input_section(self):
        """Create the timer input section"""
        input_frame = LabelFrame(self.main_frame, text="Set Timer", padding="10")
        input_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        input_frame.grid_columnconfigure(1, weight=1)
        
        # Hours
        TtkLabel(input_frame, text="Hours:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.hours_var = StringVar(value="0")
        self.hours_entry = TtkEntry(input_frame, textvariable=self.hours_var, width=10)
        self.hours_entry.grid(row=0, column=1, sticky="w", padx=(0, 10))
        
        # Minutes
        TtkLabel(input_frame, text="Minutes:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.minutes_var = StringVar(value="0")
        self.minutes_entry = TtkEntry(input_frame, textvariable=self.minutes_var, width=10)
        self.minutes_entry.grid(row=0, column=3, sticky="w", padx=(0, 10))
        
        # Seconds
        TtkLabel(input_frame, text="Seconds:").grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.seconds_var = StringVar(value="0")
        self.seconds_entry = TtkEntry(input_frame, textvariable=self.seconds_var, width=10)
        self.seconds_entry.grid(row=0, column=5, sticky="w")
        
        # Quick preset buttons
        preset_frame = TtkFrame(input_frame)
        preset_frame.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(10, 0))
        
        presets = [("5m", 300), ("10m", 600), ("15m", 900), ("30m", 1800), ("1h", 3600)]
        for i, (label, seconds) in enumerate(presets):
            btn = TtkButton(preset_frame, text=label, 
                           command=lambda s=seconds: self.set_preset_time(s))
            btn.grid(row=0, column=i, padx=2)
    
    def create_timer_display_section(self):
        """Create the timer display section"""
        display_frame = LabelFrame(self.main_frame, text="Timer Display", padding="10")
        display_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        display_frame.grid_columnconfigure(0, weight=1)
        display_frame.grid_rowconfigure(0, weight=1)
        
        # Time display
        self.time_display = TtkLabel(display_frame, text="00:00:00", 
                                     font=("Arial", 24, "bold"))
        self.time_display.grid(row=0, column=0, pady=20)
        
        # Progress bar
        self.progress_bar = Progressbar(display_frame, mode='determinate', length=300)
        self.progress_bar.grid(row=1, column=0, pady=(0, 10))
        
        # Status label
        self.status_label = TtkLabel(display_frame, text="Ready", font=("Arial", 12))
        self.status_label.grid(row=2, column=0)
    
    def create_control_buttons_section(self):
        """Create the control buttons section"""
        button_frame = TtkFrame(self.main_frame)
        button_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        button_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # Start button
        self.start_button = TtkButton(button_frame, text="Start", 
                                     command=self.start_timer)
        self.start_button.grid(row=0, column=0, padx=2)
        
        # Pause/Resume button
        self.pause_button = TtkButton(button_frame, text="Pause", 
                                     command=self.pause_resume_timer, state="disabled")
        self.pause_button.grid(row=0, column=1, padx=2)
        
        # Stop button
        self.stop_button = TtkButton(button_frame, text="Stop", 
                                    command=self.stop_timer, state="disabled")
        self.stop_button.grid(row=0, column=2, padx=2)
        
        # Reset button
        self.reset_button = TtkButton(button_frame, text="Reset", 
                                     command=self.reset_timer)
        self.reset_button.grid(row=0, column=3, padx=2)
    
    def set_preset_time(self, seconds):
        """Set timer to a preset time"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        self.hours_var.set(str(hours))
        self.minutes_var.set(str(minutes))
        self.seconds_var.set(str(secs))
    
    def start_timer(self):
        """Start the timer"""
        try:
            hours = int(self.hours_var.get() or "0")
            minutes = int(self.minutes_var.get() or "0")
            seconds = int(self.seconds_var.get() or "0")
            
            total_seconds = hours * 3600 + minutes * 60 + seconds
            
            if total_seconds <= 0:
                messagebox.showwarning("Invalid Time", "Please enter a valid time greater than 0.")
                return
            
            Timer().start_timer(total_seconds)
            self.update_button_states()
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers for hours, minutes, and seconds.")
    
    def pause_resume_timer(self):
        """Pause or resume the timer"""
        if Timer().is_paused():
            Timer().resume_timer()
            self.pause_button.config(text="Pause")
        else:
            Timer().pause_timer()
            self.pause_button.config(text="Resume")
        
        self.update_button_states()
    
    def stop_timer(self):
        """Stop the timer"""
        Timer().stop_timer()
        self.update_button_states()
    
    def reset_timer(self):
        """Reset the timer display"""
        self.hours_var.set("0")
        self.minutes_var.set("0")
        self.seconds_var.set("0")
        self.progress_bar['value'] = 0
        self.status_label.config(text="Ready")
    
    def update_button_states(self):
        """Update button states based on timer status"""
        is_running = Timer().is_running()
        is_paused = Timer().is_paused()
        
        if is_running:
            self.start_button.config(state="disabled")
            self.pause_button.config(state="normal")
            self.stop_button.config(state="normal")
            self.reset_button.config(state="disabled")
        else:
            self.start_button.config(state="normal")
            self.pause_button.config(state="disabled")
            self.stop_button.config(state="disabled")
            self.reset_button.config(state="normal")
    
    def update_display(self):
        """Update the timer display"""
        while not self._stop_update:
            try:
                if Timer().is_running() or Timer().is_completed():
                    remaining = Timer().get_remaining_time()
                    progress = Timer().get_progress()
                    status = Timer().get_status()
                    
                    # Update time display
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60
                    seconds = remaining % 60
                    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    
                    # Update UI elements (must be done in main thread)
                    self.top_level.after(0, self.update_ui_elements, time_str, progress, status)
                
                time.sleep(0.1)  # Update 10 times per second
                
            except Exception as e:
                logger.error(f"Error updating timer display: {e}")
                time.sleep(1)
        
        logger.info("Timer display update thread stopped")
    
    def update_ui_elements(self, time_str, progress, status):
        """Update UI elements (called from main thread)"""
        try:
            self.time_display.config(text=time_str)
            self.progress_bar['value'] = progress * 100
            
            # Update status and button states
            if status == "completed":
                self.status_label.config(text="Timer Complete!")
                self.update_button_states()
            elif status == "paused":
                self.status_label.config(text="Paused")
            elif status == "running":
                self.status_label.config(text="Running...")
            else:
                self.status_label.config(text="Ready")
                
        except Exception as e:
            print(f"Error updating UI elements: {e}")
    
    def on_closing(self):
        """Handle window closing"""
        try:
            # Stop the UI update thread (but not the timer)
            if hasattr(self, 'update_thread') and self.update_thread.is_alive():
                # Set a flag to stop the update loop
                self._stop_update = True
                # Wait for the thread to finish (with timeout)
                self.update_thread.join(timeout=1.0)
                if self.update_thread.is_alive():
                    logger.warning("Update thread did not stop gracefully")
            
            # Destroy the window
            self.top_level.destroy()
            
        except Exception as e:
            logger.error(f"Error closing timer window: {e}")
            self.top_level.destroy()
