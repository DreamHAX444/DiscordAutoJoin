"""
Logging infrastructure for DiscordAutoJoin.

Provides:
- A module-level 'logger' instance with rotating file handler (5 MB, 3 backups)
- CategoryFilter that injects a default 'category' attribute into log records
- Console class: unified console + file logger with category tagging and silent mode
- DEBUG_MODE flag (set via --debug CLI argument)
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from .config import LOG_FILE

# ── Core Logger ───────────────────────────────────────────────────────────────
logger: logging.Logger = logging.getLogger("DiscordAutoJoin")
logger.setLevel(logging.DEBUG)


class CategoryFilter(logging.Filter):
    """Inject a default 'category' attribute into every log record if missing."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "category"):
            record.category = "SYS"
        return True


logger.addFilter(CategoryFilter())

_fmt = logging.Formatter(
    "[%(asctime)s] %(levelname)-8s [%(category)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_fh: RotatingFileHandler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)

# Debug mode flag — set via --debug CLI argument
DEBUG_MODE: bool = False


# ── Console Logger ────────────────────────────────────────────────────────────
class Console:
    """Unified console + file logger with category tagging and silent mode.

    All messages are written to the rotating file log. Console output
    is suppressed when silent=True (used for high-frequency health checks).
    In debug mode (--debug), silent is ignored and all messages print.
    """

    @staticmethod
    def _log(level: str, category: str, msg: str, silent: bool = False) -> None:
        if not silent or DEBUG_MODE:
            print(f"[{category}] {level}: {msg}", flush=True)
        extra = {"category": category}
        if level == "INFO":
            logger.info(msg, extra=extra)
        elif level == "WARN":
            logger.warning(msg, extra=extra)
        elif level == "ERROR":
            logger.error(msg, extra=extra)
        elif level == "OK":
            logger.info(msg, extra=extra)

    @staticmethod
    def info(msg: str, silent: bool = False, category: str = "SYS") -> None:
        Console._log("INFO", category, msg, silent)

    @staticmethod
    def ok(msg: str, silent: bool = False, category: str = "SYS") -> None:
        Console._log("OK", category, msg, silent)

    @staticmethod
    def warn(msg: str, silent: bool = False, category: str = "SYS") -> None:
        Console._log("WARN", category, msg, silent)

    @staticmethod
    def error(msg: str, silent: bool = False, category: str = "SYS") -> None:
        Console._log("ERROR", category, msg, silent)


# Convenience alias used throughout the codebase
log: type[Console] = Console
