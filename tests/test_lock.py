"""
Unit tests for DiscordAutoJoin.lock — instance locking with PID-based
lock files, stale lock detection, and release.

Tests the cross-platform _pid_exists() helper and the acquire_lock() /
release_lock() public API.
"""

import os
import pytest

import DiscordAutoJoin.lock as lock_mod


class TestPidExists:
    """Tests for the _pid_exists() cross-platform helper."""

    def test_own_pid_exists(self):
        """The current process PID should be detected as alive."""
        assert lock_mod._pid_exists(os.getpid()) is True

    def test_nonexistent_pid(self):
        """A very high PID that doesn't exist should return False."""
        # Use a PID that's extremely unlikely to exist
        assert lock_mod._pid_exists(99999999) is False

    def test_zero_pid(self):
        """PID 0 (System Idle Process on Windows) should be handled."""
        result = lock_mod._pid_exists(0)
        assert isinstance(result, bool)

    def test_negative_pid(self):
        """Negative PIDs should return False."""
        assert lock_mod._pid_exists(-1) is False


class TestAcquireLock:
    """Tests for acquire_lock()."""

    def test_creates_lock_file(self, temp_appdata, mock_lock_file):
        """acquire_lock() should create a lock file with the current PID."""
        assert not os.path.exists(mock_lock_file)
        lock_mod.acquire_lock()
        assert os.path.exists(mock_lock_file)
        with open(mock_lock_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        assert pid == os.getpid()

    def test_lock_file_contains_valid_pid(self, temp_appdata, mock_lock_file):
        """Lock file should contain a valid integer PID."""
        lock_mod.acquire_lock()
        with open(mock_lock_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        pid = int(content)
        assert pid > 0
        assert pid == os.getpid()

    def test_second_instance_detected(self, temp_appdata, mock_lock_file):
        """acquire_lock() should exit when another instance's lock exists."""
        # Create a lock file with our own PID (simulating another instance)
        with open(mock_lock_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        # Calling acquire_lock should trigger sys.exit
        with pytest.raises(SystemExit) as exc_info:
            lock_mod.acquire_lock()
        assert exc_info.value.code == 1

    def test_stale_lock_overwritten(self, temp_appdata, mock_lock_file):
        """A lock file with a non-existent PID should be overwritten."""
        # Write a PID that definitely doesn't exist
        with open(mock_lock_file, "w", encoding="utf-8") as f:
            f.write("99999999")
        # Should not raise — stale lock is overwritten
        lock_mod.acquire_lock()
        assert os.path.exists(mock_lock_file)
        with open(mock_lock_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        assert pid == os.getpid()

    def test_corrupt_lock_file_overwritten(self, temp_appdata, mock_lock_file):
        """A lock file with non-integer content should be overwritten."""
        with open(mock_lock_file, "w", encoding="utf-8") as f:
            f.write("not-a-pid")
        lock_mod.acquire_lock()
        with open(mock_lock_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        assert pid == os.getpid()

    def test_empty_lock_file_overwritten(self, temp_appdata, mock_lock_file):
        """An empty lock file should be overwritten."""
        with open(mock_lock_file, "w", encoding="utf-8") as f:
            f.write("")
        lock_mod.acquire_lock()
        with open(mock_lock_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        assert pid == os.getpid()


class TestReleaseLock:
    """Tests for release_lock()."""

    def test_removes_lock_file(self, temp_appdata, mock_lock_file):
        """release_lock() should remove the lock file."""
        lock_mod.acquire_lock()
        assert os.path.exists(mock_lock_file)
        lock_mod.release_lock()
        assert not os.path.exists(mock_lock_file)

    def test_safe_when_no_lock_file(self, temp_appdata, mock_lock_file):
        """release_lock() should not raise when no lock file exists."""
        assert not os.path.exists(mock_lock_file)
        # Should not raise
        lock_mod.release_lock()

    def test_safe_when_called_twice(self, temp_appdata, mock_lock_file):
        """release_lock() called twice should not raise."""
        lock_mod.acquire_lock()
        lock_mod.release_lock()
        # Second call — should be safe
        lock_mod.release_lock()


class TestLockFileEncoding:
    """Tests for lock file encoding."""

    def test_lock_file_utf8(self, temp_appdata, mock_lock_file):
        """Lock file should be written with UTF-8 encoding."""
        lock_mod.acquire_lock()
        with open(mock_lock_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content.strip().isdigit()
