"""
Unit tests for DiscordAutoJoin.browser — Chrome process management,
lock removal, priority adjustment, and HWND discovery.

Uses mocked psutil to avoid real system process manipulation.
"""

import os
import time
import asyncio
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

import DiscordAutoJoin.browser as browser_mod


# ── Mock Helpers ──────────────────────────────────────────────────────────────

def _make_mock_proc(pid, name="chrome.exe", cmdline=None, rss_mb=100):
    """Create a mock psutil.Process with the given attributes."""
    proc = MagicMock()
    proc.info = {
        'pid': pid,
        'name': name,
        'cmdline': cmdline or [],
        'memory_info': MagicMock(rss=rss_mb * 1024 * 1024),
    }
    proc.kill = MagicMock()
    proc.nice = MagicMock()
    return proc


class TestGetChromeProcs:
    """Tests for _get_chrome_procs() generator."""

    def test_yields_chrome_processes(self):
        """Should yield processes whose name contains 'chrome'."""
        procs = [
            _make_mock_proc(100, "chrome.exe"),
            _make_mock_proc(200, "chrome.exe"),
            _make_mock_proc(300, "notepad.exe"),
        ]
        with patch('psutil.process_iter', return_value=procs):
            results = list(browser_mod._get_chrome_procs())
            assert len(results) == 2
            assert results[0].info['pid'] == 100
            assert results[1].info['pid'] == 200

    def test_filters_by_profile_name(self):
        """Should filter by profile name in command line."""
        procs = [
            _make_mock_proc(100, "chrome.exe", ["chrome.exe", "--profile-dir=MyProfile"]),
            _make_mock_proc(200, "chrome.exe", ["chrome.exe", "--other"]),
        ]
        with patch('psutil.process_iter', return_value=procs):
            results = list(browser_mod._get_chrome_procs(profile_name="MyProfile"))
            assert len(results) == 1
            assert results[0].info['pid'] == 100

    def test_handles_no_chrome_processes(self):
        """Should return empty when no Chrome processes exist."""
        procs = [_make_mock_proc(300, "notepad.exe")]
        with patch('psutil.process_iter', return_value=procs):
            results = list(browser_mod._get_chrome_procs())
            assert len(results) == 0

    def test_handles_no_processes_at_all(self):
        """Should return empty when no processes exist."""
        with patch('psutil.process_iter', return_value=[]):
            results = list(browser_mod._get_chrome_procs())
            assert len(results) == 0

    def test_handles_access_denied(self):
        """Should skip processes that raise AccessDenied."""
        import psutil
        bad_proc = MagicMock()
        bad_proc.info = {}
        # Make accessing .info['name'] raise AccessDenied
        type(bad_proc).info = PropertyMock(side_effect=psutil.AccessDenied())

        good_proc = _make_mock_proc(100, "chrome.exe")
        with patch('psutil.process_iter', return_value=[bad_proc, good_proc]):
            results = list(browser_mod._get_chrome_procs())
            assert len(results) == 1
            assert results[0].info['pid'] == 100

    def test_handles_no_such_process(self):
        """Should skip processes that raise NoSuchProcess."""
        import psutil
        bad_proc = MagicMock()
        type(bad_proc).info = PropertyMock(side_effect=psutil.NoSuchProcess(123))

        good_proc = _make_mock_proc(100, "chrome.exe")
        with patch('psutil.process_iter', return_value=[bad_proc, good_proc]):
            results = list(browser_mod._get_chrome_procs())
            assert len(results) == 1

    def test_handles_enumeration_error(self):
        """Should handle process_iter itself raising an exception."""
        with patch('psutil.process_iter', side_effect=RuntimeError("Enumeration failed")):
            results = list(browser_mod._get_chrome_procs())
            assert len(results) == 0

    def test_case_insensitive_name_match(self):
        """Should match 'Chrome.exe', 'CHROME.EXE', etc."""
        procs = [
            _make_mock_proc(100, "Chrome.Exe"),
            _make_mock_proc(200, "CHROME.EXE"),
        ]
        with patch('psutil.process_iter', return_value=procs):
            results = list(browser_mod._get_chrome_procs())
            assert len(results) == 2

    def test_handles_none_cmdline(self):
        """Should handle processes with None cmdline."""
        proc = _make_mock_proc(100, "chrome.exe", cmdline=None)
        proc.info['cmdline'] = None
        with patch('psutil.process_iter', return_value=[proc]):
            results = list(browser_mod._get_chrome_procs(profile_name="test"))
            # None cmdline won't match any profile_name, so filtered out
            assert len(results) == 0

    def test_handles_none_name(self):
        """Should skip processes with None name."""
        proc = _make_mock_proc(100, name=None)
        proc.info['name'] = None
        with patch('psutil.process_iter', return_value=[proc]):
            results = list(browser_mod._get_chrome_procs())
            assert len(results) == 0


class TestKillStaleChrome:
    """Tests for kill_stale_chrome() async function."""

    @pytest.mark.asyncio
    async def test_kills_matching_processes(self):
        """Should kill processes matching the profile name."""
        procs = [
            _make_mock_proc(100, "chrome.exe", ["chrome.exe", "--profile=ChromeProfile"]),
            _make_mock_proc(200, "chrome.exe", ["chrome.exe", "--profile=ChromeProfile"]),
        ]
        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=procs):
            with patch('psutil.pid_exists', return_value=False):  # All dead after kill
                await browser_mod.kill_stale_chrome()
                procs[0].kill.assert_called_once()
                procs[1].kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_no_processes(self):
        """Should not error when no Chrome processes exist."""
        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=[]):
            await browser_mod.kill_stale_chrome()  # Should not raise

    @pytest.mark.asyncio
    async def test_handles_kill_failure(self):
        """Should handle AccessDenied when killing a process."""
        import psutil
        proc = _make_mock_proc(100, "chrome.exe", ["chrome.exe", "--profile=ChromeProfile"])
        proc.kill.side_effect = psutil.AccessDenied()
        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=[proc]):
            with patch('psutil.pid_exists', return_value=False):
                await browser_mod.kill_stale_chrome()  # Should not raise

    @pytest.mark.asyncio
    async def test_waits_for_process_exit(self):
        """Should poll until killed processes are gone."""
        proc = _make_mock_proc(100, "chrome.exe", ["chrome.exe", "--profile=ChromeProfile"])
        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=[proc]):
            # First call returns True (still alive), then False (dead)
            with patch('psutil.pid_exists', side_effect=[True, False]):
                await browser_mod.kill_stale_chrome()
                proc.kill.assert_called_once()


class TestRemoveChromeLocks:
    """Tests for remove_chrome_locks()."""

    def test_removes_existing_lock_files(self, tmp_path):
        """Should remove SingletonLock and other lock files if present."""
        # Create mock lock files
        locks = ["SingletonLock", "SingletonCookie", "lockfile"]
        for fname in locks:
            (tmp_path / fname).touch()

        with patch('DiscordAutoJoin.browser.CHROME_PROFILE_DIR', str(tmp_path)):
            browser_mod.remove_chrome_locks()
            for fname in locks:
                assert not (tmp_path / fname).exists()

    def test_handles_no_lock_files(self, tmp_path):
        """Should not error when no lock files exist."""
        with patch('DiscordAutoJoin.browser.CHROME_PROFILE_DIR', str(tmp_path)):
            browser_mod.remove_chrome_locks()  # Should not raise

    def test_removes_crashpad_directory(self, tmp_path):
        """Should remove Crashpad directory if present."""
        crashpad = tmp_path / "Crashpad"
        crashpad.mkdir()
        (crashpad / "metadata").touch()

        with patch('DiscordAutoJoin.browser.CHROME_PROFILE_DIR', str(tmp_path)):
            browser_mod.remove_chrome_locks()
            assert not crashpad.exists()

    def test_handles_permission_error(self, tmp_path):
        """Should not raise on permission errors during removal."""
        (tmp_path / "SingletonLock").touch()
        with patch('os.remove', side_effect=PermissionError("Access denied")):
            with patch('DiscordAutoJoin.browser.CHROME_PROFILE_DIR', str(tmp_path)):
                browser_mod.remove_chrome_locks()  # Should not raise


class TestLowerChromePriority:
    """Tests for lower_chrome_priority()."""

    def test_lowers_priority_of_chrome_processes(self):
        """Should call proc.nice() with BELOW_NORMAL_PRIORITY_CLASS."""
        import psutil
        procs = [
            _make_mock_proc(100, "chrome.exe", rss_mb=150),
            _make_mock_proc(200, "chrome.exe", rss_mb=200),
        ]
        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=procs):
            result = browser_mod.lower_chrome_priority()
            assert result['count'] == 2
            assert result['total_memory_mb'] == pytest.approx(350.0, rel=0.1)
            assert result['pids'] == [100, 200]
            assert 'elapsed' in result
            procs[0].nice.assert_called_once_with(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            procs[1].nice.assert_called_once_with(psutil.BELOW_NORMAL_PRIORITY_CLASS)

    def test_returns_zero_when_no_chrome(self):
        """Should return count=0 when no Chrome processes exist."""
        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=[]):
            result = browser_mod.lower_chrome_priority()
            assert result['count'] == 0
            assert result['total_memory_mb'] == 0.0
            assert result['pids'] == []

    def test_handles_access_denied(self):
        """Should skip processes that can't be adjusted."""
        import psutil
        bad_proc = _make_mock_proc(100, "chrome.exe")
        bad_proc.nice.side_effect = psutil.AccessDenied()
        good_proc = _make_mock_proc(200, "chrome.exe", rss_mb=100)

        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=[bad_proc, good_proc]):
            result = browser_mod.lower_chrome_priority()
            assert result['count'] == 1
            assert result['pids'] == [200]

    def test_handles_no_such_process(self):
        """Should skip processes that disappear during iteration."""
        import psutil
        bad_proc = _make_mock_proc(100, "chrome.exe")
        bad_proc.nice.side_effect = psutil.NoSuchProcess(100)

        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=[bad_proc]):
            result = browser_mod.lower_chrome_priority()
            assert result['count'] == 0

    def test_handles_none_memory_info(self):
        """Should handle processes with None memory_info."""
        proc = _make_mock_proc(100, "chrome.exe")
        proc.info['memory_info'] = None

        with patch('DiscordAutoJoin.browser._get_chrome_procs', return_value=[proc]):
            result = browser_mod.lower_chrome_priority()
            assert result['count'] == 1
            assert result['total_memory_mb'] == 0.0


class TestFindChromeHwnd:
    """Tests for find_chrome_hwnd() — Windows-specific HWND discovery."""

    def test_sets_hwnd_when_found(self, reset_state):
        """Should set state.browser_hwnd when a Discord window is found."""
        mock_hwnd = 12345

        def mock_enum(callback, _):
            # Simulate finding a window with 'discord' in title
            callback(mock_hwnd, None)
            return True

        with patch('ctypes.windll.user32.EnumWindows', side_effect=mock_enum):
            with patch('ctypes.windll.user32.IsWindowVisible', return_value=True):
                with patch('ctypes.windll.user32.GetWindowTextLengthW', return_value=10):
                    with patch('ctypes.windll.user32.GetWindowTextW') as mock_get_text:
                        # Make the buffer contain 'discord'
                        def set_text(hwnd, buf, size):
                            buf.value = "Discord | Voice Channel"
                        mock_get_text.side_effect = set_text

                        browser_mod.find_chrome_hwnd(reset_state)
                        assert reset_state.browser_hwnd == mock_hwnd

    def test_no_hwnd_when_no_discord_window(self, reset_state):
        """Should not set browser_hwnd when no Discord window exists."""
        mock_hwnd = 12345

        def mock_enum(callback, _):
            callback(mock_hwnd, None)
            return True

        with patch('ctypes.windll.user32.EnumWindows', side_effect=mock_enum):
            with patch('ctypes.windll.user32.IsWindowVisible', return_value=True):
                with patch('ctypes.windll.user32.GetWindowTextLengthW', return_value=10):
                    with patch('ctypes.windll.user32.GetWindowTextW') as mock_get_text:
                        def set_text(hwnd, buf, size):
                            buf.value = "Notepad - Untitled"
                        mock_get_text.side_effect = set_text

                        browser_mod.find_chrome_hwnd(reset_state)
                        assert reset_state.browser_hwnd is None

    def test_skips_invisible_windows(self, reset_state):
        """Should skip windows that are not visible."""
        def mock_enum(callback, _):
            callback(12345, None)
            return True

        with patch('ctypes.windll.user32.EnumWindows', side_effect=mock_enum):
            with patch('ctypes.windll.user32.IsWindowVisible', return_value=False):
                browser_mod.find_chrome_hwnd(reset_state)
                assert reset_state.browser_hwnd is None

    def test_skips_empty_title_windows(self, reset_state):
        """Should skip windows with empty titles."""
        def mock_enum(callback, _):
            callback(12345, None)
            return True

        with patch('ctypes.windll.user32.EnumWindows', side_effect=mock_enum):
            with patch('ctypes.windll.user32.IsWindowVisible', return_value=True):
                with patch('ctypes.windll.user32.GetWindowTextLengthW', return_value=0):
                    browser_mod.find_chrome_hwnd(reset_state)
                    assert reset_state.browser_hwnd is None

    def test_case_insensitive_discord_match(self, reset_state):
        """Should match 'DISCORD', 'Discord', 'discord' in window title."""
        mock_hwnd = 12345

        def mock_enum(callback, _):
            callback(mock_hwnd, None)
            return True

        with patch('ctypes.windll.user32.EnumWindows', side_effect=mock_enum):
            with patch('ctypes.windll.user32.IsWindowVisible', return_value=True):
                with patch('ctypes.windll.user32.GetWindowTextLengthW', return_value=10):
                    with patch('ctypes.windll.user32.GetWindowTextW') as mock_get_text:
                        def set_text(hwnd, buf, size):
                            buf.value = "DISCORD | My Server"
                        mock_get_text.side_effect = set_text

                        browser_mod.find_chrome_hwnd(reset_state)
                        assert reset_state.browser_hwnd == mock_hwnd