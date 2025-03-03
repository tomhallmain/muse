import os
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Optional, Tuple, Dict
from utils.temp_dir import TempDir
from utils.utils import Utils

class FFmpegHandler:
    """Handler for all FFmpeg operations with filename sanitization."""
    
    # Cache of sanitized filenames to their original paths
    _filename_cache: Dict[str, str] = {}
    
    @staticmethod
    def sanitize_filename(filepath: str) -> str:
        """
        Convert filepath to a safe version that works with ffmpeg.
        Caches the result to maintain mapping of sanitized to original names.
        """
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
        
        # Create sanitized path
        sanitized_path = str(path.parent / filename)
        
        # If file exists with different case, use a numbered variant
        counter = 1
        while os.path.exists(sanitized_path) and os.path.realpath(sanitized_path) != os.path.realpath(filepath):
            base, ext = os.path.splitext(filename)
            sanitized_path = str(path.parent / f"{base}_{counter}{ext}")
            counter += 1
            
        # Create symlink if needed
        if sanitized_path != filepath:
            if os.path.exists(sanitized_path):
                os.remove(sanitized_path)
            os.symlink(filepath, sanitized_path)
            
        FFmpegHandler._filename_cache[filepath] = sanitized_path
        return sanitized_path

    @staticmethod
    def get_volume(filepath: str) -> Tuple[float, float]:
        """Get mean and max volume for a media file."""
        sanitized_path = FFmpegHandler.sanitize_filename(filepath)
        args = ["ffmpeg", "-i", sanitized_path, "-af", "volumedetect", "-f", "null", "/dev/null"]
        
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output, _ = process.communicate()
            output_str = output.decode("utf-8", errors="ignore")
            
            mean_volume = -9999.0
            max_volume = -9999.0
            
            mean_volume_tag = "] mean_volume: "
            max_volume_tag = "] max_volume: "
            
            for line in output_str.split("\n"):
                if mean_volume_tag in line:
                    mean_volume = float(line[line.index(mean_volume_tag)+len(mean_volume_tag):-3].strip())
                if max_volume_tag in line:
                    max_volume = float(line[line.index(max_volume_tag)+len(max_volume_tag):-3].strip())
                    
            return mean_volume, max_volume
            
        except Exception as e:
            Utils.log(f"Error getting volume for {filepath}: {str(e)}")
            return -9999.0, -9999.0

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
        """Get duration of media file in seconds."""
        sanitized_path = FFmpegHandler.sanitize_filename(filepath)
        args = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            sanitized_path
        ]
        
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output, _ = process.communicate()
            duration_str = output.decode("utf-8", errors="ignore").strip()
            return float(duration_str) if duration_str else None
        except Exception as e:
            Utils.log(f"Error getting duration for {filepath}: {str(e)}")
            return None

    @staticmethod
    def cleanup_cache():
        """Remove all symlinks and clear the filename cache."""
        for original, sanitized in FFmpegHandler._filename_cache.items():
            try:
                if os.path.islink(sanitized):
                    os.remove(sanitized)
            except Exception as e:
                Utils.log(f"Error cleaning up symlink {sanitized}: {str(e)}")
        FFmpegHandler._filename_cache.clear() 