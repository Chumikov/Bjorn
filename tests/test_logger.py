import logging
from logging.handlers import RotatingFileHandler

import pytest

from rich.logging import RichHandler


class TestLoggerHandlerGuard:
    """LOG-1: Logger() should not accumulate duplicate handlers when called
    repeatedly with the same name."""

    def test_single_instance_has_two_handlers(self):
        from logger import Logger
        log = Logger(name="test.log.dup.single", enable_file_logging=True)
        try:
            # one console handler + one file handler
            assert len(log.logger.handlers) == 2
        finally:
            for h in list(log.logger.handlers):
                log.logger.removeHandler(h)
                h.close()

    def test_repeated_calls_do_not_duplicate_handlers(self):
        from logger import Logger
        # First instantiation
        log1 = Logger(name="test.log.dup.repeated", enable_file_logging=True)
        count_after_first = len(log1.logger.handlers)
        try:
            # Second, third instantiation with same name
            log2 = Logger(name="test.log.dup.repeated", enable_file_logging=True)
            log3 = Logger(name="test.log.dup.repeated", enable_file_logging=True)
            count_after_third = len(log3.logger.handlers)
            assert count_after_first == count_after_third == 2, (
                f"Handler leak: first={count_after_first}, third={count_after_third}")
        finally:
            for h in list(log1.logger.handlers):
                log1.logger.removeHandler(h)
                h.close()

    def test_at_most_one_rich_handler_and_one_file_handler(self):
        from logger import Logger
        log = Logger(name="test.log.dup.types", enable_file_logging=True)
        try:
            for _ in range(5):
                Logger(name="test.log.dup.types", enable_file_logging=True)
            rich_count = sum(1 for h in log.logger.handlers if isinstance(h, RichHandler))
            file_count = sum(1 for h in log.logger.handlers
                             if isinstance(h, RotatingFileHandler))
            assert rich_count == 1, f"Expected 1 RichHandler, got {rich_count}"
            assert file_count == 1, f"Expected 1 RotatingFileHandler, got {file_count}"
        finally:
            for h in list(log.logger.handlers):
                log.logger.removeHandler(h)
                h.close()

    def test_disable_file_logging_adds_only_console_handler(self):
        from logger import Logger
        log = Logger(name="test.log.dup.consoleonly", enable_file_logging=False)
        try:
            assert len(log.logger.handlers) == 1
            assert isinstance(log.logger.handlers[0], RichHandler)
        finally:
            for h in list(log.logger.handlers):
                log.logger.removeHandler(h)
                h.close()


class TestLoggerDisableScoped:
    """LOG-2: disable_logging() should only silence this logger, not other
    loggers in the process."""

    def test_disable_does_not_kill_other_loggers(self):
        from logger import Logger
        # An unrelated logger created BEFORE disable is called must still work.
        other = logging.getLogger("test.log.unrelated.outside")
        other.setLevel(logging.DEBUG)
        other.propagate = False
        captured = []
        class _CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record.getMessage())
        other.addHandler(_CaptureHandler())
        try:
            log = Logger(name="test.log.scoped.disable", enable_file_logging=False)
            log.disable_logging()
            # Emit on the unrelated logger AFTER disable.
            other.warning("should still appear")
            assert "should still appear" in captured, (
                "disable_logging() should not silence other loggers")
        finally:
            other.removeHandler(other.handlers[0])

    def test_disabled_logger_does_not_emit(self):
        from logger import Logger
        log = Logger(name="test.log.scoped.silent", enable_file_logging=False)
        captured = []
        class _CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record.getMessage())
        # Replace handlers with our capture handler to inspect output
        for h in list(log.logger.handlers):
            log.logger.removeHandler(h)
        capture_handler = _CaptureHandler()
        capture_handler.setLevel(logging.DEBUG)
        log.logger.addHandler(capture_handler)
        try:
            log.disable_logging()
            log.error("this should be suppressed")
            assert captured == [], (
                f"Disabled logger should not emit; got {captured}")
        finally:
            log.logger.removeHandler(capture_handler)

    def test_disable_does_not_change_global_logging_disable(self):
        """The fix should NOT use logging.disable() (which is process-global)."""
        from logger import Logger
        # Snapshot the global disable level before
        before = logging.root.manager.disable
        try:
            log = Logger(name="test.log.scoped.noglobal", enable_file_logging=False)
            log.disable_logging()
            after = logging.root.manager.disable
            assert before == after, (
                f"Global logging.disable level changed: {before} -> {after}. "
                f"disable_logging() must be instance-scoped, not global.")
        finally:
            # Restore in case some other test runs after
            logging.disable(before)

    def test_source_does_not_call_global_logging_disable(self):
        """AST guarantee: disable_logging must not invoke the module-level
        logging.disable() (which is process-global)."""
        import ast
        import inspect
        import textwrap
        from logger import Logger
        src = inspect.getsource(Logger.disable_logging)
        # Method source is indented inside a class; dedent before parsing.
        src = textwrap.dedent(src)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if (node.func.attr == "disable"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "logging"):
                    pytest.fail(
                        "disable_logging() must not call logging.disable(); "
                        "that is a process-global side-effect. Use "
                        "self.logger.setLevel(CRITICAL + 1) instead.")
