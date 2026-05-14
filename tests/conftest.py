"""
Shared pytest fixtures and configuration for DiscordAutoJoin tests.

Provides:
- Temporary directories for config, lock files, and Chrome profiles.
- Mocked environment variables (APPDATA).
- Cleanup helpers for lock files and state reset.
"""

import os
import sys
import tempfile
import shutil
import pytest

# Ensure the package is importable from the tests directory
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)


@pytest.fixture
def temp_appdata(monkeypatch):
    """Create a temporary %APPDATA% directory and point the app at it.

    Updates both config.py constants AND the lock module's cached
    LOCK_FILE reference so acquire_lock() uses the temp directory.

    Yields the path to the temp directory. Cleans up after the test.
    """
    tmp = tempfile.mkdtemp(prefix="discordautojoin_test_")
    monkeypatch.setenv("APPDATA", tmp)
    # Re-import config so it picks up the new APPDATA
    import DiscordAutoJoin.config as cfg
    import DiscordAutoJoin.lock as lock_mod

    original_dir = cfg.APP_DATA_DIR
    original_lock_file = lock_mod.LOCK_FILE

    cfg.APP_DATA_DIR = tmp
    cfg.CHROME_PROFILE_DIR = os.path.join(tmp, "ChromeProfile")
    cfg.LOG_FILE = os.path.join(tmp, "app.log")
    cfg.LOCK_FILE = os.path.join(tmp, "app.lock")
    cfg.CONFIG_FILE = os.path.join(tmp, "config.json")

    # Also update the lock module's cached reference
    lock_mod.LOCK_FILE = cfg.LOCK_FILE

    os.makedirs(cfg.APP_DATA_DIR, exist_ok=True)
    yield tmp
    # Restore
    cfg.APP_DATA_DIR = original_dir
    lock_mod.LOCK_FILE = original_lock_file
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def clean_config(temp_appdata):
    """Provide a fresh config file with DEFAULT_CONFIG values.

    Returns the path to the config file.
    """
    import DiscordAutoJoin.config as cfg

    if os.path.exists(cfg.CONFIG_FILE):
        os.remove(cfg.CONFIG_FILE)
    # Force reload
    cfg.CONFIG = cfg.load_config()
    return cfg.CONFIG_FILE


@pytest.fixture
def sample_config_dict():
    """Return a sample configuration dictionary for testing."""
    return {
        "DISCORD_URL": "https://discord.com/channels/123/456",
        "MAX_JOIN_RETRIES": 10,
        "POLL_INTERVAL": 3.0,
        "RESTART_DELAY": 2,
        "HEALTH_LOG_EVERY": 6,
        "MAX_CONSECUTIVE_ERRS": 2,
        "MAX_RELOAD_FAILS": 1,
        "MAX_LAUNCH_RETRIES": 3,
    }


@pytest.fixture
def reset_state():
    """Reset the global AppState singleton to defaults after each test."""
    from DiscordAutoJoin.state import state

    # Save events (they can't be reset easily)
    first_run = state.first_run_done
    should_exit = state.should_exit
    yield state
    # Reset all mutable fields
    state.status = "Initializing"
    state.paused = False
    state.force_reconnect = False
    state.browser_hwnd = None
    state.browser_hidden = False
    state.is_restarting = False
    state.restart_count = 0
    state.last_action = "App Started"
    first_run.clear()
    should_exit.clear()


@pytest.fixture
def mock_lock_file(temp_appdata):
    """Create a mock lock file with a fake PID, then clean up.

    Ensures no existing lock file is present before the test and
    cleans up after. Uses the temp_appdata path.
    """
    import DiscordAutoJoin.config as cfg

    lock_path = cfg.LOCK_FILE
    # Ensure no existing lock
    if os.path.exists(lock_path):
        os.remove(lock_path)
    yield lock_path
    if os.path.exists(lock_path):
        os.remove(lock_path)
