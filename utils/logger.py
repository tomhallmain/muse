import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from utils.custom_formatter import CustomFormatter

def setup_logger():
    # create logger
    logger = logging.getLogger("muse")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(CustomFormatter())
    logger.addHandler(ch)

    # Create log file in ApplicationData
    appdata_dir = os.getenv('APPDATA') if sys.platform == 'win32' else os.path.expanduser('~/.local/share')
    log_dir = Path(appdata_dir) / 'muse' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f'muse_{date_str}.log'

    # Add file handler
    fh = logging.FileHandler(log_file, mode='w+', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(CustomFormatter())
    logger.addHandler(fh)

    return logger, log_file

# Initialize logger and log_file as module-level variables
logger, log_file = setup_logger() 