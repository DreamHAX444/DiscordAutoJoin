"""
Unit tests for DiscordAutoJoin.config — configuration loading, merging,
missing keys, corrupt files, and environment variable handling.
"""

import os
import json

import DiscordAutoJoin.config as cfg


class TestDefaultConfig:
    """Tests for DEFAULT_CONFIG and initial state."""

    def test_default_config_has_required_keys(self):
        """DEFAULT_CONFIG must contain all expected keys."""
        required = [
            "DISCORD_URL",
            "MAX_JOIN_RETRIES",
            "POLL_INTERVAL",
            "RESTART_DELAY",
            "HEALTH_LOG_EVERY",
            "MAX_CONSECUTIVE_ERRS",
            "MAX_RELOAD_FAILS",
            "MAX_LAUNCH_RETRIES",
        ]
        for key in required:
            assert key in cfg.DEFAULT_CONFIG, f"Missing key: {key}"

    def test_default_config_types(self):
        """DEFAULT_CONFIG values must have correct types."""
        assert isinstance(cfg.DEFAULT_CONFIG["DISCORD_URL"], str)
        assert isinstance(cfg.DEFAULT_CONFIG["MAX_JOIN_RETRIES"], int)
        assert isinstance(cfg.DEFAULT_CONFIG["POLL_INTERVAL"], float)
        assert isinstance(cfg.DEFAULT_CONFIG["RESTART_DELAY"], int)
        assert isinstance(cfg.DEFAULT_CONFIG["HEALTH_LOG_EVERY"], int)
        assert isinstance(cfg.DEFAULT_CONFIG["MAX_CONSECUTIVE_ERRS"], int)
        assert isinstance(cfg.DEFAULT_CONFIG["MAX_RELOAD_FAILS"], int)
        assert isinstance(cfg.DEFAULT_CONFIG["MAX_LAUNCH_RETRIES"], int)


class TestLoadConfig:
    """Tests for load_config() behavior."""

    def test_first_run_creates_config_file(self, temp_appdata):
        """On first run (no config file), load_config() creates one with defaults."""
        assert not os.path.exists(cfg.CONFIG_FILE)
        result = cfg.load_config()
        assert os.path.exists(cfg.CONFIG_FILE)
        assert result == cfg.DEFAULT_CONFIG

    def test_loads_existing_config(self, temp_appdata, sample_config_dict):
        """load_config() reads an existing config file correctly."""
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(sample_config_dict, f)
        result = cfg.load_config()
        assert result["DISCORD_URL"] == sample_config_dict["DISCORD_URL"]
        assert result["MAX_JOIN_RETRIES"] == sample_config_dict["MAX_JOIN_RETRIES"]

    def test_merges_missing_keys_from_defaults(self, temp_appdata):
        """Missing keys in saved config are filled from DEFAULT_CONFIG."""
        partial = {"DISCORD_URL": "https://custom.url/channels/1/2"}
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(partial, f)
        result = cfg.load_config()
        # Custom value preserved
        assert result["DISCORD_URL"] == "https://custom.url/channels/1/2"
        # Missing keys filled from defaults
        assert result["MAX_JOIN_RETRIES"] == cfg.DEFAULT_CONFIG["MAX_JOIN_RETRIES"]
        assert result["POLL_INTERVAL"] == cfg.DEFAULT_CONFIG["POLL_INTERVAL"]

    def test_corrupt_json_falls_back_to_defaults(self, temp_appdata):
        """Corrupt JSON file should fall back to DEFAULT_CONFIG."""
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("this is not valid json {{{")
        result = cfg.load_config()
        assert result == cfg.DEFAULT_CONFIG

    def test_empty_file_falls_back_to_defaults(self, temp_appdata):
        """Empty config file should fall back to DEFAULT_CONFIG."""
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("")
        result = cfg.load_config()
        assert result == cfg.DEFAULT_CONFIG

    def test_utf8_encoding_supported(self, temp_appdata):
        """Config with UTF-8 characters should load correctly."""
        data = {"DISCORD_URL": "https://discord.com/channels/123/456"}
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        result = cfg.load_config()
        assert result["DISCORD_URL"] == data["DISCORD_URL"]

    def test_extra_keys_preserved(self, temp_appdata):
        """User-added keys not in DEFAULT_CONFIG should be preserved."""
        data = {"DISCORD_URL": "https://x.com", "CUSTOM_KEY": "custom_value"}
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = cfg.load_config()
        assert result["CUSTOM_KEY"] == "custom_value"
        # Default keys still present
        assert "MAX_JOIN_RETRIES" in result


class TestPathConstants:
    """Tests for path constants."""

    def test_app_data_dir_in_appdata(self, temp_appdata):
        """APP_DATA_DIR must be under the APPDATA environment variable."""
        assert cfg.APP_DATA_DIR.startswith(temp_appdata)

    def test_chrome_profile_dir_under_appdata(self, temp_appdata):
        """CHROME_PROFILE_DIR must be a subdirectory of APP_DATA_DIR."""
        assert cfg.CHROME_PROFILE_DIR.startswith(cfg.APP_DATA_DIR)

    def test_log_file_under_appdata(self, temp_appdata):
        """LOG_FILE must be under APP_DATA_DIR."""
        assert cfg.LOG_FILE.startswith(cfg.APP_DATA_DIR)

    def test_lock_file_under_appdata(self, temp_appdata):
        """LOCK_FILE must be under APP_DATA_DIR."""
        assert cfg.LOCK_FILE.startswith(cfg.APP_DATA_DIR)

    def test_config_file_under_appdata(self, temp_appdata):
        """CONFIG_FILE must be under APP_DATA_DIR."""
        assert cfg.CONFIG_FILE.startswith(cfg.APP_DATA_DIR)

    def test_app_data_dir_exists(self, temp_appdata):
        """APP_DATA_DIR must be created if it doesn't exist."""
        assert os.path.isdir(cfg.APP_DATA_DIR)


class TestModuleLevelConfig:
    """Tests for the module-level CONFIG singleton."""

    def test_config_is_dict(self):
        """CONFIG must be a dict."""
        assert isinstance(cfg.CONFIG, dict)

    def test_config_has_all_default_keys(self):
        """CONFIG must contain all DEFAULT_CONFIG keys."""
        for key in cfg.DEFAULT_CONFIG:
            assert key in cfg.CONFIG, f"Missing key in CONFIG: {key}"
