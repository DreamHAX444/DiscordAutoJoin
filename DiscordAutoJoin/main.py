"""
DiscordAutoJoin — Automated Discord voice channel joiner.

Entry point. Sets up logging, acquires the instance lock, registers
Windows startup, starts the asyncio automation thread, and runs the
system tray icon loop.

Usage:
    python -m DiscordAutoJoin.main
    python -m DiscordAutoJoin.main --debug
    python -m DiscordAutoJoin.main --version
"""

import sys
import os
import threading
import subprocess
import argparse

# Ensure the package directory is importable when run directly
if __name__ == "__main__" and __package__ is None:
    _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _parent)
    __package__ = "DiscordAutoJoin"

from . import (
    CONFIG, CONFIG_FILE,
    logger, log, DEBUG_MODE,
    state,
    acquire_lock, release_lock,
    register_startup, _get_icon, _menu_generator,
    run_asyncio_loop,
)
from .tray import icon as tray_icon_module
import pystray

# ── Version ────────────────────────────────────────────────────────────────────
VERSION = "1.0.0"


def parse_args():
    """Parse command-line arguments.

    Returns:
        argparse.Namespace with 'debug' (bool) and 'version' (bool) attributes.
    """
    parser = argparse.ArgumentParser(
        description="DiscordAutoJoin — Automated Discord voice channel joiner"
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable debug mode: all log messages print to console, extra diagnostics'
    )
    parser.add_argument(
        '--version', '-V', action='store_true',
        help='Print version and exit'
    )
    return parser.parse_args()


def main():
    """Entry point for console_scripts: runs the application normally.
    
    Parses command-line arguments to support --version and --debug flags.
    """
    args = parse_args()
    if args.version:
        print(f"DiscordAutoJoin v{VERSION}")
        sys.exit(0)
    _run_app(debug=args.debug)


def main_debug():
    """Entry point for console_scripts: runs the application in debug mode.
    
    Supports --version flag to print version and exit without starting the app.
    """
    args = parse_args()
    if args.version:
        print(f"DiscordAutoJoin v{VERSION}")
        sys.exit(0)
    _run_app(debug=True)


def _run_app(debug=False):
    """Core application runner — shared by main() and main_debug().

    Args:
        debug: If True, enable debug mode (all messages to console).
    """
    if debug:
        from . import logging_setup
        logging_setup.DEBUG_MODE = True
        log.info("Debug mode enabled", category="SYS")

    acquire_lock()
    register_startup()
    log.info(f"DiscordAutoJoin v{VERSION} started. Config loaded from {CONFIG_FILE}", category="SYS")

    auto_thread = threading.Thread(target=run_asyncio_loop, daemon=True)
    auto_thread.start()

    try:
        icon = pystray.Icon(
            "DiscordAutoJoin",
            _get_icon("gray"),
            "Auto-Join: Initializing",
            menu=pystray.Menu(_menu_generator)
        )
        # Set the module-level icon reference so tray callbacks can access it
        import DiscordAutoJoin.tray as tray_mod
        tray_mod.icon = icon

        icon.run()
    finally:
        state.should_exit.set()
        auto_thread.join(timeout=10)
        release_lock()
        if state.is_restarting:
            subprocess.Popen([sys.executable] + sys.argv)


if __name__ == "__main__":
    args = parse_args()
    if args.version:
        print(f"DiscordAutoJoin v{VERSION}")
        sys.exit(0)
    _run_app(debug=args.debug)