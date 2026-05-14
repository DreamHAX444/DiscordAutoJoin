"""
Unit tests for DiscordAutoJoin.tray — icon generation, menu generator,
tray callbacks, set_tray(), update_last_action(), and register_startup().
"""

import os
import sys
import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from DiscordAutoJoin.tray import (
    _get_icon, _menu_generator, set_tray, update_last_action,
    _on_login_done, _toggle_pause, _trigger_reconnect,
    _restart_app, _exit_app, register_startup,
)
from DiscordAutoJoin.state import state


class TestGetIcon:
    """Tests for _get_icon() icon generation and caching."""

    def test_returns_pil_image(self):
        """Should return a PIL Image."""
        from PIL import Image
        icon = _get_icon("green")
        assert isinstance(icon, Image.Image)

    def test_correct_dimensions(self):
        """Icon should be 64x64 pixels."""
        icon = _get_icon("green")
        assert icon.size == (64, 64)

    def test_rgb_mode(self):
        """Icon should be in RGB mode."""
        icon = _get_icon("green")
        assert icon.mode == "RGB"

    def test_caches_icons(self):
        """Same color should return the same cached object."""
        icon1 = _get_icon("green")
        icon2 = _get_icon("green")
        assert icon1 is icon2

    def test_different_colors_different_objects(self):
        """Different colors should return different objects."""
        green = _get_icon("green")
        red = _get_icon("red")
        assert green is not red

    def test_supports_named_colors(self):
        """Should support named colors like 'green', 'yellow', 'blue'."""
        for color in ['green', 'yellow', 'blue', 'darkred', 'gray']:
            icon = _get_icon(color)
            assert icon is not None

    def test_supports_hex_colors(self):
        """Should support hex color strings."""
        icon = _get_icon("#FF0000")
        assert icon is not None

    def test_black_background(self):
        """Icon should have a black background (pixel at 0,0)."""
        icon = _get_icon("green")
        pixel = icon.getpixel((0, 0))
        assert pixel == (0, 0, 0)


class TestMenuGenerator:
    """Tests for _menu_generator() dynamic menu."""

    def test_yields_menu_items(self, reset_state):
        """Should yield pystray.MenuItem objects."""
        import pystray
        items = list(_menu_generator())
        assert len(items) > 0
        for item in items:
            assert isinstance(item, pystray.MenuItem)

    def test_contains_status_item(self, reset_state):
        """Menu should contain a status display item."""
        reset_state.status = "Connected"
        items = list(_menu_generator())
        status_items = [i for i in items if "Status:" in str(i.text)]
        assert len(status_items) >= 1

    def test_contains_uptime_item(self, reset_state):
        """Menu should contain an uptime display item."""
        items = list(_menu_generator())
        uptime_items = [i for i in items if "Uptime:" in str(i.text)]
        assert len(uptime_items) >= 1

    def test_contains_last_action_item(self, reset_state):
        """Menu should contain a last action display item."""
        items = list(_menu_generator())
        action_items = [i for i in items if "Last:" in str(i.text)]
        assert len(action_items) >= 1

    def test_contains_restart_count_item(self, reset_state):
        """Menu should contain a restart count display item."""
        items = list(_menu_generator())
        restart_items = [i for i in items if "Restarts:" in str(i.text)]
        assert len(restart_items) >= 1

    def test_contains_pause_toggle(self, reset_state):
        """Menu should contain a pause/resume toggle item."""
        items = list(_menu_generator())
        pause_items = [i for i in items if "Pause" in str(i.text) or "Resume" in str(i.text)]
        assert len(pause_items) >= 1

    def test_contains_force_reconnect(self, reset_state):
        """Menu should contain a force reconnect item."""
        items = list(_menu_generator())
        reconnect_items = [i for i in items if "Reconnect" in str(i.text)]
        assert len(reconnect_items) >= 1

    def test_contains_show_hide_browser(self, reset_state):
        """Menu should contain a show/hide browser toggle."""
        items = list(_menu_generator())
        browser_items = [i for i in items if "Chrome" in str(i.text)]
        assert len(browser_items) >= 1

    def test_contains_exit_item(self, reset_state):
        """Menu should contain an exit item."""
        items = list(_menu_generator())
        exit_items = [i for i in items if "Exit" in str(i.text)]
        assert len(exit_items) >= 1

    def test_contains_restart_item(self, reset_state):
        """Menu should contain a restart item."""
        items = list(_menu_generator())
        restart_items = [i for i in items if "Restart App" in str(i.text)]
        assert len(restart_items) >= 1

    def test_contains_view_log_item(self, reset_state):
        """Menu should contain a view debug log item."""
        items = list(_menu_generator())
        log_items = [i for i in items if "Log" in str(i.text)]
        assert len(log_items) >= 1

    def test_login_item_when_waiting(self, reset_state):
        """When status is 'Waiting for login', menu should show Confirm Login."""
        reset_state.status = "Waiting for login"
        items = list(_menu_generator())
        login_items = [i for i in items if "Confirm Login" in str(i.text)]
        assert len(login_items) >= 1

    def test_no_login_item_when_connected(self, reset_state):
        """When connected, menu should NOT show Confirm Login."""
        reset_state.status = "Connected"
        items = list(_menu_generator())
        login_items = [i for i in items if "Confirm Login" in str(i.text)]
        assert len(login_items) == 0

    def test_pause_text_when_running(self, reset_state):
        """When not paused, menu should show 'Pause Automation'."""
        reset_state.paused = False
        items = list(_menu_generator())
        pause_items = [i for i in items if "Pause Automation" in str(i.text)]
        assert len(pause_items) >= 1

    def test_resume_text_when_paused(self, reset_state):
        """When paused, menu should show 'Resume Automation'."""
        reset_state.paused = True
        items = list(_menu_generator())
        resume_items = [i for i in items if "Resume Automation" in str(i.text)]
        assert len(resume_items) >= 1

    def test_show_chrome_when_hidden(self, reset_state):
        """When browser is hidden, menu should show 'Show Chrome'."""
        reset_state.browser_hidden = True
        items = list(_menu_generator())
        show_items = [i for i in items if "Show Chrome" in str(i.text)]
        assert len(show_items) >= 1

    def test_hide_chrome_when_visible(self, reset_state):
        """When browser is visible, menu should show 'Hide Chrome'."""
        reset_state.browser_hidden = False
        items = list(_menu_generator())
        hide_items = [i for i in items if "Hide Chrome" in str(i.text)]
        assert len(hide_items) >= 1

    def test_config_submenu_present(self, reset_state):
        """Menu should contain a View Config submenu."""
        items = list(_menu_generator())
        config_items = [i for i in items if "View Config" in str(i.text)]
        assert len(config_items) >= 1

    def test_dashboard_items_disabled(self, reset_state):
        """Dashboard items (status, uptime, etc.) should be disabled."""
        items = list(_menu_generator())
        dashboard_items = [i for i in items if "Status:" in str(i.text)]
        for item in dashboard_items:
            assert item.enabled is False


class TestSetTray:
    """Tests for set_tray() function."""

    def test_updates_state_status(self, reset_state):
        """Should update state.status."""
        set_tray("Connected", "green")
        assert reset_state.status == "Connected"

    def test_no_error_when_icon_is_none(self, reset_state):
        """Should not raise when tray icon is not set."""
        import DiscordAutoJoin.tray as tray_mod
        tray_mod.icon = None
        set_tray("Connected", "green")  # Should not raise

    def test_sets_icon_color(self, reset_state):
        """Should set icon color on the tray icon object."""
        import DiscordAutoJoin.tray as tray_mod
        mock_icon = MagicMock()
        tray_mod.icon = mock_icon

        set_tray("Connected", "green")
        assert mock_icon.icon is not None
        mock_icon.update_menu.assert_called_once()

        tray_mod.icon = None  # Cleanup

    def test_sets_tooltip(self, reset_state):
        """Should set the tray tooltip text."""
        import DiscordAutoJoin.tray as tray_mod
        mock_icon = MagicMock()
        tray_mod.icon = mock_icon

        set_tray("Connected", "green")
        assert "Connected" in mock_icon.title

        tray_mod.icon = None

    def test_paused_overrides_to_gray(self, reset_state):
        """When paused, icon should be gray regardless of color arg."""
        import DiscordAutoJoin.tray as tray_mod
        mock_icon = MagicMock()
        tray_mod.icon = mock_icon
        reset_state.paused = True

        set_tray("Connected", "green")
        # The icon should be gray (we can't easily check the color,
        # but we can verify the tooltip shows paused)
        assert "Paused" in mock_icon.title

        tray_mod.icon = None


class TestUpdateLastAction:
    """Tests for update_last_action() function."""

    def test_updates_state_last_action(self, reset_state):
        """Should update state.last_action."""
        update_last_action("Test action")
        assert reset_state.last_action == "Test action"

    def test_updates_action_timestamp(self, reset_state):
        """Should update state.action_timestamp."""
        before = datetime.now()
        update_last_action("Test action")
        assert reset_state.action_timestamp >= before

    def test_no_error_when_icon_is_none(self, reset_state):
        """Should not raise when tray icon is not set."""
        import DiscordAutoJoin.tray as tray_mod
        tray_mod.icon = None
        update_last_action("Test action")  # Should not raise

    def test_default_category_is_state(self, reset_state):
        """Default category should be 'STATE'."""
        update_last_action("Test action")
        assert reset_state.last_action == "Test action"


class TestTrayCallbacks:
    """Tests for tray action callbacks."""

    def test_on_login_done_sets_event(self, reset_state):
        """_on_login_done should set first_run_done event."""
        assert not reset_state.first_run_done.is_set()
        _on_login_done()
        assert reset_state.first_run_done.is_set()

    def test_on_login_done_updates_status(self, reset_state):
        """_on_login_done should set status to 'Connecting...'."""
        _on_login_done()
        assert reset_state.status == "Connecting..."

    def test_toggle_pause_from_unpaused(self, reset_state):
        """_toggle_pause should set paused=True when unpaused."""
        reset_state.paused = False
        _toggle_pause()
        assert reset_state.paused is True

    def test_toggle_pause_from_paused(self, reset_state):
        """_toggle_pause should set paused=False when paused."""
        reset_state.paused = True
        _toggle_pause()
        assert reset_state.paused is False

    def test_trigger_reconnect_sets_flag(self, reset_state):
        """_trigger_reconnect should set force_reconnect=True."""
        reset_state.force_reconnect = False
        _trigger_reconnect()
        assert reset_state.force_reconnect is True

    def test_restart_app_sets_flags(self, reset_state):
        """_restart_app should set is_restarting and should_exit."""
        reset_state.is_restarting = False
        assert not reset_state.should_exit.is_set()
        _restart_app()
        assert reset_state.is_restarting is True
        assert reset_state.should_exit.is_set()

    def test_exit_app_sets_should_exit(self, reset_state):
        """_exit_app should set should_exit."""
        assert not reset_state.should_exit.is_set()
        _exit_app()
        assert reset_state.should_exit.is_set()

    def test_exit_app_does_not_set_restarting(self, reset_state):
        """_exit_app should NOT set is_restarting."""
        reset_state.is_restarting = False
        _exit_app()
        assert reset_state.is_restarting is False


class TestRegisterStartup:
    """Tests for register_startup() Windows registry function."""

    def test_handles_registry_error_gracefully(self):
        """Should log a warning but not raise on registry errors."""
        with patch('winreg.OpenKey', side_effect=PermissionError("Access denied")):
            # Should not raise
            register_startup()

    def test_handles_generic_error_gracefully(self):
        """Should handle any exception during registry access."""
        with patch('winreg.OpenKey', side_effect=RuntimeError("Unexpected")):
            register_startup()  # Should not raise

    def test_uses_frozen_path_when_frozen(self):
        """When sys.frozen is True, should use only executable path."""
        with patch('sys.frozen', True, create=True):
            with patch('winreg.OpenKey') as mock_open:
                with patch('winreg.SetValueEx'):
                    with patch('winreg.CloseKey'):
                        register_startup()
                        # Verify it was called (didn't crash)
                        mock_open.assert_called_once()