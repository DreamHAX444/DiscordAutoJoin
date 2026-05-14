"""
Browser lifecycle management: Chrome process cleanup, lock removal,
priority adjustment, and HWND discovery.

All Chrome process operations use psutil (no PowerShell/WMIC).
"""

import os
import ctypes
import time
import asyncio
import shutil
import logging
import psutil

from .config import CHROME_PROFILE_DIR
from .logging_setup import log

logger = logging.getLogger("DiscordAutoJoin")


# ── Chrome Process Utilities ──────────────────────────────────────────────────

def _get_chrome_procs(profile_name=None):
    """Yield psutil.Process objects for all running Chrome instances.

    Args:
        profile_name: If provided, only yield processes whose command line
                      contains this string (used to filter by profile dir).

    Yields:
        psutil.Process: Matching Chrome process objects.
    """
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
            try:
                if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                    if profile_name:
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if profile_name not in cmdline:
                            continue
                    yield proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.debug(f"_get_chrome_procs enumeration error: {e}")


async def kill_stale_chrome():
    """Terminate all Chrome processes tied to this app's profile directory.

    Uses psutil instead of PowerShell/WMIC for cross-compatibility.
    Waits up to 5 seconds for processes to actually exit (async-friendly).
    Logs PIDs of killed processes for debugging.
    """
    prof_name = os.path.basename(CHROME_PROFILE_DIR)
    killed_pids = []
    start_time = time.monotonic()

    for proc in _get_chrome_procs(profile_name=prof_name):
        try:
            pid = proc.info['pid']
            proc.kill()
            killed_pids.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.debug(f"kill_stale_chrome: cannot kill PID {proc.info['pid']}: {e}")

    if killed_pids:
        log.info(f"Terminated {len(killed_pids)} stale Chrome process(es): PIDs={killed_pids}",
                 category="SYS", silent=True)

    # Wait for processes to actually terminate (async-friendly polling)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        still_alive = [pid for pid in killed_pids if psutil.pid_exists(pid)]
        if not still_alive:
            break
        await asyncio.sleep(0.5)

    elapsed = time.monotonic() - start_time
    logger.debug(f"kill_stale_chrome completed in {elapsed:.2f}s")


def remove_chrome_locks():
    """Remove Chrome singleton lock files and Crashpad metadata from the profile directory.

    These files can prevent Chrome from launching if a previous instance
    crashed or was force-killed. Safe to call before every launch.
    """
    locks = ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile", ".parentlock"]
    removed = []
    for fname in locks:
        path = os.path.join(CHROME_PROFILE_DIR, fname)
        try:
            if os.path.exists(path):
                os.remove(path)
                removed.append(fname)
        except Exception as e:
            logger.debug(f"remove_chrome_locks: cannot remove {fname}: {e}")

    crashpad_dir = os.path.join(CHROME_PROFILE_DIR, "Crashpad")
    try:
        if os.path.exists(crashpad_dir):
            shutil.rmtree(crashpad_dir, ignore_errors=True)
            removed.append("Crashpad/")
    except Exception as e:
        logger.debug(f"remove_chrome_locks: cannot remove Crashpad/: {e}")

    if removed:
        logger.debug(f"Removed Chrome lock artifacts: {removed}")


def lower_chrome_priority():
    """Set all Chrome processes to below-normal priority using psutil.

    Returns a dict with statistics for logging:
        {'count': N, 'total_memory_mb': M, 'pids': [...]}

    Replaces the deprecated 'wmic' approach from Phase 1.
    """
    count = 0
    total_memory_mb = 0.0
    pids = []
    start_time = time.monotonic()

    for proc in _get_chrome_procs():
        try:
            pid = proc.info['pid']
            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            count += 1
            pids.append(pid)
            if proc.info['memory_info']:
                total_memory_mb += proc.info['memory_info'].rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.debug(f"lower_chrome_priority: cannot adjust PID {proc.info['pid']}: {e}")

    elapsed = time.monotonic() - start_time
    if count > 0:
        log.info(f"Chrome priority lowered: {count} proc(s) | Memory: {total_memory_mb:.1f} MB | "
                 f"PIDs={pids} | took {elapsed:.2f}s",
                 category="SYS", silent=True)

    return {'count': count, 'total_memory_mb': total_memory_mb, 'pids': pids, 'elapsed': elapsed}


# ── Window Handle Discovery ───────────────────────────────────────────────────

def find_chrome_hwnd(state):
    """Locate the Chrome window HWND by enumerating visible windows.

    Searches for a visible window whose title contains 'discord'
    and stores the first match in state.browser_hwnd.

    Args:
        state: AppState instance (browser_hwnd will be set on it).
    """
    hwnds = []
    buf = ctypes.create_unicode_buffer(260)

    def cb(hwnd, _):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if 0 < n < 260:
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 260)
                if "discord" in buf.value.lower():
                    hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(cb), 0)
    if hwnds:
        state.browser_hwnd = hwnds[0]