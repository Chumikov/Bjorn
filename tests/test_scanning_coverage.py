"""Behavioral tests for scanning.py (COV-4).

Tests update_netkb merge logic, LiveStatusUpdater, sort_and_write_csv,
GetIpFromCsv — the CSV manipulation parts of the scanner that are most
bug-prone and fully testable without real nmap.
"""
import csv
import os
import sys
from unittest.mock import MagicMock

import pytest


def _make_scanner(tmp_path):
    """Build a NetworkScanner with tmp paths (no real nmap)."""
    sys.modules.pop('actions.scanning', None)
    from actions.scanning import NetworkScanner
    ns = NetworkScanner.__new__(NetworkScanner)
    sd = MagicMock()
    sd.netkbfile = str(tmp_path / "netkb.csv")
    sd.livestatusfile = str(tmp_path / "livestatus.csv")
    sd.scan_results_dir = str(tmp_path / "scan_results")
    sd.mac_scan_blacklist = []
    sd.ip_scan_blacklist = []
    sd.blacklistcheck = False
    os.makedirs(sd.scan_results_dir, exist_ok=True)
    ns.shared_data = sd
    ns.logger = MagicMock()
    ns.blacklistcheck = False
    ns.mac_scan_blacklist = []
    ns.ip_scan_blacklist = []
    ns.lock = __import__('threading').Lock()
    ns.displaying_csv = False
    return ns


def _write_netkb(path, rows=None, action_cols=None):
    headers = ["MAC Address", "IPs", "Hostnames", "Alive", "Ports"]
    if action_cols:
        headers += action_cols
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in (rows or []):
            w.writerow(r)


class TestUpdateNetkb:
    def test_adds_new_host(self, tmp_path):
        ns = _make_scanner(tmp_path)
        _write_netkb(ns.shared_data.netkbfile)
        netkb_data = [
            ("AA:BB:CC:DD:EE:01", "10.0.0.1", "host1", [22, 80]),
        ]
        alive_macs = {"AA:BB:CC:DD:EE:01"}
        ns.update_netkb(ns.shared_data.netkbfile, netkb_data, alive_macs)
        with open(ns.shared_data.netkbfile, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["MAC Address"] == "AA:BB:CC:DD:EE:01"
        assert "10.0.0.1" in rows[0]["IPs"]
        assert rows[0]["Alive"] == "1"
        assert "22" in rows[0]["Ports"]

    def test_marks_missing_host_as_dead(self, tmp_path):
        ns = _make_scanner(tmp_path)
        _write_netkb(ns.shared_data.netkbfile, [
            ["AA:BB", "10.0.0.1", "h1", "1", "22"],
        ])
        # Empty scan → old host should be marked Alive=0.
        ns.update_netkb(ns.shared_data.netkbfile, [], set())
        with open(ns.shared_data.netkbfile, 'r') as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["Alive"] == "0"

    def test_updates_existing_host_ports(self, tmp_path):
        ns = _make_scanner(tmp_path)
        _write_netkb(ns.shared_data.netkbfile, [
            ["AA:BB", "10.0.0.1", "h1", "1", "22"],
        ])
        ns.update_netkb(ns.shared_data.netkbfile,
                        [("AA:BB", "10.0.0.1", "h1", [80, 443])],
                        {"AA:BB"})
        with open(ns.shared_data.netkbfile, 'r') as f:
            rows = list(csv.DictReader(f))
        assert "22" in rows[0]["Ports"]  # old port preserved
        assert "80" in rows[0]["Ports"]  # new port added
        assert "443" in rows[0]["Ports"]

    def test_skips_standalone_and_zero_mac(self, tmp_path):
        ns = _make_scanner(tmp_path)
        _write_netkb(ns.shared_data.netkbfile)
        ns.update_netkb(ns.shared_data.netkbfile,
                        [("STANDALONE", "x", "x", []),
                         ("00:00:00:00:00:00", "10.0.0.1", "h", [22])],
                        set())
        with open(ns.shared_data.netkbfile, 'r') as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 0  # both skipped


class TestLiveStatusUpdater:
    def test_updates_livestatus_from_netkb(self, tmp_path):
        from actions.scanning import NetworkScanner
        ns = _make_scanner(tmp_path)
        _write_netkb(ns.shared_data.netkbfile, [
            ["AA:BB", "10.0.0.1", "h1", "1", "22;80"],
            ["CC:DD", "10.0.0.2", "h2", "0", ""],
            ["STANDALONE", "x", "x", "0", ""],
        ])
        with open(ns.shared_data.livestatusfile, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["Total Open Ports", "Alive Hosts Count",
                        "All Known Hosts Count", "Vulnerabilities Count"])
            w.writerow(["0", "0", "0", "0"])
        updater = NetworkScanner.LiveStatusUpdater(
            ns.shared_data.netkbfile, ns.shared_data.livestatusfile)
        updater.update_livestatus()
        with open(ns.shared_data.livestatusfile, 'r') as f:
            row = next(csv.DictReader(f))
        assert int(row["Alive Hosts Count"]) == 1
        assert int(row["All Known Hosts Count"]) == 2
