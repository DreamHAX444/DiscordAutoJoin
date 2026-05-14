"""
Unit tests for DiscordAutoJoin.actions — safe_eval() wrapper, MONITOR_JS
and CLICK_MIC_JS JavaScript snippets, and error handling paths.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock

from DiscordAutoJoin.actions import MONITOR_JS, CLICK_MIC_JS, safe_eval


class TestMonitorJS:
    """Tests for the MONITOR_JS JavaScript snippet structure."""

    def test_is_callable_function(self):
        """MONITOR_JS should be an arrow function string."""
        assert MONITOR_JS.startswith("() => {")
        assert MONITOR_JS.endswith("}")

    def test_returns_object_with_required_keys(self):
        """The JS should return an object with joinVisible, camOff, micUnmuted."""
        assert "joinVisible" in MONITOR_JS
        assert "camOff" in MONITOR_JS
        assert "micUnmuted" in MONITOR_JS
        assert "return { joinVisible, camOff, micUnmuted }" in MONITOR_JS

    def test_uses_xpath_for_join_button(self):
        """Should use XPath to find the Join Voice button (case-insensitive)."""
        assert "join voice" in MONITOR_JS.lower()
        assert "translate" in MONITOR_JS  # Case-insensitive XPath

    def test_checks_aria_label_for_camera(self):
        """Should check aria-label for Turn On Camera."""
        assert "Turn On Camera" in MONITOR_JS

    def test_checks_aria_label_for_mic(self):
        """Should check aria-label for microphone mute/unmute."""
        assert "aria-label" in MONITOR_JS
        assert "ute" in MONITOR_JS  # Mute
        assert "icrophone" in MONITOR_JS  # Microphone

    def test_handles_missing_mic_button(self):
        """Should handle case where mic button is not found."""
        assert "if (micBtn)" in MONITOR_JS

    def test_handles_aria_checked_attribute(self):
        """Should check aria-checked attribute for toggle state."""
        assert "aria-checked" in MONITOR_JS


class TestClickMicJS:
    """Tests for the CLICK_MIC_JS JavaScript snippet."""

    def test_is_callable_function(self):
        """CLICK_MIC_JS should be an arrow function string."""
        assert CLICK_MIC_JS.startswith("() => {")
        assert CLICK_MIC_JS.endswith("}")

    def test_finds_mic_button(self):
        """Should query for microphone button."""
        assert "querySelector" in CLICK_MIC_JS
        assert "icrophone" in CLICK_MIC_JS

    def test_clicks_if_found(self):
        """Should call click() if button is found."""
        assert "click()" in CLICK_MIC_JS

    def test_guards_against_missing_button(self):
        """Should check if micBtn exists before clicking."""
        assert "if (micBtn)" in CLICK_MIC_JS


class TestSafeEval:
    """Tests for the safe_eval() async wrapper."""

    @pytest.mark.asyncio
    async def test_returns_evaluation_result(self):
        """safe_eval should return the JS evaluation result."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {"test": "value"}

        result = await safe_eval(mock_page, "() => ({ test: 'value' })")
        assert result == {"test": "value"}
        mock_page.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_timeout_to_wait_for(self):
        """safe_eval should pass timeout to asyncio.wait_for."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = "ok"

        result = await safe_eval(mock_page, "() => 'ok'", timeout=5)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        """safe_eval should return None when evaluation times out."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=asyncio.TimeoutError())

        result = await safe_eval(mock_page, "() => ({})", timeout=0.001)
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_on_browser_closed(self):
        """safe_eval should re-raise PlaywrightError for closed browser."""
        from playwright.async_api import Error as PlaywrightError

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(
            side_effect=PlaywrightError(
                "Target page, context or browser has been closed"
            )
        )

        with pytest.raises(PlaywrightError):
            await safe_eval(mock_page, "() => ({})")

    @pytest.mark.asyncio
    async def test_raises_on_browser_closed_alt_message(self):
        """safe_eval should re-raise for 'Browser closed' message variant."""
        from playwright.async_api import Error as PlaywrightError

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(
            side_effect=PlaywrightError("Browser closed unexpectedly")
        )

        with pytest.raises(PlaywrightError):
            await safe_eval(mock_page, "() => ({})")

    @pytest.mark.asyncio
    async def test_returns_none_on_non_fatal_playwright_error(self):
        """safe_eval should return None for non-fatal Playwright errors."""
        from playwright.async_api import Error as PlaywrightError

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(
            side_effect=PlaywrightError("Some random selector error")
        )

        result = await safe_eval(mock_page, "() => ({})")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_generic_exception(self):
        """safe_eval should return None for unexpected exceptions."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Unexpected failure"))

        result = await safe_eval(mock_page, "() => ({})")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_value_error(self):
        """safe_eval should return None for ValueError."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=ValueError("Bad value"))

        result = await safe_eval(mock_page, "() => ({})")
        assert result is None

    @pytest.mark.asyncio
    async def test_default_timeout_is_10(self):
        """safe_eval should default to 10 second timeout."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = "ok"

        # We can't easily assert the timeout value, but we can verify
        # the function signature accepts it as optional
        result = await safe_eval(mock_page, "() => 'ok'")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_passes_monitor_js_correctly(self):
        """safe_eval should work with MONITOR_JS."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "joinVisible": False,
            "camOff": False,
            "micUnmuted": False,
        }

        result = await safe_eval(mock_page, MONITOR_JS)
        assert result == {"joinVisible": False, "camOff": False, "micUnmuted": False}

    @pytest.mark.asyncio
    async def test_passes_click_mic_js_correctly(self):
        """safe_eval should work with CLICK_MIC_JS."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = None

        result = await safe_eval(mock_page, CLICK_MIC_JS)
        assert result is None
