import os
from pathlib import Path
import random
import re
import shutil
import subprocess
from typing import Optional, Tuple, Dict
import unicodedata

from utils.temp_dir import TempDir
from utils.utils import Utils

class FFmpegHandler:
    """Handler for all FFmpeg operations with filename sanitization."""
    
    # Cache of sanitized filenames to their original paths
    _filename_cache: Dict[str, str] = {}
    ffprobe_available = Utils.executable_available("ffprobe")
    ffmpeg_available = Utils.executable_available("ffmpeg")
    # Maximum size for file copying (100MB)
    MAX_COPY_SIZE = 100 * 1024 * 1024

    @staticmethod
    def cleanup_cache():
        """Remove all temporary files/symlinks and clear the filename cache."""
        for original, sanitized in FFmpegHandler._filename_cache.items():
            try:
                if os.path.exists(sanitized):
                    os.remove(sanitized)
            except Exception as e:
                Utils.log(f"Error cleaning up temporary file {sanitized}: {str(e)}")
        FFmpegHandler._filename_cache.clear()

    @staticmethod
    def sanitize_filename(filepath: str) -> str:
        """
        Convert filepath to a safe version that works with ffmpeg.
        First tries symlinks, then falls back to copying if the file is small enough.
        For large files, attempts to use the original path with basic sanitization.
        
        Args:
            filepath: Path to the file to sanitize
            
        Returns:
            Sanitized path that can be used with ffmpeg
            
        Raises:
            Exception: If the filepath contains emoji or other problematic characters
        """
        if not FFmpegHandler.ffmpeg_available:
            raise Exception("ffmpeg is not available.")

        # Check for emoji in the filepath
        if Utils.contains_emoji(filepath):
            raise Exception(f"Filepath contains emoji characters which are not supported: {filepath}")

        if filepath in FFmpegHandler._filename_cache:
            return FFmpegHandler._filename_cache[filepath]

        # Convert to Path object for better path handling
        path = Path(filepath)
        # Sanitize the filename
        filename = path.name
        # Remove diacritics and normalize
        filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode('ASCII')
        # Replace problematic characters
        filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        
        # Create sanitized path in TempDir
        temp_dir = TempDir.get()
        sanitized_path = temp_dir.get_filepath(filename)
        
        # If file exists with different case, use a numbered variant
        counter = 1
        while os.path.exists(sanitized_path):
            base, ext = os.path.splitext(filename)
            sanitized_path = temp_dir.get_filepath(f"{base}_{counter}{ext}")
            counter += 1

        # Try to create symlink first (works on Unix, might work on Windows with right permissions)
        try:
            if os.path.exists(sanitized_path):
                os.remove(sanitized_path)
            os.symlink(filepath, sanitized_path)
            FFmpegHandler._filename_cache[filepath] = sanitized_path
            return sanitized_path
        except Exception as e:
            if os.name != 'nt':
                # Symlink creation often fails on Windows
                Utils.log_yellow(f"Symlink creation failed for {filepath}, trying fallback methods")

        # If symlink fails, check file size before attempting to copy
        try:
            file_size = os.path.getsize(filepath)
            if file_size > FFmpegHandler.MAX_COPY_SIZE:
                Utils.log_yellow(f"File too large to copy ({file_size / 1024 / 1024:.1f}MB), using original path")
                # # For large files, try to use the original path if it's already safe
                # if all(c.isascii() and (c.isalnum() or c in '._-/\\') for c in str(path)):
                #     return str(path)
                # # If original path isn't safe, try to use a sanitized version in the same directory
                # safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', path.name)
                # safe_path = path.parent / safe_name
                # if not os.path.exists(safe_path):
                #     shutil.move(filepath, safe_path)
                #     return str(safe_path)
                # Utils.log_yellow(f"Could not create safe path for large file, attempting to use original path")
                return filepath
            
            # For small files, create a copy - these should be removed upon program exit
            shutil.copy2(filepath, sanitized_path)
            FFmpegHandler._filename_cache[filepath] = sanitized_path
            return sanitized_path
            
        except Exception as e:
            Utils.log(f"Error handling file {filepath}: {str(e)}")
            # If all else fails, return original path as fallback
            return filepath

    @staticmethod
    def get_volume(filepath: str) -> Tuple[float, float]:
        """Get mean and max volume for a media file."""
        sanitized_path = FFmpegHandler.sanitize_filename(filepath)
        args = ["ffmpeg", "-i", sanitized_path, "-af", "volumedetect", "-f", "null", "/dev/null"]
        mean_volume = -9999.0
        max_volume = -9999.0
        mean_volume_tag = "] mean_volume: "
        max_volume_tag = "] max_volume: "
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output, _ = process.communicate()
            output_str = output.decode("utf-8", errors="ignore")
            for line in output_str.split("\n"):
                if mean_volume_tag in line:
                    mean_volume = float(line[line.index(mean_volume_tag)+len(mean_volume_tag):-3].strip())
                if max_volume_tag in line:
                    max_volume = float(line[line.index(max_volume_tag)+len(max_volume_tag):-3].strip())
        except Exception as e:
            Utils.log_yellow(f"Error getting volume for {filepath}: {str(e)}")
        return mean_volume, max_volume

    @staticmethod
    def split_media(
        input_path: str,
        output_path: str,
        start_time: float,
        duration: float,
        copy_codec: bool = True
    ) -> bool:
        """Split media file into segments."""
        sanitized_input = FFmpegHandler.sanitize_filename(input_path)
        sanitized_output = FFmpegHandler.sanitize_filename(output_path)
        
        codec_args = ["-c", "copy"] if copy_codec else []
        args = [
            "ffmpeg",
            "-i", sanitized_input,
            "-ss", str(start_time),
            "-t", str(duration),
            *codec_args,
            "-y",  # Overwrite output file if it exists
            sanitized_output
        ]
        
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output, _ = process.communicate()
            return process.returncode == 0
        except Exception as e:
            Utils.log(f"Error splitting media {input_path}: {str(e)}")
            return False

    @staticmethod
    def get_duration(filepath: str) -> Optional[float]:
        """
        Get duration of media file in seconds, prioritizing ffprobe if available.
        Falls back to ffmpeg if ffprobe is not available.
        """
        sanitized_path = FFmpegHandler.sanitize_filename(filepath)
        
        # Check if ffprobe is available
        if FFmpegHandler.ffprobe_available:
            args = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", sanitized_path]
            try:
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                output, _ = process.communicate()
                for line in output.split("\n"):
                    try:
                        return float(line[:-1])  # Match original behavior of trimming last char
                    except Exception as e:
                        Utils.log(f"Error parsing ffprobe duration output: {str(e)}")
            except Exception as e:
                Utils.log(f"Error running ffprobe: {str(e)}")
        
        # Fallback to ffmpeg if ffprobe fails or is not available
        args = ["ffmpeg", "-i", sanitized_path]
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            for line in stderr.split("\n"):
                if "Duration: " in line and ", start:" in line:
                    duration_value = line[line.find("Duration: ") + len("Duration: "):line.find(", start:")]
                    sexagesimal_time_vals = duration_value.split(":")
                    duration_seconds = (
                        int(sexagesimal_time_vals[0]) * 3600 + 
                        int(sexagesimal_time_vals[1]) * 60 + 
                        float(sexagesimal_time_vals[2])
                    )
                    return duration_seconds
        except Exception as e:
            Utils.log(f"Error getting duration with ffmpeg: {str(e)}")
            
        Utils.log_red(f"Failed to get track length: {filepath}")
        return None

    @staticmethod
    def detect_silence_times(
        filepath: str,
        noise_threshold: float = 0.001,
        duration: float = 2
    ) -> list[list[float]]:
        """
        Detect periods of silence in an audio file.
        
        Args:
            filepath: Path to the audio file
            noise_threshold: Threshold below which audio is considered silence (default: 0.001)
            duration: Minimum duration of silence to detect (default: 2 seconds)
            
        Returns:
            List of [start_time, end_time, duration] lists for each silence period
        """
        sanitized_path = FFmpegHandler.sanitize_filename(filepath)
        silence_times = []
        args = ["ffmpeg", "-i", sanitized_path, "-af", f"silencedetect=n={noise_threshold}:d={duration}", "-f", "null", "/dev/null"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output, _ = process.communicate()
        silence_interval = [0.0]
        for line in output.split("\n"):
            if "silencedetect @" in line and "] " in line:
                if len(silence_interval) == 0 or (len(silence_interval) == 1 and silence_interval[0] == 0.0):
                    if "silence_start: " in line:
                        _, text = line.split("] ")
                        value = float(re.sub(r"[^0-9\.\-]+", "", text[len("silence_start: "):]))
                        if len(silence_interval) == 0 or value > 0.5:
                            silence_interval.append(value)
                            if len(silence_interval) == 2:
                                # Grab the part from the start of track to the first detected
                                # the duration of the first part should be equal to the first detected silence.
                                silence_interval.append(silence_interval[1])
                                silence_times.append(list(silence_interval))
                                silence_interval.clear()
                                # set up the next interval
                                silence_interval.append(value)
                elif "silence_end: " in line:
                    _, text = line.split("] ")
                    if " | " in line:
                        end_text, duration_text = text.split(" | ")
                    else:
                        end_text = text
                        duration_text = ""
                    end_value = re.sub(r"[^0-9\.\-]+", "", end_text[len("silence_end: "):])
                    silence_interval.append(float(end_value))
                    if duration_text != "":
                        duration_value = re.sub(r"[^0-9\.\-]+", "", duration_text[len("silence_duration: "):])
                        silence_interval.append(float(duration_value))
                    silence_times.append(list(silence_interval))
                    silence_interval.clear()
        return silence_times 

    @staticmethod
    def get_track_part_path(
        filepath: str,
        title: str,
        ext: str,
        start: float,
        end: float,
        idx: int = -1,
        total: int = -1
    ) -> str:
        """
        Create a track part from a media file using specified time boundaries.
        
        Args:
            filepath: Path to the input media file
            title: Base title for the output file
            ext: File extension for output file
            start: Start time in seconds
            end: End time in seconds
            idx: Part index (optional)
            total: Total number of parts (optional)
            temp_dir: Directory to store the output file (uses TempDir if None)
            
        Returns:
            Path to the created track part
        
        Raises:
            Exception: If start/end times are invalid
        """
        if start == -1 or end == -1 or start > end:
            raise Exception(f"Invalid start and end values provided for get_track_part_path: {start}, {end}")
        # Create output filename
        if idx == -1 or total == -1:
            temp_basename = f"{title} part{ext}"
        else:
            temp_basename = f"{title} ({idx}-{total}){ext}"
        temp_filepath = TempDir.get().get_filepath(temp_basename)
        # Convert times to sexagesimal format (HH:MM:SS.xxx)
        start_time = Utils.get_sexagesimal_time_str(start)
        end_time = Utils.get_sexagesimal_time_str(end)
        Utils.log(f"Creating track part {idx} out of {total} with anchors start={start}, end={end}")
        sanitized_input = FFmpegHandler.sanitize_filename(filepath)
        sanitized_output = FFmpegHandler.sanitize_filename(temp_filepath)
        
        args = [
            "ffmpeg",
            "-i", sanitized_input,
            "-ss", start_time,
            "-to", end_time,
            "-c:a", "copy",  # Copy audio codec to avoid re-encoding
            sanitized_output
        ]
        
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output, _ = process.communicate()
            if process.returncode == 0:
                return temp_filepath
            else:
                raise Exception(f"FFmpeg failed with return code {process.returncode}")
        except Exception as e:
            Utils.log(f"Error creating track part from {filepath}: {str(e)}")
            raise e

    @staticmethod
    def extract_non_silent_track_parts(
        filepath: str,
        title: str,
        ext: str,
        select_random_track_part: bool = True,
        noise_threshold: float = 0.001,
        duration: float = 2
    ) -> list[str]:
        """
        Extract non-silent parts of a track as separate files.
        
        Args:
            filepath: Path to the input audio file
            title: Base title for the output files
            ext: File extension for output files
            select_random_track_part: If True, only extract a random part
            noise_threshold: Threshold for silence detection
            duration: Minimum silence duration
            
        Returns:
            List of paths to the extracted track parts
        """
        silence_times = FFmpegHandler.detect_silence_times(filepath, noise_threshold, duration)
        if not silence_times:
            Utils.log_yellow("No silence detected, returning None")
            return []
        Utils.log(f"Silence times: {silence_times}")
        track_paths = []
        if select_random_track_part:
            idx = random.randint(1, len(silence_times))
            track_anchors = silence_times[idx-1]
            track_path = FFmpegHandler.get_track_part_path(
                filepath=filepath,
                title=title,
                ext=ext,
                start=track_anchors[0],
                end=track_anchors[1],
                idx=idx,
                total=len(silence_times)
            )
            track_paths.append(track_path)
        else:
            for idx, track_anchors in enumerate(silence_times, 1):
                track_path = FFmpegHandler.get_track_part_path(
                    filepath=filepath,
                    title=title,
                    ext=ext,
                    start=track_anchors[0],
                    end=track_anchors[1],
                    idx=idx,
                    total=len(silence_times)
                )
                track_paths.append(track_path)
        return track_paths