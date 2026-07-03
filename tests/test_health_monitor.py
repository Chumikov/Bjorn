"""PORT-5: HealthMonitor runtime telemetry.

Behavioral: the metric helpers read real /proc on Linux, and the thread
starts/reports/stops cleanly. Queue counts (SQLite) are intentionally
absent (degraded mode) — that's covered by the v2.0.0 migration.
"""
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

import health_monitor
from health_monitor import HealthMonitor


def _shared(interval=None, with_epd=False):
    sd = MagicMock()
    sd.config = {} if interval is None else {"health_monitor_interval_s": interval}
    if with_epd:
        sd.epd_helper.check_health.return_value = {
            "consecutive_errors": 0, "success_rate": 100.0}
    else:
        sd.epd_helper = None
    return sd


class TestMetricHelpers:
    @pytest.mark.skipif(sys.platform == "win32", reason="/proc unavailable on Windows")
    def test_rss_kb_returns_positive_int(self):
        hm = HealthMonitor(_shared())
        rss = hm._rss_kb()
        assert isinstance(rss, int) and rss > 0, (
            f"RSS must be a positive int from /proc/self/status; got {rss}.")

    @pytest.mark.skipif(sys.platform == "win32", reason="/proc unavailable on Windows")
    def test_fd_count_returns_positive_int(self):
        hm = HealthMonitor(_shared())
        fd = hm._fd_count()
        assert isinstance(fd, int) and fd > 0, (
            f"FD count must be a positive int from /proc/self/fd; got {fd}.")

    def test_epd_metrics_empty_without_manager(self):
        hm = HealthMonitor(_shared(with_epd=False))
        assert hm._epd_metrics() == {}

    def test_epd_metrics_from_manager(self):
        hm = HealthMonitor(_shared(with_epd=True))
        m = hm._epd_metrics()
        assert m["success_rate"] == 100.0
        assert m["consecutive_errors"] == 0


class TestIntervalConfig:
    def test_default_interval(self):
        hm = HealthMonitor(_shared())
        assert hm.interval_s == 60

    def test_interval_from_config(self):
        hm = HealthMonitor(_shared(interval=15))
        assert hm.interval_s == 15

    def test_interval_explicit_override(self):
        hm = HealthMonitor(_shared(interval=15), interval_s=5)
        assert hm.interval_s == 5


class TestLifecycle:
    def test_start_report_stop_exits_cleanly(self):
        hm = HealthMonitor(_shared(), interval_s=60)
        hm.start()
        # The first report happens immediately on run(); give it a moment.
        time.sleep(0.3)
        assert hm.is_alive(), "HealthMonitor thread should be running."
        hm.stop()
        hm.join(timeout=5)
        assert not hm.is_alive(), (
            "stop() must release the wait() so the daemon thread exits.")

    def test_stop_without_start_is_noop(self):
        hm = HealthMonitor(_shared())
        hm.stop()  # must not raise

    def test_is_daemon(self):
        hm = HealthMonitor(_shared())
        # Daemon so it never blocks process exit (per AGENTS.md, only core
        # workers like bjorn_thread are non-daemon).
        assert hm.daemon is True
