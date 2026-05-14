"""
Unit tests for DiscordAutoJoin.state — thread-safe AppState with RLock-protected
properties, threading.Event behavior, and concurrent access patterns.
"""

import threading

from DiscordAutoJoin.state import AppState, state


class TestAppStateInit:
    """Tests for AppState initialization."""

    def test_default_status(self):
        """New AppState should have 'Initializing' status."""
        s = AppState()
        assert s.status == "Initializing"

    def test_default_paused_false(self):
        """New AppState should not be paused."""
        s = AppState()
        assert s.paused is False

    def test_default_force_reconnect_false(self):
        """New AppState should not have force_reconnect set."""
        s = AppState()
        assert s.force_reconnect is False

    def test_default_browser_hwnd_none(self):
        """New AppState should have no browser HWND."""
        s = AppState()
        assert s.browser_hwnd is None

    def test_default_browser_hidden_false(self):
        """New AppState should not have browser hidden."""
        s = AppState()
        assert s.browser_hidden is False

    def test_default_is_restarting_false(self):
        """New AppState should not be restarting."""
        s = AppState()
        assert s.is_restarting is False

    def test_default_restart_count_zero(self):
        """New AppState should have restart_count of 0."""
        s = AppState()
        assert s.restart_count == 0

    def test_default_last_action(self):
        """New AppState should have 'App Started' as last_action."""
        s = AppState()
        assert s.last_action == "App Started"

    def test_events_created(self):
        """first_run_done and should_exit must be threading.Event instances."""
        s = AppState()
        assert isinstance(s.first_run_done, threading.Event)
        assert isinstance(s.should_exit, threading.Event)

    def test_events_initially_unset(self):
        """Events should start unset."""
        s = AppState()
        assert not s.first_run_done.is_set()
        assert not s.should_exit.is_set()


class TestAppStateProperties:
    """Tests for property getters and setters."""

    def test_status_get_set(self, reset_state):
        """status property should get and set correctly."""
        reset_state.status = "Connected"
        assert reset_state.status == "Connected"

    def test_paused_get_set(self, reset_state):
        """paused property should get and set correctly."""
        reset_state.paused = True
        assert reset_state.paused is True
        reset_state.paused = False
        assert reset_state.paused is False

    def test_force_reconnect_get_set(self, reset_state):
        """force_reconnect property should get and set correctly."""
        reset_state.force_reconnect = True
        assert reset_state.force_reconnect is True

    def test_browser_hwnd_get_set(self, reset_state):
        """browser_hwnd property should get and set correctly."""
        reset_state.browser_hwnd = 12345
        assert reset_state.browser_hwnd == 12345

    def test_browser_hidden_get_set(self, reset_state):
        """browser_hidden property should get and set correctly."""
        reset_state.browser_hidden = True
        assert reset_state.browser_hidden is True

    def test_is_restarting_get_set(self, reset_state):
        """is_restarting property should get and set correctly."""
        reset_state.is_restarting = True
        assert reset_state.is_restarting is True

    def test_restart_count_get_set(self, reset_state):
        """restart_count property should get and set correctly."""
        reset_state.restart_count = 5
        assert reset_state.restart_count == 5

    def test_last_action_get_set(self, reset_state):
        """last_action property should get and set correctly."""
        reset_state.last_action = "Test Action"
        assert reset_state.last_action == "Test Action"

    def test_action_timestamp_get_set(self, reset_state):
        """action_timestamp property should get and set correctly."""
        from datetime import datetime

        ts = datetime.now()
        reset_state.action_timestamp = ts
        assert reset_state.action_timestamp == ts

    def test_start_time_is_float(self, reset_state):
        """start_time should be a float (time.time() value)."""
        assert isinstance(reset_state.start_time, float)
        assert reset_state.start_time > 0


class TestAppStateThreadSafety:
    """Tests for concurrent access to AppState properties."""

    def test_concurrent_reads(self, reset_state):
        """Multiple threads reading properties should not deadlock."""
        reset_state.status = "Testing"
        results = []

        def reader():
            for _ in range(100):
                results.append(reset_state.status)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 500
        assert all(r == "Testing" for r in results)

    def test_concurrent_writes(self, reset_state):
        """Multiple threads writing restart_count should not corrupt state."""

        def writer(start, count):
            for i in range(start, start + count):
                reset_state.restart_count = i

        t1 = threading.Thread(target=writer, args=(0, 100))
        t2 = threading.Thread(target=writer, args=(100, 100))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Final value should be one of the written values (not corrupted)
        assert 0 <= reset_state.restart_count <= 199

    def test_concurrent_read_write(self, reset_state):
        """Concurrent reads and writes should not deadlock or corrupt."""
        errors = []

        def reader():
            try:
                for _ in range(200):
                    _ = reset_state.status
                    _ = reset_state.paused
                    _ = reset_state.restart_count
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(200):
                    reset_state.status = f"State-{i}"
                    reset_state.restart_count = i
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent access: {errors}"


class TestAppStateEvents:
    """Tests for threading.Event behavior."""

    def test_first_run_done_set_clear(self, reset_state):
        """first_run_done event should be settable and clearable."""
        assert not reset_state.first_run_done.is_set()
        reset_state.first_run_done.set()
        assert reset_state.first_run_done.is_set()
        reset_state.first_run_done.clear()
        assert not reset_state.first_run_done.is_set()

    def test_should_exit_set_clear(self, reset_state):
        """should_exit event should be settable and clearable."""
        assert not reset_state.should_exit.is_set()
        reset_state.should_exit.set()
        assert reset_state.should_exit.is_set()
        reset_state.should_exit.clear()
        assert not reset_state.should_exit.is_set()

    def test_event_wait_timeout(self, reset_state):
        """Event.wait() with timeout should return False when not set."""
        assert not reset_state.first_run_done.wait(timeout=0.01)

    def test_event_wait_signaled(self, reset_state):
        """Event.wait() should return True immediately when set."""
        reset_state.first_run_done.set()
        assert reset_state.first_run_done.wait(timeout=0.01)


class TestSingletonState:
    """Tests for the module-level singleton 'state'."""

    def test_singleton_is_appstate(self):
        """The module-level 'state' must be an AppState instance."""
        assert isinstance(state, AppState)

    def test_singleton_same_instance(self):
        """Importing state twice should return the same instance."""
        from DiscordAutoJoin.state import state as state2

        assert state is state2
