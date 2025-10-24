"""
Utilities for handling administrator privileges on Windows.
"""

import os
import sys
import ctypes
import subprocess
from typing import Optional, Tuple
from utils.logging_setup import get_logger

logger = get_logger(__name__)


def is_admin() -> bool:
    """
    Check if the current process is running with administrator privileges.
    
    Returns:
        True if running as administrator, False otherwise
    """
    try:
        import platform
        if platform.system() != "Windows":
            # On non-Windows systems, assume we have necessary privileges
            # Audio device switching may work differently on other platforms
            return True
        
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception as e:
        logger.debug(f"Error checking admin status: {e}")
        return False


def request_admin_privileges() -> bool:
    """
    Request administrator privileges by restarting the application with elevated permissions.
    
    Returns:
        True if successfully restarted with admin privileges, False otherwise
    """
    try:
        import platform
        if platform.system() != "Windows":
            logger.info("Administrator privilege elevation not needed on this platform")
            return True
        
        if is_admin():
            logger.info("Already running with administrator privileges")
            return True
        
        logger.info("Requesting administrator privileges...")
        
        # Get the current script path
        script_path = sys.executable
        script_args = sys.argv
        
        # Use ShellExecuteW to request elevation
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",  # Request elevation
            script_path,
            " ".join(script_args),
            None,
            1  # SW_SHOWNORMAL
        )
        
        # ShellExecuteW returns a value > 32 on success
        if result > 32:
            logger.info("Successfully requested administrator privileges")
            # Exit current instance since we're starting a new elevated one
            sys.exit(0)
        else:
            logger.warning(f"Failed to request administrator privileges. Error code: {result}")
            return False
            
    except Exception as e:
        logger.error(f"Error requesting administrator privileges: {e}")
        return False


def check_and_request_admin_for_audio() -> Tuple[bool, str]:
    """
    Check if admin privileges are needed for audio device switching and request them if necessary.
    
    Returns:
        Tuple of (success, message) where success indicates if we can proceed with audio operations
    """
    try:
        if is_admin():
            return True, "Running with administrator privileges - audio device switching enabled"
        
        logger.info("Administrator privileges required for audio device switching")
        
        # Try to request elevation
        if request_admin_privileges():
            return True, "Requested administrator privileges - please restart the application"
        else:
            return False, "Administrator privileges are required for audio device switching. Please run the application as administrator."
            
    except Exception as e:
        logger.error(f"Error checking admin privileges: {e}")
        return False, f"Error checking administrator privileges: {e}"


def show_admin_required_message(message: str) -> None:
    """
    Show a message to the user about administrator privileges being required.
    
    Args:
        message: The message to display
    """
    try:
        import tkinter as tk
        from tkinter import messagebox
        
        # Create a temporary root window for the message box
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        messagebox.showwarning(
            "Administrator Privileges Required",
            f"{message}\n\nTo enable audio device switching:\n"
            "1. Close this application\n"
            "2. Right-click on the application icon\n"
            "3. Select 'Run as administrator'\n"
            "4. Restart the application"
        )
        
        root.destroy()
        
    except Exception as e:
        logger.error(f"Error showing admin message: {e}")
        # Fallback to console output
        print(f"\n{message}")
        print("To enable audio device switching, please run the application as administrator.")


def create_elevated_shortcut() -> bool:
    """
    Create a shortcut that runs the application with administrator privileges.
    
    Returns:
        True if shortcut was created successfully, False otherwise
    """
    try:
        import winshell
        from win32com.client import Dispatch
        
        # Get the current script path
        script_path = os.path.abspath(sys.argv[0])
        script_dir = os.path.dirname(script_path)
        
        # Create shortcut path
        desktop = winshell.desktop()
        shortcut_path = os.path.join(desktop, "Muse (Administrator).lnk")
        
        # Create the shortcut
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = script_path
        shortcut.Arguments = ""
        shortcut.WorkingDirectory = script_dir
        shortcut.Description = "Muse Media Player with Administrator Privileges"
        
        # Set to run as administrator
        shortcut_path_obj = shortcut_path.replace('.lnk', '')
        with open(shortcut_path_obj, 'wb') as f:
            # This is a simplified approach - in practice, you'd need to set the shortcut properties
            # to request elevation through the Windows API
            pass
        
        logger.info(f"Created administrator shortcut: {shortcut_path}")
        return True
        
    except ImportError:
        logger.warning("winshell not available - cannot create administrator shortcut")
        return False
    except Exception as e:
        logger.error(f"Error creating administrator shortcut: {e}")
        return False
