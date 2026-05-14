"""
Instance locking — ensures only one copy of DiscordAutoJoin runs at a time.

Uses a PID-based lock file in %APPDATA%/DiscordAutoJoin/app.lock.
Stale locks (PID no longer alive) are automatically detected and overwritten.

Cross-platform PID checking: uses psutil.pid_exists() on all platforms
(falls back to OS-specific methods if psutil is unavailable).
"""

from __future__ import annotations

import os
import sys
from .config import LOCK_FILE
from .logging_setup import logger, log


def _pid_exists(pid: int) -> bool:
    """Check whether a process with the given PID is currently running.

    Uses psutil.pid_exists() for cross-platform reliability. On Windows,
    os.kill(pid, 0) is not available — this function provides a safe
    alternative.

    Args:
        pid: Process ID to check.

    Returns:
        bool: True if the process exists, False otherwise.
    """
    try:
        import psutil

        return bool(psutil.pid_exists(pid))
    except ImportError:
        # Fallback for environments without psutil
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False


def acquire_lock() -> None:
    """Ensure only one instance of the app runs at a time.

    Creates a lock file containing the current PID. If a lock file
    already exists and its PID is still alive, exits immediately.
    Stale lock files (PID no longer exists) are overwritten.

    Raises:
        SystemExit(1): If another instance is already running.
    """
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if _pid_exists(pid):
                log.error(
                    f"Another instance is already running (PID {pid}). Exiting.",
                    category="SYS",
                )
                sys.exit(1)
            else:
                logger.debug(
                    "Stale lock file detected (PID %d not alive), overwriting.", pid
                )
        except (ValueError, OSError):
            # Lock file is corrupt or unreadable — overwrite it
            logger.debug("Corrupt lock file detected, overwriting.")
    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def release_lock() -> None:
    """Remove the lock file. Safe to call even if the file doesn't exist."""
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except Exception as e:
            logger.debug(f"Failed to remove lock file: {e}")
