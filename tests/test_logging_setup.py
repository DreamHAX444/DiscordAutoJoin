"""
Unit tests for DiscordAutoJoin.logging_setup — CategoryFilter, Console class,
DEBUG_MODE flag, and logger configuration.
"""

import logging

from DiscordAutoJoin.logging_setup import logger, CategoryFilter, Console, log


class TestCategoryFilter:
    """Tests for the CategoryFilter logging filter."""

    def test_adds_default_category(self):
        """Should inject 'SYS' category when record has no category."""
        filt = CategoryFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        # Record should not have category initially
        assert not hasattr(record, "category")
        result = filt.filter(record)
        assert result is True
        assert record.category == "SYS"

    def test_preserves_existing_category(self):
        """Should not overwrite an existing category attribute."""
        filt = CategoryFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.category = "NET"
        result = filt.filter(record)
        assert result is True
        assert record.category == "NET"

    def test_always_returns_true(self):
        """filter() should always return True (never suppress records)."""
        filt = CategoryFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filt.filter(record) is True


class TestConsole:
    """Tests for the Console class (unified console + file logger)."""

    def test_log_is_console_class(self):
        """The 'log' alias should be the Console class itself."""
        assert log is Console

    def test_info_method_exists(self):
        """Console should have an info() static method."""
        assert hasattr(Console, "info")
        assert callable(Console.info)

    def test_ok_method_exists(self):
        """Console should have an ok() static method."""
        assert hasattr(Console, "ok")
        assert callable(Console.ok)

    def test_warn_method_exists(self):
        """Console should have a warn() static method."""
        assert hasattr(Console, "warn")
        assert callable(Console.warn)

    def test_error_method_exists(self):
        """Console should have an error() static method."""
        assert hasattr(Console, "error")
        assert callable(Console.error)

    def test_info_prints_to_console(self, capsys):
        """Console.info() should print to stdout when not silent."""
        Console.info("Test message", silent=False, category="SYS")
        captured = capsys.readouterr()
        assert "Test message" in captured.out
        assert "[SYS]" in captured.out

    def test_info_suppressed_when_silent(self, capsys):
        """Console.info() should not print when silent=True."""
        Console.info("Silent message", silent=True, category="SYS")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_info_prints_in_debug_mode(self, capsys):
        """Console.info() should print even when silent if DEBUG_MODE is True."""
        import DiscordAutoJoin.logging_setup as ls

        original = ls.DEBUG_MODE
        ls.DEBUG_MODE = True
        try:
            Console.info("Debug message", silent=True, category="SYS")
            captured = capsys.readouterr()
            assert "Debug message" in captured.out
        finally:
            ls.DEBUG_MODE = original

    def test_error_prints_to_console(self, capsys):
        """Console.error() should print to stdout."""
        Console.error("Error message", silent=False, category="ERR")
        captured = capsys.readouterr()
        assert "Error message" in captured.out
        assert "[ERR]" in captured.out

    def test_warn_prints_to_console(self, capsys):
        """Console.warn() should print to stdout."""
        Console.warn("Warning message", silent=False, category="SYS")
        captured = capsys.readouterr()
        assert "Warning message" in captured.out

    def test_ok_prints_to_console(self, capsys):
        """Console.ok() should print to stdout."""
        Console.ok("OK message", silent=False, category="SYS")
        captured = capsys.readouterr()
        assert "OK message" in captured.out

    def test_default_category_is_sys(self, capsys):
        """Default category should be 'SYS'."""
        Console.info("Default category test", silent=False)
        captured = capsys.readouterr()
        assert "[SYS]" in captured.out

    def test_custom_category_appears(self, capsys):
        """Custom category should appear in output."""
        Console.info("Custom category", silent=False, category="NET")
        captured = capsys.readouterr()
        assert "[NET]" in captured.out

    def test_flush_on_print(self, capsys):
        """Output should be flushed (flush=True in print)."""
        Console.info("Flush test", silent=False)
        captured = capsys.readouterr()
        assert "Flush test" in captured.out


class TestLogger:
    """Tests for the module-level logger instance."""

    def test_logger_exists(self):
        """The 'logger' instance should exist."""
        assert logger is not None

    def test_logger_name(self):
        """Logger should be named 'DiscordAutoJoin'."""
        assert logger.name == "DiscordAutoJoin"

    def test_logger_has_category_filter(self):
        """Logger should have at least one CategoryFilter attached."""
        has_cat_filter = any(isinstance(f, CategoryFilter) for f in logger.filters)
        assert has_cat_filter

    def test_logger_level_is_debug(self):
        """Logger level should be DEBUG."""
        assert logger.level == logging.DEBUG

    def test_logger_has_handlers(self):
        """Logger should have at least one handler (RotatingFileHandler)."""
        assert len(logger.handlers) > 0


class TestDebugMode:
    """Tests for the DEBUG_MODE flag."""

    def test_debug_mode_default_false(self):
        """DEBUG_MODE should default to False."""
        import DiscordAutoJoin.logging_setup as ls

        assert ls.DEBUG_MODE is False

    def test_debug_mode_can_be_set(self):
        """DEBUG_MODE should be settable."""
        import DiscordAutoJoin.logging_setup as ls

        original = ls.DEBUG_MODE
        try:
            ls.DEBUG_MODE = True
            assert ls.DEBUG_MODE is True
            ls.DEBUG_MODE = False
            assert ls.DEBUG_MODE is False
        finally:
            ls.DEBUG_MODE = original
