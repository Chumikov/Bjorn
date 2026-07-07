"""Behavioral tests for utils.py data-serving endpoints (COV-2).

Tests the HTTP endpoints that serve CSV data as HTML/JSON: serve_netkb_data,
serve_network_data, serve_credentials_data, serve_current_config, list_files.
Uses the custom_handler_server fixture (real HTTPServer + CustomHandler).
"""
import csv
import json
import os
import urllib.request
import urllib.error

import pytest


def _write_netkb(path, rows=None):
    """Write a netkb.csv with headers + optional rows."""
    headers = ["MAC Address", "IPs", "Hostnames", "Alive", "Ports", "SSHBruteforce"]
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in (rows or []):
            w.writerow(row)


class TestNetkbDataEndpoint:
    def test_netkb_data_returns_200(self, custom_handler_server, tmp_path):
        """GET /netkb_data returns 200 with HTML table content."""
        sd = custom_handler_server["shared"]
        sd.netkbfile = str(tmp_path / "netkb.csv")
        _write_netkb(sd.netkbfile, [
            ["AA:BB", "10.0.0.1", "host1", "1", "22", ""],
            ["CC:DD", "10.0.0.2", "host2", "0", "", ""],
        ])
        req = urllib.request.Request(
            f"{custom_handler_server['base_url']}/netkb_data")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode()
            assert "10.0.0.1" in body  # alive host shown
            assert "host1" in body

    def test_netkb_data_json_returns_200(self, custom_handler_server):
        """GET /netkb_data_json returns 200 with JSON."""
        req = urllib.request.Request(
            f"{custom_handler_server['base_url']}/netkb_data_json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read())
            assert "ips" in data or "actions" in data or isinstance(data, dict)


class TestNetworkDataEndpoint:
    def test_network_data_returns_200(self, custom_handler_server, tmp_path):
        """GET /network_data returns 200."""
        # network_data reads latest scan_results/result_*.csv
        scan_dir = str(tmp_path / "scan_results")
        os.makedirs(scan_dir, exist_ok=True)
        custom_handler_server["shared"].scan_results_dir = scan_dir
        result_file = os.path.join(scan_dir, "result_192_168_1_0_24.csv")
        with open(result_file, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["IP", "Hostname", "Alive", "MAC Address", "22", "80"])
            w.writerow(["10.0.0.1", "host1", "1", "AA:BB", "22", ""])
        req = urllib.request.Request(
            f"{custom_handler_server['base_url']}/network_data")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200


class TestCredentialsDataEndpoint:
    def test_list_credentials_returns_200(self, custom_handler_server, tmp_path):
        """GET /list_credentials returns 200."""
        cracked_dir = str(tmp_path / "crackedpwd")
        os.makedirs(cracked_dir, exist_ok=True)
        custom_handler_server["shared"].crackedpwddir = cracked_dir
        # Write a minimal credentials CSV.
        with open(os.path.join(cracked_dir, "ssh.csv"), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["MAC Address", "IP Address", "Hostname", "User", "Password", "Port"])
            w.writerow(["AA:BB", "10.0.0.1", "host1", "root", "12345", "22"])
        req = urllib.request.Request(
            f"{custom_handler_server['base_url']}/list_credentials")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode()
            assert "root" in body or "10.0.0.1" in body


class TestConfigEndpoints:
    def test_load_config_returns_json(self, custom_handler_server):
        """GET /load_config returns JSON config."""
        req = urllib.request.Request(
            f"{custom_handler_server['base_url']}/load_config")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read())
            assert isinstance(data, dict)

    def test_restore_default_config_returns_200(self, custom_handler_server):
        """GET /restore_default_config responds."""
        req = urllib.request.Request(
            f"{custom_handler_server['base_url']}/restore_default_config")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200


class TestListFilesEndpoint:
    def test_list_files_returns_json(self, custom_handler_server, tmp_path):
        """GET /list_files returns JSON tree."""
        stolen_dir = str(tmp_path / "data_stolen")
        os.makedirs(stolen_dir, exist_ok=True)
        # Create a test file.
        with open(os.path.join(stolen_dir, "test.txt"), 'w') as f:
            f.write("test")
        custom_handler_server["shared"].datastolendir = stolen_dir
        req = urllib.request.Request(
            f"{custom_handler_server['base_url']}/list_files")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read())
            assert isinstance(data, list)
            # Should contain the test.txt file.
            names = [f.get("name") for f in data]
            assert "test.txt" in names
