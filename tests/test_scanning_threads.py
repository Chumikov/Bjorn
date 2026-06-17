"""SCN-1, SCN-2: scanning.py thread-join and hostname-once fixes.

SCN-1: PortScanner.start() and ScanPorts.scan_network_and_write_to_csv()
spawned threads without joining them. The caller read self.open_ports
while threads were still running (race). The second location used
time.sleep(5) as a "wait" — replaced with explicit thread joining.

SCN-2: scan_host() called self.outer_instance.nm[ip].hostname() twice in
a ternary expression. Cached into a single call.
"""
import socket
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# SCN-1
# ---------------------------------------------------------------------------


class TestScanningThreadJoins:
    def test_no_time_sleep_5_in_scanning(self):
        """The fixed-time busy-wait hack must be gone."""
        with open("actions/scanning.py", encoding="utf-8") as f:
            src = f.read()
        assert "time.sleep(5)" not in src, (
            "scanning.py must not use the fixed 5s busy-wait — replaced with "
            "thread.join().")

    def test_start_collects_and_joins_threads(self):
        """Source-level: PortScanner.start() must collect + join threads."""
        with open("actions/scanning.py", encoding="utf-8") as f:
            src = f.read()
        assert "threads = []" in src or "threads.append" in src, (
            "scanning.py must collect spawned threads into a list.")
        assert "t.join()" in src or "t.join(timeout" in src, (
            "scanning.py must join spawned threads before returning.")

    def test_open_ports_complete_after_start_returns(self):
        """Behavioral: when start() returns, all scan threads must have
        finished invoking scan_with_semaphore for each port."""
        sys.modules.pop("actions.scanning", None)
        from actions import scanning as scanning_mod

        called_ports = []
        outer = MagicMock()
        outer.semaphore = threading.Semaphore(20)

        ps = scanning_mod.NetworkScanner.PortScanner.__new__(
            scanning_mod.NetworkScanner.PortScanner)
        ps.outer_instance = outer
        ps.portstart = 1
        ps.portend = 10
        ps.extra_ports = [80, 443]
        ps.logger = MagicMock()
        ps.scan_with_semaphore = lambda port: called_ports.append(port)

        ps.start()

        expected = sorted([1, 2, 3, 4, 5, 6, 7, 8, 9, 80, 443])
        assert sorted(called_ports) == expected, (
            f"Not all ports scanned when start() returned: "
            f"got {sorted(called_ports)}, expected {expected}")

    def test_scan_network_joins_threads(self):
        """Source-level: scan_network_and_write_to_csv must collect threads
        and call join() before sort_and_write_csv."""
        with open("actions/scanning.py", encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if "def scan_network_and_write_to_csv" in line:
                body = "".join(lines[i:i+30])
                assert "threads = []" in body or "threads.append" in body, (
                    "scan_network_and_write_to_csv must collect threads.")
                join_pos = body.find("t.join")
                sort_pos = body.find("sort_and_write_csv")
                assert join_pos != -1 and sort_pos != -1, (
                    f"Could not find join/sort calls in method body:\n{body}")
                assert join_pos < sort_pos, (
                    "join() must come before sort_and_write_csv so the CSV "
                    "contains all hosts. Body:\n" + body)
                return
        pytest.fail("scan_network_and_write_to_csv method not found")


# ---------------------------------------------------------------------------
# SCN-2
# ---------------------------------------------------------------------------


class TestHostnameCalledOnce:
    def test_no_double_hostname_call_in_scan_host(self):
        """The buggy ternary `nm[ip].hostname() if nm[ip].hostname() else ''`
        must be replaced with `nm[ip].hostname() or ''`."""
        with open("actions/scanning.py", encoding="utf-8") as f:
            src = f.read()
        assert ".hostname() if" not in src, (
            "scan_host must not call .hostname() twice (SCN-2). "
            "Found 'X.hostname() if X.hostname() else' pattern.")

    def test_hostname_called_once_behavioral(self):
        """Mock nm[ip].hostname and assert it's called once per host."""
        sys.modules.pop("actions.scanning", None)
        from actions import scanning as scanning_mod

        sp = scanning_mod.NetworkScanner.ScanPorts.__new__(
            scanning_mod.NetworkScanner.ScanPorts)

        outer = MagicMock()
        outer.blacklistcheck = False
        outer.ip_scan_blacklist = []
        outer.mac_scan_blacklist = []
        outer.lock = threading.Lock()
        outer.get_mac_address = MagicMock(return_value="aa:bb:cc:dd:ee:ff")

        sp.outer_instance = outer
        sp.csv_scan_file = "/tmp/test_scan_hosts.csv"
        sp.ip_hostname_list = []
        sp.progress = 0  # scan_host increments this after each host

        hostname_calls = {"count": 0}
        def hostname():
            hostname_calls["count"] += 1
            return "test-host"
        host_mock = MagicMock()
        host_mock.hostname.side_effect = hostname
        outer.nm.__getitem__.return_value = host_mock

        with patch("builtins.open", MagicMock()):
            sp.scan_host("10.0.0.1")

        assert hostname_calls["count"] == 1, (
            f"hostname() should be called exactly once; got "
            f"{hostname_calls['count']}")


# ---------------------------------------------------------------------------
# SCN-3
# ---------------------------------------------------------------------------


class TestNetifacesReplaced:
    def test_no_netifaces_import(self):
        """netifaces must not be imported (replaced by psutil)."""
        with open("actions/scanning.py", encoding="utf-8") as f:
            src = f.read()
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            assert "netifaces" not in line, (
                f"Non-comment reference to netifaces at line {i}: {line!r}")

    def test_psutil_imported(self):
        with open("actions/scanning.py", encoding="utf-8") as f:
            src = f.read()
        assert "import psutil" in src, (
            "scanning.py must import psutil (replaces netifaces).")

    def test_get_network_calls_psutil_methods(self):
        """Behavioral: get_network() must invoke psutil.net_if_gateways and
        net_if_addrs (replacing the old netifaces calls)."""
        sys.modules.pop("actions.scanning", None)
        from actions import scanning as scanning_mod

        ns = scanning_mod.NetworkScanner.__new__(scanning_mod.NetworkScanner)
        ns.logger = MagicMock()

        with patch.object(scanning_mod, "psutil") as mock_psutil:
            ipv4_addr = MagicMock()
            ipv4_addr.family = socket.AF_INET
            ipv4_addr.address = "192.168.1.42"
            ipv4_addr.netmask = "255.255.255.0"
            mock_psutil.AF_INET = socket.AF_INET
            mock_psutil.net_if_gateways.return_value = {
                "default": {socket.AF_INET: ("192.168.1.1", "wlan0", True)}
            }
            mock_psutil.net_if_addrs.return_value = {"wlan0": [ipv4_addr]}

            ns.get_network()

            assert mock_psutil.net_if_gateways.called, (
                "get_network() must call psutil.net_if_gateways()")
            assert mock_psutil.net_if_addrs.called, (
                "get_network() must call psutil.net_if_addrs()")
