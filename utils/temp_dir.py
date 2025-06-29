import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta

from utils.logging_setup import get_logger

# Get logger for this module
logger = get_logger(__name__)

class TempDir:
    prefix = "tmp_muse_"
    temporary_directory_parent = tempfile.gettempdir()
    open_directories = {}
    # Dictionary to track creation times of files
    file_timestamps = {}
    # Maximum age for temp files (4 hours by default)
    MAX_FILE_AGE_HOURS = 6
    # How often to check for old files (every 24 hours)
    CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
    # Last cleanup timestamp initialized to current time
    last_cleanup_time = time.time()

    @staticmethod
    def get(prefix=prefix):
        current_time = time.time()
        
        # Check if we should run cleanup of old files
        if current_time - TempDir.last_cleanup_time > TempDir.CLEANUP_INTERVAL_SECONDS:
            TempDir.cleanup_old_files()
            TempDir.last_cleanup_time = current_time

        if prefix not in TempDir.open_directories:
            temp_dir = TempDir(prefix)
            TempDir.open_directories[prefix] = temp_dir
        return TempDir.open_directories[prefix]

    @staticmethod
    def cleanup():
        """Clean up all temporary directories and tracked files."""
        # First remove all tracked files
        for filepath in list(TempDir.file_timestamps.keys()):
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {filepath} - {str(e)}")
        TempDir.file_timestamps.clear()

        # Then remove directories
        for prefix, directory in TempDir.open_directories.items():
            try:
                if os.path.exists(directory._temp_directory):
                    shutil.rmtree(directory._temp_directory)
            except Exception as e:
                logger.error("Failed to delete temp dir: " + directory._temp_directory)
        TempDir.open_directories.clear()

    @staticmethod
    def cleanup_old_files():
        """Clean up temporary files that are older than MAX_FILE_AGE_HOURS."""
        current_time = time.time()
        max_age_seconds = TempDir.MAX_FILE_AGE_HOURS * 3600
        
        # Clean up tracked files
        files_to_remove = []
        for filepath, create_time in TempDir.file_timestamps.items():
            if current_time - create_time > max_age_seconds:
                try:
                    if os.path.exists(filepath):
                        file_age_hours = (current_time - create_time) / 3600
                        logger.info(f"Removing old temp file: {os.path.basename(filepath)} (age: {file_age_hours:.1f} hours)")
                        os.remove(filepath)
                except Exception as e:
                    logger.warning(f"Error removing old file {filepath}: {str(e)}")
                files_to_remove.append(filepath)

        # Clean up tracking dictionary
        for filepath in files_to_remove:
            TempDir.file_timestamps.pop(filepath, None)

        # Also look for any untracked files in temp directories
        if os.path.exists(TempDir.temporary_directory_parent):
            for dirname in os.listdir(TempDir.temporary_directory_parent):
                if dirname.startswith(TempDir.prefix):
                    dirpath = os.path.join(TempDir.temporary_directory_parent, dirname)
                    if os.path.isfile(dirpath):  # Only handle files
                        try:
                            file_create_time = os.path.getctime(dirpath)
                            if current_time - file_create_time > max_age_seconds:
                                logger.info(f"Removing untracked temp file: {dirname}")
                                os.remove(dirpath)
                        except Exception as e:
                            logger.warning(f"Error checking/removing untracked file {dirname}: {str(e)}")

    def __init__(self, prefix=prefix):
        self._prefix = prefix
        self.purge_prefix()
        self._temp_directory = os.path.join(TempDir.temporary_directory_parent, prefix + str(os.urandom(24).hex()))
        os.makedirs(self._temp_directory, exist_ok=True)

    def purge_prefix(self):
        """Eagerly purge any existing files with this prefix."""
        for _dir in os.listdir(TempDir.temporary_directory_parent):
            if _dir.startswith(self._prefix):
                path = os.path.join(TempDir.temporary_directory_parent, _dir)
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                    else:
                        shutil.rmtree(path)
                    logger.info("Purging stale temp item: " + _dir)
                except Exception as e:
                    logger.warning(f"Error purging stale temp item {_dir}: {str(e)}")

    def get_filepath(self, filename=None):
        if filename is None or filename.strip() == "":
            return self._temp_directory
        filepath = os.path.join(self._temp_directory, filename)
        # Track the file when a new path is generated
        TempDir.file_timestamps[filepath] = time.time()
        return filepath

    def add_file(self, filename, file_content="", write_flags="w"):
        temp_file_path = os.path.join(TempDir.temporary_directory_parent, filename)
        with open(temp_file_path, write_flags) as f:
            f.write(file_content)
        # Track the newly created file
        TempDir.file_timestamps[temp_file_path] = time.time()
        return temp_file_path
