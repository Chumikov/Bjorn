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
