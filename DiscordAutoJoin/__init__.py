"""
DiscordAutoJoin — Automated Discord voice channel joiner.

A Windows background application that automatically joins a Discord
voice channel, enables the camera, mutes the mic, and monitors
connection health via a system tray icon.
"""

from .config import CONFIG, CONFIG_FILE
from .logging_setup import logger, log, DEBUG_MODE
from .state import state
from .lock import acquire_lock, release_lock
from .tray import register_startup, _get_icon, _menu_generator, icon as tray_icon
from .automation import run_asyncio_loop
from .main import VERSION, main, main_debug