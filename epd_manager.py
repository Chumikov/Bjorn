"""epd_manager.py - Singleton wrapper around Waveshare EPD drivers.

PORT-2: replaces the bare ``EPDHelper`` with a singleton that serializes
SPI access (class-level ``RLock``), retries transient failures, and
recovers (hard reset + driver reload) after consecutive errors. The public
API (``init_full_update`` / ``init_partial_update`` / ``display_partial``
/ ``clear``) is a strict superset of the old helper, so call sites in
``shared.py`` and ``display.py`` keep working unchanged; the ``epd``
attribute still holds the raw Waveshare EPD object (``.width``/``.height``).

Adapted from ``upstream/ai:epd_manager.py`` (verbatim behaviour; Logger
call adjusted to this fork's signature).
"""
import importlib
import logging
import threading
import time
from PIL import Image

from logger import Logger

logger = Logger(name="epd_manager.py", level=logging.INFO)

DEBUG_MANAGER = False


def debug_log(message, level="debug"):
    if not DEBUG_MANAGER:
        return
    if level == "info":
        logger.info(f"[EPD_MANAGER] {message}")
    elif level == "warning":
        logger.warning(f"[EPD_MANAGER] {message}")
    elif level == "error":
        logger.error(f"[EPD_MANAGER] {message}")
    else:
        logger.debug(f"[EPD_MANAGER] {message}")


class EPDManager:
    _instance = None
    _instance_lock = threading.Lock()
    _spi_lock = threading.RLock()

    MAX_CONSECUTIVE_ERRORS = 3
    RESET_COOLDOWN = 5.0

    def __new__(cls, epd_type: str):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, epd_type: str):
        if self._initialized:
            if epd_type != self.epd_type:
                logger.warning(
                    f"EPDManager already initialized with {self.epd_type}, "
                    f"ignoring requested type {epd_type}"
                )
            return

        self.epd_type = epd_type
        self.epd = None
        self.last_reset = time.time()
        self.error_count = 0
        self.last_error_time = 0.0
        self.total_operations = 0
        self.successful_operations = 0
        self.last_operation_duration = 0.0
        self.total_operation_duration = 0.0
        self.timeout_count = 0
        self.recovery_attempts = 0
        self.recovery_failures = 0

        self._load_driver()
        self._initialized = True

    # ------------------------------------------------------------------ driver

    def _load_driver(self):
        debug_log(f"Loading EPD driver {self.epd_type}", "info")
        epd_module_name = f"resources.waveshare_epd.{self.epd_type}"
        epd_module = importlib.import_module(epd_module_name)
        self.epd = epd_module.EPD()

    # ------------------------------------------------------------------ calls

    def _safe_call(self, func, *args, **kwargs):
        with EPDManager._spi_lock:
            self.total_operations += 1
            started = time.monotonic()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                self.error_count += 1
                self.last_error_time = time.time()
                logger.error(f"EPD operation failed ({func.__name__}): {exc}")

                if self.error_count < self.MAX_CONSECUTIVE_ERRORS:
                    return self._simple_retry(func, args, kwargs, exc)

                return self._perform_recovery(func, args, kwargs, exc)

            self.successful_operations += 1
            self.error_count = 0
            self.last_operation_duration = time.monotonic() - started
            self.total_operation_duration += self.last_operation_duration
            return result

    def _simple_retry(self, func, args, kwargs, original_error):
        time.sleep(0.3)
        try:
            result = func(*args, **kwargs)
            self.successful_operations += 1
            self.error_count = 0
            return result
        except Exception as retry_error:
            logger.error(f"EPD retry failed ({func.__name__}): {retry_error}")
            raise original_error

    def _perform_recovery(self, func, args, kwargs, original_error):
        now = time.time()
        wait_s = max(0.0, self.RESET_COOLDOWN - (now - self.last_reset))
        if wait_s > 0:
            time.sleep(wait_s)

        self.recovery_attempts += 1
        try:
            self.hard_reset()
            result = func(*args, **kwargs)
            self.successful_operations += 1
            self.error_count = 0
            return result
        except Exception as exc:
            self.recovery_failures += 1
            logger.critical(f"EPD recovery failed: {exc}")
            self.error_count = 0
            raise original_error

    # -------------------------------------------------------------- public api

    def init_full_update(self):
        return self._safe_call(self._init_full)

    def init_partial_update(self):
        return self._safe_call(self._init_partial)

    def display_partial(self, image):
        return self._safe_call(self._display_partial, image)

    def display_full(self, image):
        return self._safe_call(self._display_full, image)

    def clear(self):
        return self._safe_call(self._clear)

    def sleep(self):
        return self._safe_call(self._sleep)

    def check_health(self):
        uptime = time.time() - self.last_reset
        success_rate = 100.0
        avg_ms = 0.0

        if self.total_operations > 0:
            success_rate = (self.successful_operations / self.total_operations) * 100.0
            avg_ms = (self.total_operation_duration / self.total_operations) * 1000.0

        return {
            "uptime_seconds": round(uptime, 3),
            "total_operations": int(self.total_operations),
            "successful_operations": int(self.successful_operations),
            "success_rate": round(success_rate, 2),
            "consecutive_errors": int(self.error_count),
            "timeout_count": int(self.timeout_count),
            "last_reset": self.last_reset,
            "last_operation_duration_ms": round(self.last_operation_duration * 1000.0, 2),
            "avg_operation_duration_ms": round(avg_ms, 2),
            "recovery_attempts": int(self.recovery_attempts),
            "recovery_failures": int(self.recovery_failures),
            "is_healthy": self.error_count == 0,
        }

    # ------------------------------------------------------------- impl methods

    def _init_full(self):
        if hasattr(self.epd, "FULL_UPDATE"):
            self.epd.init(self.epd.FULL_UPDATE)
        elif hasattr(self.epd, "lut_full_update"):
            self.epd.init(self.epd.lut_full_update)
        else:
            self.epd.init()

    def _init_partial(self):
        if hasattr(self.epd, "PART_UPDATE"):
            self.epd.init(self.epd.PART_UPDATE)
        elif hasattr(self.epd, "lut_partial_update"):
            self.epd.init(self.epd.lut_partial_update)
        else:
            self.epd.init()

    def _display_partial(self, image):
        if hasattr(self.epd, "displayPartial"):
            self.epd.displayPartial(self.epd.getbuffer(image))
        else:
            self.epd.display(self.epd.getbuffer(image))

    def _display_full(self, image):
        self.epd.display(self.epd.getbuffer(image))

    def _clear(self):
        if hasattr(self.epd, "Clear"):
            self.epd.Clear()
            return

        w, h = self.epd.width, self.epd.height
        blank = Image.new("1", (w, h), 255)
        try:
            self._display_partial(blank)
        finally:
            blank.close()

    def _sleep(self):
        if hasattr(self.epd, "sleep"):
            self.epd.sleep()

    def hard_reset(self, force: bool = False):
        with EPDManager._spi_lock:
            started = time.monotonic()
            try:
                if self.epd and hasattr(self.epd, "epdconfig"):
                    try:
                        self.epd.epdconfig.module_exit(cleanup=True)
                    except TypeError:
                        self.epd.epdconfig.module_exit()
                    except Exception as exc:
                        logger.warning(f"EPD module_exit during reset failed: {exc}")

                self._load_driver()

                # Validate the new driver with a full init.
                if hasattr(self.epd, "FULL_UPDATE"):
                    self.epd.init(self.epd.FULL_UPDATE)
                else:
                    self.epd.init()

                self.last_reset = time.time()
                self.error_count = 0
                if force:
                    logger.warning(
                        f"EPD forced hard reset completed in {time.monotonic() - started:.2f}s"
                    )
                else:
                    logger.warning(
                        f"EPD hard reset completed in {time.monotonic() - started:.2f}s"
                    )
            except Exception as exc:
                logger.critical(f"EPD hard reset failed: {exc}")
                raise
