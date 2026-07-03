"""PORT-2: EPDManager — singleton EPD wrapper with SPI RLock + circuit breaker.

Behavioral tests of the manager logic. The real Waveshare driver is stubbed
(stub _load_driver to inject a fake ``self.epd``) so no hardware / import
chain is needed. Real SPI/GPIO contention and hard_reset recovery can ONLY
be validated on an RPi — those are covered by the mandatory hardware session.
"""
import sys
import threading
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def epd_manager_module(monkeypatch):
    """Import the REAL epd_manager module (bypass conftest's module mock),
    and reset the singleton + stub the driver loader for isolation."""
    sys.modules.pop('epd_manager', None)
    import epd_manager
    # Reset the class-level singleton between tests.
    monkeypatch.setattr(epd_manager.EPDManager, "_instance", None)
    monkeypatch.setattr(epd_manager.time, "sleep", lambda *_a, **_k: None)
    return epd_manager


def _new_manager(epd_manager_module, epd_mock=None):
    """Construct an EPDManager without touching the waveshare import chain."""
    epd_mock = epd_mock or MagicMock()
    epd_mock.width = 122
    epd_mock.height = 250

    orig_init = epd_manager_module.EPDManager.__init__

    def patched_init(self, epd_type):
        # Run the real __init__ but intercept _load_driver.
        self._load_driver = lambda: setattr(self, "epd", epd_mock)
        orig_init(self, epd_type)

    epd_manager_module.EPDManager.__init__ = patched_init
    try:
        mgr = epd_manager_module.EPDManager("epd2in13_V4")
    finally:
        epd_manager_module.EPDManager.__init__ = orig_init
    return mgr, epd_mock


class TestSingleton:
    def test_same_type_returns_same_instance(self, epd_manager_module):
        a, _ = _new_manager(epd_manager_module)
        # Second construction with same type must not re-init.
        b, _ = _new_manager(epd_manager_module)
        assert a is b, "EPDManager must be a singleton (same instance)."

    def test_different_type_keeps_first_instance(self, epd_manager_module):
        a, _ = _new_manager(epd_manager_module)
        # Force a second construction attempt with a different type.
        epd_manager_module.EPDManager("epd2in7")
        assert a is epd_manager_module.EPDManager._instance, (
            "A different epd_type on the second construction must NOT replace "
            "the existing singleton.")


class TestSafeCall:
    def test_success_increments_counters(self, epd_manager_module):
        mgr, epd = _new_manager(epd_manager_module)
        mgr.display_partial(MagicMock())
        assert epd.displayPartial.called
        assert mgr.total_operations == 1
        assert mgr.successful_operations == 1
        assert mgr.error_count == 0

    def test_retry_after_transient_failure(self, epd_manager_module):
        # displayPartial fails once, then succeeds on the 0.3s retry.
        epd = MagicMock()
        epd.width, epd.height = 122, 250
        epd.getbuffer.return_value = b"x"
        calls = {"n": 0}

        def flaky(buf):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient SPI glitch")
            return None

        epd.displayPartial.side_effect = flaky
        mgr, _ = _new_manager(epd_manager_module, epd)
        mgr.display_partial(MagicMock())  # should retry and succeed
        assert calls["n"] == 2, "Transient failure must trigger one retry."
        assert mgr.successful_operations == 1
        assert mgr.error_count == 0, "Successful retry must reset error_count."

    def test_check_health_shape(self, epd_manager_module):
        mgr, _ = _new_manager(epd_manager_module)
        mgr.display_partial(MagicMock())
        health = mgr.check_health()
        assert health["total_operations"] == 1
        assert health["successful_operations"] == 1
        assert health["success_rate"] == 100.0
        assert health["is_healthy"] is True


class TestSpiLock:
    def test_spi_lock_is_an_rlock(self, epd_manager_module):
        # RLock allows reentrant locking from the same thread — required so
        # _perform_recovery (which calls hard_reset, itself taking _spi_lock)
        # doesn't deadlock.
        assert isinstance(epd_manager_module.EPDManager._spi_lock,
                          type(threading.RLock()))
