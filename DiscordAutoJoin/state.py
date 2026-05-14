"""
Thread-safe application state shared between the asyncio automation thread
and the main (system tray) thread.

All mutable fields are protected by threading.RLock. Access is through
properties that acquire the lock automatically. threading.Event objects
(first_run_done, should_exit) are inherently thread-safe and exposed directly.
"""

import time
import threading
from datetime import datetime


class AppState:
    """Mutable application state with RLock-protected properties.

    Shared between:
    - The asyncio automation thread (reads/writes status, counters, flags)
    - The main tray thread (reads status for menu display, writes pause/exit flags)

    threading.Event objects are inherently thread-safe and exposed directly.
    All other fields use @property with RLock.
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Thread-safe events (no lock needed)
        self.first_run_done = threading.Event()
        self.should_exit = threading.Event()

        # RLock-protected fields
        self._status = "Initializing"
        self._paused = False
        self._force_reconnect = False
        self._browser_hwnd = None
        self._browser_hidden = False
        self._is_restarting = False
        self._restart_count = 0
        self._start_time = time.time()
        self._last_action = "App Started"
        self._action_timestamp = datetime.now()

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def status(self):
        with self._lock:
            return self._status

    @status.setter
    def status(self, value):
        with self._lock:
            self._status = value

    @property
    def paused(self):
        with self._lock:
            return self._paused

    @paused.setter
    def paused(self, value):
        with self._lock:
            self._paused = value

    @property
    def force_reconnect(self):
        with self._lock:
            return self._force_reconnect

    @force_reconnect.setter
    def force_reconnect(self, value):
        with self._lock:
            self._force_reconnect = value

    @property
    def browser_hwnd(self):
        with self._lock:
            return self._browser_hwnd

    @browser_hwnd.setter
    def browser_hwnd(self, value):
        with self._lock:
            self._browser_hwnd = value

    @property
    def browser_hidden(self):
        with self._lock:
            return self._browser_hidden

    @browser_hidden.setter
    def browser_hidden(self, value):
        with self._lock:
            self._browser_hidden = value

    @property
    def is_restarting(self):
        with self._lock:
            return self._is_restarting

    @is_restarting.setter
    def is_restarting(self, value):
        with self._lock:
            self._is_restarting = value

    @property
    def restart_count(self):
        with self._lock:
            return self._restart_count

    @restart_count.setter
    def restart_count(self, value):
        with self._lock:
            self._restart_count = value

    @property
    def start_time(self):
        with self._lock:
            return self._start_time

    @property
    def last_action(self):
        with self._lock:
            return self._last_action

    @last_action.setter
    def last_action(self, value):
        with self._lock:
            self._last_action = value

    @property
    def action_timestamp(self):
        with self._lock:
            return self._action_timestamp

    @action_timestamp.setter
    def action_timestamp(self, value):
        with self._lock:
            self._action_timestamp = value


# Singleton instance — imported by all modules that need shared state
state = AppState()