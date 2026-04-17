"""
Logger module — provides rotating file + colored console logging.
Usage:
    from src.common.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Scraping started")
"""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# src/common/logger.py -> src/common -> src/ -> project_root/ -> project_root/logs
LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Custom colored formatter for console
# ---------------------------------------------------------------------------
class _ColoredFormatter(logging.Formatter):
    """Adds color to log level names for console output."""

    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN if HAS_COLORAMA else "",
        logging.INFO: Fore.GREEN if HAS_COLORAMA else "",
        logging.WARNING: Fore.YELLOW if HAS_COLORAMA else "",
        logging.ERROR: Fore.RED if HAS_COLORAMA else "",
        logging.CRITICAL: Fore.RED + Style.BRIGHT if HAS_COLORAMA else "",
    }
    RESET = Style.RESET_ALL if HAS_COLORAMA else ""

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------
_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str = "job_scraper") -> logging.Logger:
    """
    Get or create a logger with both file and console handlers.

    File:    logs/scraper_YYYY-MM-DD.log  (5 MB max, 5 backups)
    Console: colored output (INFO level)
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers on re-import
    if logger.handlers:
        _LOGGERS[name] = logger
        return logger

    # --- File handler (DEBUG level — captures everything) ---
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"scraper_{today}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    # --- Console handler (INFO level — clean output) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    if HAS_COLORAMA:
        console_fmt = _ColoredFormatter(
            "%(asctime)s | %(levelname)-18s | %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        console_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        )
    console_handler.setFormatter(console_fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _LOGGERS[name] = logger
    return logger
