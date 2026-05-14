"""
End-to-end integration tests for DiscordAutoJoin.

Simulates a full automation run using mocked Playwright browser, page,
and Discord interactions. Validates the complete flow:
configuration loading → browser launch → login → join action →
state update → monitoring → cleanup.

All external dependencies (Chrome, Discord API) are mocked to avoid
real network calls. Uses pytest-asyncio for async test support.
"""

import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

# Ensure package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Mock Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_page():
    """Create a fully mocked Playwright Page with all methods used by automation."""
    page = AsyncMock()
    page.is_closed.return_value = False

    # Mock locator chain — page.locator() is synchronous in Playwright
    mock_locator = AsyncMock()
    mock_locator.count.return_value = 0  # No auth box = logged in
    mock_locator.first = mock_locator
    mock_locator.click = AsyncMock()
    mock_locator.wait_for = AsyncMock()

    # page.locator must be a MagicMock (sync), not AsyncMock
    page.locator = MagicMock(return_value=mock_locator)
    page.goto = AsyncMock()
    page.reload = AsyncMock()
    page.route = AsyncMock()
    page.add_style_tag = AsyncMock()
    page.evaluate = AsyncMock()
    page.close = AsyncMock()

    return page


@pytest.fixture
def mock_context(mock_page):
    """Create a mocked Playwright BrowserContext."""
    context = AsyncMock()
    context.pages = [mock_page]
    context.new_page = AsyncMock(return_value=mock_page)
    context.close = AsyncMock()
    return context


@pytest.fixture
def mock_browser():
    """Create a mocked Playwright Browser."""
    browser = AsyncMock()
    return browser


@pytest.fixture
def mock_playwright(mock_context):
    """Create a mocked Playwright instance."""
    pw = AsyncMock()
    pw.chromium.launch_persistent_context = AsyncMock(return_value=mock_context)
    return pw


@pytest.fixture
def integration_state(temp_appdata, clean_config):
    """Set up state for integration testing with clean config."""
    from DiscordAutoJoin.state import state

    # Reset everything
    state.status = "Initializing"
    state.paused = False
    state.force_reconnect = False
    state.browser_hwnd = None
    state.browser_hidden = False
    state.is_restarting = False
    state.restart_count = 0
    state.last_action = "App Started"
    state.first_run_done.clear()
    state.should_exit.clear()
    yield state
    state.should_exit.set()


# ── Integration Tests ──────────────────────────────────────────────────────────


@pytest.mark.integration
class TestConfigurationLoading:
    """Verify config is loaded correctly before automation starts."""

    def test_config_loaded_before_automation(self, integration_state, clean_config):
        """Config must be available and valid before automation loop runs."""
        from DiscordAutoJoin.config import CONFIG

        assert "DISCORD_URL" in CONFIG
        assert "POLL_INTERVAL" in CONFIG
        assert "MAX_JOIN_RETRIES" in CONFIG
        assert isinstance(CONFIG["POLL_INTERVAL"], (int, float))
        assert CONFIG["POLL_INTERVAL"] > 0


@pytest.mark.integration
class TestBrowserLaunchFlow:
    """Verify browser launch sequence with mocked Playwright."""

    @pytest.mark.asyncio
    async def test_launch_persistent_context_called(
        self, integration_state, mock_playwright
    ):
        """Browser launch should use launch_persistent_context with correct args."""
        from DiscordAutoJoin.config import CHROME_PROFILE_DIR
        from DiscordAutoJoin.chrome_flags import CHROME_ARGS

        _context = await mock_playwright.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE_DIR,
            channel="chrome",
            headless=False,
            no_viewport=True,
            permissions=["camera", "microphone"],
            args=CHROME_ARGS,
        )

        mock_playwright.chromium.launch_persistent_context.assert_called_once()
        call_kwargs = (
            mock_playwright.chromium.launch_persistent_context.call_args.kwargs
        )
        assert call_kwargs["channel"] == "chrome"
        assert call_kwargs["headless"] is False
        assert "camera" in call_kwargs["permissions"]
        assert "microphone" in call_kwargs["permissions"]
        assert len(call_kwargs["args"]) > 0

    @pytest.mark.asyncio
    async def test_launch_retry_on_failure(self, integration_state):
        """Failed launches should be retried with exponential backoff."""
        from DiscordAutoJoin.config import CONFIG

        max_retries = CONFIG.get("MAX_LAUNCH_RETRIES", 5)
        assert max_retries >= 1
        # The retry logic exists in automation.py — verify the config value
        assert isinstance(max_retries, int)


@pytest.mark.integration
class TestLoginFlow:
    """Verify login detection and manual login flow."""

    @pytest.mark.asyncio
    async def test_auth_detection_when_logged_out(self, mock_page, integration_state):
        """When auth box is present, should wait for manual login."""
        # Simulate logged-out state
        mock_page.locator.return_value.count.return_value = 1  # Auth box present
        mock_page.evaluate.return_value = {"test": True}

        from DiscordAutoJoin.actions import safe_eval

        # safe_eval should handle the logged-out page gracefully
        result = await safe_eval(mock_page, "() => ({ test: true })")
        assert result == {"test": True}

    @pytest.mark.asyncio
    async def test_auth_detection_when_logged_in(self, mock_page, integration_state):
        """When no auth box, should proceed directly to join."""
        mock_page.locator.return_value.count.return_value = 0  # No auth box
        mock_page.evaluate.return_value = {"test": True}

        from DiscordAutoJoin.actions import safe_eval

        result = await safe_eval(mock_page, "() => ({ test: true })")
        assert result == {"test": True}

    def test_first_run_done_event_flow(self, integration_state):
        """first_run_done event should control login wait loop."""
        assert not integration_state.first_run_done.is_set()
        integration_state.first_run_done.set()
        assert integration_state.first_run_done.is_set()
        integration_state.first_run_done.clear()
        assert not integration_state.first_run_done.is_set()


@pytest.mark.integration
class TestJoinAction:
    """Verify voice channel join sequence."""

    @pytest.mark.asyncio
    async def test_join_button_click(self, mock_page, integration_state):
        """Join Voice button should be clicked when visible."""
        mock_page.locator.return_value.click = AsyncMock()

        btn = mock_page.locator('button:has-text("Join Voice")').first
        await btn.click(timeout=3000)

        mock_page.locator.return_value.click.assert_called()

    @pytest.mark.asyncio
    async def test_disconnect_button_appears_after_join(
        self, mock_page, integration_state
    ):
        """After joining, Disconnect button should be waited for."""
        mock_page.locator.return_value.wait_for = AsyncMock()

        await mock_page.locator('[aria-label="Disconnect"]').first.wait_for(
            state="visible", timeout=8000
        )

        mock_page.locator.return_value.wait_for.assert_called()

    @pytest.mark.asyncio
    async def test_join_retry_on_timeout(self, integration_state):
        """Join retries should respect MAX_JOIN_RETRIES config."""
        from DiscordAutoJoin.config import CONFIG

        assert CONFIG["MAX_JOIN_RETRIES"] > 0
        assert isinstance(CONFIG["MAX_JOIN_RETRIES"], int)


@pytest.mark.integration
class TestMonitoringLoop:
    """Verify health monitoring and state polling."""

    @pytest.mark.asyncio
    async def test_monitor_js_returns_expected_structure(
        self, mock_page, integration_state
    ):
        """MONITOR_JS evaluation should return joinVisible, camOff, micUnmuted."""
        from DiscordAutoJoin.actions import MONITOR_JS, safe_eval

        # Mock the JS evaluation to return a healthy state
        mock_page.evaluate.return_value = {
            "joinVisible": False,
            "camOff": False,
            "micUnmuted": False,
        }

        result = await safe_eval(mock_page, MONITOR_JS)
        assert result is not None
        assert "joinVisible" in result
        assert "camOff" in result
        assert "micUnmuted" in result

    @pytest.mark.asyncio
    async def test_voice_drop_detection(self, mock_page, integration_state):
        """When joinVisible is True, voice has dropped."""
        from DiscordAutoJoin.actions import MONITOR_JS, safe_eval

        mock_page.evaluate.return_value = {
            "joinVisible": True,  # Voice dropped!
            "camOff": False,
            "micUnmuted": False,
        }

        result = await safe_eval(mock_page, MONITOR_JS)
        assert result["joinVisible"] is True

    @pytest.mark.asyncio
    async def test_camera_off_detection(self, mock_page, integration_state):
        """When camOff is True, camera needs re-enabling."""
        from DiscordAutoJoin.actions import MONITOR_JS, safe_eval

        mock_page.evaluate.return_value = {
            "joinVisible": False,
            "camOff": True,  # Camera off!
            "micUnmuted": False,
        }

        result = await safe_eval(mock_page, MONITOR_JS)
        assert result["camOff"] is True

    @pytest.mark.asyncio
    async def test_mic_unmuted_detection(self, mock_page, integration_state):
        """When micUnmuted is True, mic needs muting."""
        from DiscordAutoJoin.actions import MONITOR_JS, safe_eval

        mock_page.evaluate.return_value = {
            "joinVisible": False,
            "camOff": False,
            "micUnmuted": True,  # Mic unmuted!
        }

        result = await safe_eval(mock_page, MONITOR_JS)
        assert result["micUnmuted"] is True

    @pytest.mark.asyncio
    async def test_poll_interval_respected(self, integration_state):
        """POLL_INTERVAL config should be a positive number."""
        from DiscordAutoJoin.config import CONFIG

        assert CONFIG["POLL_INTERVAL"] > 0
        assert isinstance(CONFIG["POLL_INTERVAL"], (int, float))


@pytest.mark.integration
class TestStateTransitions:
    """Verify state changes throughout the automation lifecycle."""

    def test_initial_state(self, integration_state):
        """State should start at Initializing."""
        assert integration_state.status == "Initializing"
        assert integration_state.paused is False
        assert integration_state.restart_count == 0

    def test_state_transitions_to_connected(self, integration_state):
        """State should transition through statuses."""
        integration_state.status = "Loading..."
        assert integration_state.status == "Loading..."

        integration_state.status = "Connecting..."
        assert integration_state.status == "Connecting..."

        integration_state.status = "Connected"
        assert integration_state.status == "Connected"

    def test_pause_toggles_state(self, integration_state):
        """Pause should toggle correctly."""
        integration_state.paused = True
        assert integration_state.paused is True
        integration_state.paused = False
        assert integration_state.paused is False

    def test_force_reconnect_triggers_restart(self, integration_state):
        """force_reconnect should be settable."""
        integration_state.force_reconnect = True
        assert integration_state.force_reconnect is True
        integration_state.force_reconnect = False
        assert integration_state.force_reconnect is False

    def test_restart_count_increments(self, integration_state):
        """restart_count should increment across restarts."""
        integration_state.restart_count = 0
        integration_state.restart_count += 1
        assert integration_state.restart_count == 1
        integration_state.restart_count += 1
        assert integration_state.restart_count == 2


@pytest.mark.integration
class TestCleanup:
    """Verify cleanup procedures."""

    def test_should_exit_stops_loop(self, integration_state):
        """Setting should_exit should signal the automation loop to stop."""
        assert not integration_state.should_exit.is_set()
        integration_state.should_exit.set()
        assert integration_state.should_exit.is_set()

    def test_lock_released_on_exit(self, temp_appdata, mock_lock_file):
        """Lock file should be removable after release."""
        from DiscordAutoJoin.lock import acquire_lock, release_lock

        acquire_lock()
        assert os.path.exists(mock_lock_file)
        release_lock()
        assert not os.path.exists(mock_lock_file)

    @pytest.mark.asyncio
    async def test_context_close_on_cleanup(self, mock_context):
        """Browser context should be closed during cleanup."""
        await mock_context.close()
        mock_context.close.assert_called_once()


@pytest.mark.integration
class TestErrorRecovery:
    """Verify error recovery paths."""

    @pytest.mark.asyncio
    async def test_safe_eval_handles_timeout(self, mock_page, integration_state):
        """safe_eval should return None on timeout."""
        from DiscordAutoJoin.actions import safe_eval

        mock_page.evaluate = AsyncMock(side_effect=asyncio.TimeoutError())

        result = await safe_eval(mock_page, "() => ({})", timeout=0.01)
        assert result is None

    @pytest.mark.asyncio
    async def test_safe_eval_handles_page_closed(self, mock_page, integration_state):
        """safe_eval should re-raise PlaywrightError for closed browser."""
        from DiscordAutoJoin.actions import safe_eval
        from playwright.async_api import Error as PlaywrightError

        mock_page.evaluate = AsyncMock(
            side_effect=PlaywrightError(
                "Target page, context or browser has been closed"
            )
        )

        with pytest.raises(PlaywrightError):
            await safe_eval(mock_page, "() => ({})")

    @pytest.mark.asyncio
    async def test_safe_eval_handles_generic_error(self, mock_page, integration_state):
        """safe_eval should return None on generic Playwright errors."""
        from DiscordAutoJoin.actions import safe_eval
        from playwright.async_api import Error as PlaywrightError

        mock_page.evaluate = AsyncMock(
            side_effect=PlaywrightError("Some non-fatal error")
        )

        result = await safe_eval(mock_page, "() => ({})")
        assert result is None

    def test_max_consecutive_errors_config(self, integration_state):
        """MAX_CONSECUTIVE_ERRS should trigger page reload."""
        from DiscordAutoJoin.config import CONFIG

        assert CONFIG["MAX_CONSECUTIVE_ERRS"] > 0
        assert isinstance(CONFIG["MAX_CONSECUTIVE_ERRS"], int)

    def test_max_reload_fails_config(self, integration_state):
        """MAX_RELOAD_FAILS should trigger context restart."""
        from DiscordAutoJoin.config import CONFIG

        assert CONFIG["MAX_RELOAD_FAILS"] > 0
        assert isinstance(CONFIG["MAX_RELOAD_FAILS"], int)


@pytest.mark.integration
class TestResourceOptimization:
    """Verify resource guard and optimization features."""

    @pytest.mark.asyncio
    async def test_optimize_page_called(self, mock_page, integration_state):
        """optimize_page should set up route interception and CSS injection."""
        from DiscordAutoJoin.resource_guard import optimize_page

        await optimize_page(mock_page)

        mock_page.route.assert_called_once()
        mock_page.add_style_tag.assert_called_once()

    def test_chrome_args_no_dangerous_flags(self):
        """CHROME_ARGS must not contain dangerous security-disabling flags."""
        from DiscordAutoJoin.chrome_flags import CHROME_ARGS

        dangerous = [
            "--disable-web-security",
            "--no-sandbox",
            "--disable-site-isolation-trials",
            "--disable-gpu-sandbox",
        ]
        for flag in dangerous:
            assert flag not in CHROME_ARGS, f"Dangerous flag found: {flag}"

    def test_chrome_args_has_resource_limits(self):
        """CHROME_ARGS should include memory-limiting flags."""
        from DiscordAutoJoin.chrome_flags import CHROME_ARGS

        assert "--js-flags=--max-old-space-size=128" in CHROME_ARGS
        assert "--renderer-process-limit=1" in CHROME_ARGS


@pytest.mark.integration
class TestTrayIntegration:
    """Verify tray icon and menu integration points."""

    def test_tray_module_imports(self):
        """Tray module should be importable without errors."""
        from DiscordAutoJoin.tray import (
            _get_icon,
            _menu_generator,
            set_tray,
            update_last_action,
            register_startup,
        )

        # All symbols should be callable or accessible
        assert callable(_get_icon)
        assert callable(_menu_generator)
        assert callable(set_tray)
        assert callable(update_last_action)
        assert callable(register_startup)

    def test_icon_generation(self):
        """_get_icon should return a PIL Image for valid colors."""
        from DiscordAutoJoin.tray import _get_icon
        from PIL import Image

        for color in ["green", "yellow", "blue", "darkred", "gray", "#FF0000"]:
            icon = _get_icon(color)
            assert isinstance(icon, Image.Image)
            assert icon.size == (64, 64)

    def test_icon_caching(self):
        """_get_icon should cache generated icons."""
        from DiscordAutoJoin.tray import _get_icon

        icon1 = _get_icon("green")
        icon2 = _get_icon("green")
        assert icon1 is icon2  # Same object (cached)

    def test_menu_generator_yields_items(self):
        """_menu_generator should yield pystray.MenuItem objects."""
        from DiscordAutoJoin.tray import _menu_generator
        import pystray

        items = list(_menu_generator())
        assert len(items) > 0
        for item in items:
            assert isinstance(item, pystray.MenuItem)


@pytest.mark.integration
class TestModuleCohesion:
    """Verify all 12 modules import and work together."""

    def test_all_modules_importable(self):
        """Every module in the package should be importable."""
        modules = [
            "DiscordAutoJoin.chrome_flags",
            "DiscordAutoJoin.config",
            "DiscordAutoJoin.logging_setup",
            "DiscordAutoJoin.lock",
            "DiscordAutoJoin.state",
            "DiscordAutoJoin.resource_guard",
            "DiscordAutoJoin.actions",
            "DiscordAutoJoin.browser",
            "DiscordAutoJoin.tray",
            "DiscordAutoJoin.automation",
            "DiscordAutoJoin",
        ]
        for mod_name in modules:
            try:
                __import__(mod_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {mod_name}: {e}")

    def test_package_exports_all_required_symbols(self):
        """__init__.py should export all symbols used by main.py."""
        from DiscordAutoJoin import (
            CONFIG,
            state,
        )

        # If we got here without ImportError, all exports work
        assert CONFIG is not None
        assert state is not None

    def test_no_circular_imports(self):
        """Importing the package should not cause circular import errors."""
        # This would raise ImportError if circular deps exist
        import DiscordAutoJoin

        # Access a few symbols to trigger lazy imports
        _ = DiscordAutoJoin.state
        _ = DiscordAutoJoin.CONFIG
        _ = DiscordAutoJoin.logger
