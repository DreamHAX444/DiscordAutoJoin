"""
System tray icon, menu, and callbacks.

Provides:
- Tray icon generation (colored circle on black background, cached)
- Dynamic right-click menu with real-time stats dashboard
- Tray action callbacks (pause, reconnect, show/hide browser, restart, exit)
- set_tray() for updating icon color, tooltip, and menu
- update_last_action() for recording state changes
- register_startup() for Windows startup registration
"""

import os
import sys
import ctypes
import time
import winreg
from datetime import datetime, timedelta
from PIL import Image, ImageDraw
import pystray

from .config import CONFIG, LOG_FILE
from .state import state
from .logging_setup import log
from .browser import find_chrome_hwnd

# Module-level icon reference — set by main.py after pystray.Icon is created
icon = None

# ── Icon Generation ───────────────────────────────────────────────────────────
_icon_cache = {}


def _get_icon(color):
    """Generate or retrieve a cached 64x64 tray icon (colored circle on black).

    Args:
        color: PIL-compatible color string (e.g., 'green', '#FF0000').

    Returns:
        PIL.Image: The generated/cached icon image.
    """
    if color not in _icon_cache:
        img = Image.new('RGB', (64, 64), (0, 0, 0))
        ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
        _icon_cache[color] = img
    return _icon_cache[color]


# ── Tray Update Helpers ───────────────────────────────────────────────────────

def update_last_action(action, category="STATE", silent=True):
    """Record the most recent automation action and refresh the tray menu.

    Args:
        action: Human-readable description of the action.
        category: Log category tag (STATE, USR, NET, ERR, SYS).
        silent: If True, suppress console output (still written to file log).
    """
    state.last_action = action
    state.action_timestamp = datetime.now()
    log.info(action, silent=silent, category=category)
    if icon:
        icon.update_menu()


def set_tray(status, color):
    """Update the system tray icon color, tooltip, and menu.

    Args:
        status: Status string shown in tooltip and menu (e.g., 'Connected').
        color: Icon color — 'green', 'yellow', 'blue', 'darkred', 'gray'.
               Overridden to 'gray' if automation is paused.
    """
    state.status = status
    if icon:
        display_color = "gray" if state.paused else color
        display_status = f"Paused ({status})" if state.paused else status
        icon.icon = _get_icon(display_color)
        icon.title = f"Auto-Join: {display_status}"
        icon.update_menu()


# ── Tray Action Callbacks ─────────────────────────────────────────────────────

def _on_login_done(*_):
    """Tray callback: user confirms manual Discord login is complete."""
    update_last_action("Manual Login Confirmed", category="USR")
    state.first_run_done.set()
    set_tray("Connecting...", "yellow")


def _toggle_pause(*_):
    """Tray callback: pause or resume automation."""
    state.paused = not state.paused
    action = "Paused" if state.paused else "Resumed"
    update_last_action(f"Automation {action} by user", category="USR")
    set_tray(state.status, "green" if state.status == "Connected" else "yellow")


def _trigger_reconnect(*_):
    """Tray callback: force a full disconnect/reconnect cycle."""
    update_last_action("Force Reconnect Initiated by user", category="USR")
    state.force_reconnect = True


def _toggle_browser(*_):
    """Tray callback: show or hide the Chrome window via Win32 API."""
    if not state.browser_hwnd:
        find_chrome_hwnd(state)
    if not state.browser_hwnd:
        return
    if state.browser_hidden:
        ctypes.windll.user32.ShowWindow(state.browser_hwnd, 9)   # SW_RESTORE
        state.browser_hidden = False
    else:
        ctypes.windll.user32.ShowWindow(state.browser_hwnd, 6)   # SW_MINIMIZE
        state.browser_hidden = True
    if icon:
        icon.update_menu()


def _restart_app(*_):
    """Tray callback: trigger a clean app restart."""
    log.info("Restarting app via tray...", silent=True, category="USR")
    state.is_restarting = True
    state.should_exit.set()
    if icon:
        icon.stop()


def _exit_app(*_):
    """Tray callback: clean shutdown and exit."""
    log.info("Exiting app via tray...", silent=True, category="USR")
    state.should_exit.set()
    if icon:
        icon.stop()


# ── Menu Generator ────────────────────────────────────────────────────────────

def _menu_generator():
    """Generates the tray menu dynamically upon right-click for real-time stats."""
    uptime = str(timedelta(seconds=int(time.time() - state.start_time)))
    time_since_action = str(timedelta(seconds=int((datetime.now() - state.action_timestamp).total_seconds())))

    # === Dashboard Display (Disabled Items acts as text/labels) ===
    status_icon = "\u23f8\ufe0f" if state.paused else ("\U0001f7e2" if state.status == "Connected" else "\U0001f7e1")
    yield pystray.MenuItem(f"{status_icon} Status: {state.status}", lambda: None, enabled=False)
    yield pystray.MenuItem(f"\u23f1\ufe0f Uptime: {uptime}", lambda: None, enabled=False)
    yield pystray.MenuItem(f"\u26a1 Last: {state.last_action} ({time_since_action} ago)", lambda: None, enabled=False)
    yield pystray.MenuItem(f"\U0001f504 Restarts: {state.restart_count}", lambda: None, enabled=False)

    yield pystray.Menu.SEPARATOR

    # === Configuration Submenu ===
    yield pystray.MenuItem("\u2699\ufe0f View Config", pystray.Menu(
        pystray.MenuItem(f"Target URL: ...{CONFIG['DISCORD_URL'][-20:]}", lambda: None, enabled=False),
        pystray.MenuItem(f"Poll Interval: {CONFIG['POLL_INTERVAL']}s", lambda: None, enabled=False),
        pystray.MenuItem(f"Max Join Retries: {CONFIG['MAX_JOIN_RETRIES']}", lambda: None, enabled=False),
        pystray.MenuItem(f"Max Launch Retries: {CONFIG.get('MAX_LAUNCH_RETRIES', 5)}", lambda: None, enabled=False),
        pystray.MenuItem(f"Health Log Freq: {CONFIG['HEALTH_LOG_EVERY']} polls", lambda: None, enabled=False)
    ))

    yield pystray.Menu.SEPARATOR

    # === Actionable Controls ===
    if state.status == "Waiting for login":
        yield pystray.MenuItem("\u2705 Confirm Login Done", _on_login_done)
        yield pystray.Menu.SEPARATOR

    pause_text = "\u25b6\ufe0f Resume Automation" if state.paused else "\u23f8\ufe0f Pause Automation"
    yield pystray.MenuItem(pause_text, _toggle_pause)
    yield pystray.MenuItem("\U0001f50c Force Reconnect", _trigger_reconnect)

    visibility_text = "\U0001f441\ufe0f Show Chrome" if state.browser_hidden else "\U0001f648 Hide Chrome"
    yield pystray.MenuItem(visibility_text, _toggle_browser)

    yield pystray.Menu.SEPARATOR
    yield pystray.MenuItem("\U0001f4dc View Debug Log", lambda *_: os.startfile(LOG_FILE))
    yield pystray.MenuItem("\U0001f501 Restart App", _restart_app)
    yield pystray.MenuItem("\u274c Exit", _exit_app)


# ── Startup Registration ──────────────────────────────────────────────────────

def register_startup():
    """Register the app in Windows startup via HKCU Run registry key.

    On failure (e.g., permission denied), logs a warning but does not
    prevent the app from running.
    """
    script = os.path.abspath(sys.argv[0])
    cmd = f'"{sys.executable}"' if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{script}"'
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE | winreg.KEY_READ
        )
        winreg.SetValueEx(key, "DiscordAutoJoin", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
    except Exception as e:
        log.warn(f"Registry startup failed: {e}", category="SYS")