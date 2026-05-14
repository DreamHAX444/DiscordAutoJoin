"""
Application configuration management.

Handles:
- Path constants (app data dir, Chrome profile, log/lock/config files)
- Default configuration values
- JSON config loading with UTF-8 encoding, field validation, and
  automatic merging of missing keys from defaults.
"""

import os
import json
import logging

logger = logging.getLogger("DiscordAutoJoin")

# ── Path Constants ────────────────────────────────────────────────────────────
APP_DATA_DIR = os.path.join(os.environ["APPDATA"], "DiscordAutoJoin")
CHROME_PROFILE_DIR = os.path.join(APP_DATA_DIR, "ChromeProfile")
LOG_FILE = os.path.join(APP_DATA_DIR, "app.log")
LOCK_FILE = os.path.join(APP_DATA_DIR, "app.lock")
CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")
os.makedirs(APP_DATA_DIR, exist_ok=True)

# ── Default Configuration ─────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "DISCORD_URL": "https://discord.com/channels/1436354443636379732/1436354444462784625",
    "MAX_JOIN_RETRIES": 30,
    "POLL_INTERVAL": 5.0,
    "RESTART_DELAY": 5,
    "HEALTH_LOG_EVERY": 12,
    "MAX_CONSECUTIVE_ERRS": 3,
    "MAX_RELOAD_FAILS": 2,
    "MAX_LAUNCH_RETRIES": 5,
}


def load_config():
    """Load configuration from disk with UTF-8 encoding, merging with defaults.

    On first run, creates the config file with DEFAULT_CONFIG values.
    On subsequent runs, merges saved config with defaults so new keys
    are always present. Validates required fields and logs warnings
    for missing keys.

    Returns:
        dict: Merged configuration dictionary. Falls back to DEFAULT_CONFIG on any error.
    """
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        # Validate required fields — warn if any defaults are missing from saved config
        missing = [k for k in DEFAULT_CONFIG if k not in loaded]
        if missing:
            logger.warning(f"Config file missing keys: {missing}. Filling from defaults.")
        merged = {**DEFAULT_CONFIG, **loaded}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as out:
            json.dump(merged, out, indent=4, ensure_ascii=False)
        return merged
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Config load error: {e}. Using defaults.")
        return dict(DEFAULT_CONFIG)


# Module-level config instance — loaded once at import time
CONFIG = load_config()