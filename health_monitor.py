"""health_monitor.py - Runtime health logging (PORT-5).

A daemon thread that periodically logs the signals needed to diagnose the
v1.3.x ``OSError: [Errno 24] Too many open files`` exhaustion and memory
leaks: thread count, RSS memory, and open-FD count. EPD telemetry from
``EPDManager.check_health()`` (PORT-2) is included when available.

DEGRADED vs upstream/ai: queue counts (``action_queue`` pending/running)
require SQLite (MIGR-1, v2.0.0) and are omitted here; the high-value
thread/RSS/FD signals are dependency-free. Uses plain ``logger.info/error``
(this fork's Logger has no ``error_throttled``).
"""
import os
import threading
import logging

from logger import Logger

logger = Logger(name="health_monitor.py", level=logging.INFO)

_DEFAULT_INTERVAL_S = 60


class HealthMonitor(threading.Thread):
    """Periodically logs runtime health (threads / RSS / FDs / EPD stats)."""

    def __init__(self, shared_data, interval_s=None):
        super().__init__(name="HealthMonitor", daemon=True)
        self.shared_data = shared_data
        cfg_interval = None
        try:
            cfg_interval = shared_data.config.get("health_monitor_interval_s")
        except AttributeError:
            cfg_interval = None
        self.interval_s = int(interval_s if interval_s is not None
                              else (cfg_interval or _DEFAULT_INTERVAL_S))
        self._stop_event = threading.Event()

    def run(self):
        logger.info(f"HealthMonitor started (interval={self.interval_s}s).")
        # First report quickly so health is visible right after startup
        # instead of after a full interval.
        self._report()
        while not self._stop_event.wait(self.interval_s):
            self._report()
        logger.info("HealthMonitor stopped.")

    def stop(self):
        self._stop_event.set()

    def _report(self):
        try:
            thread_count = threading.active_count()
            rss_kb = self._rss_kb()
            fd_count = self._fd_count()
            epd = self._epd_metrics()
            logger.info(
                "health "
                f"thread_count={thread_count} "
                f"rss_kb={rss_kb} "
                f"fd_count={fd_count} "
                f"epd_errors={epd.get('consecutive_errors', 'n/a')} "
                f"epd_success_rate={epd.get('success_rate', 'n/a')}"
            )
        except Exception as exc:  # noqa: broad-except — monitor must never kill the service
            logger.error(f"Health monitor report error: {exc}")

    # -------------------------------------------------------------- metric helpers

    def _rss_kb(self):
        """Resident set size in KB from /proc/self/status (no psutil)."""
        try:
            with open("/proc/self/status", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1])
        except (OSError, ValueError, IndexError):
            return -1
        return -1

    def _fd_count(self):
        """Number of open file descriptors via /proc/self/fd."""
        try:
            return len(os.listdir("/proc/self/fd"))
        except OSError:
            return -1

    def _epd_metrics(self):
        """EPDManager.check_health() if an EPDManager (PORT-2) is attached."""
        mgr = getattr(self.shared_data, "epd_helper", None)
        if mgr is None or not hasattr(mgr, "check_health"):
            return {}
        try:
            return mgr.check_health()
        except Exception:  # noqa: broad-except
            return {}
