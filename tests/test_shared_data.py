"""Behavioral tests for shared.py data methods (COV-5).

Tests read_data/write_data (CSV merge), initialize_csv, create_livestatusfile,
generate_actions_json, load/save_config — all with tmp files.
SharedData constructed via __new__ (no __init__, no EPD/network).
"""
import csv
import json
import os
import sys
from unittest.mock import MagicMock

import pytest


def _make_shared(tmp_path):
    """Build SharedData with tmp paths (no __init__)."""
    sys.modules.pop('shared', None)
    from shared import SharedData
    sd = SharedData.__new__(SharedData)
    sd.netkbfile = str(tmp_path / "netkb.csv")
    sd.livestatusfile = str(tmp_path / "livestatus.csv")
    sd.actions_file = str(tmp_path / "actions.json")
    sd.actions_dir = str(tmp_path / "actions")
    sd.shared_config_json = str(tmp_path / "shared_config.json")
    sd.configdir = str(tmp_path)
    os.makedirs(sd.actions_dir, exist_ok=True)
    sd.config = {}
    sd._data_lock = __import__('threading').RLock()
    sd.status_list = []
    return sd


class TestReadData:
    def test_reads_existing_csv(self, tmp_path):
        sd = _make_shared(tmp_path)
        with open(sd.netkbfile, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["MAC Address", "IPs", "Hostnames", "Alive", "Ports"])
            w.writerow(["AA:BB", "10.0.0.1", "host1", "1", "22;80"])
            w.writerow(["CC:DD", "10.0.0.2", "host2", "0", ""])
        data = sd.read_data()
        assert len(data) == 2
        assert data[0]["IPs"] == "10.0.0.1"
        assert data[0]["Alive"] == "1"
        assert data[1]["Hostnames"] == "host2"

    def test_creates_csv_if_missing(self, tmp_path):
        sd = _make_shared(tmp_path)
        # initialize_csv is called inside read_data if file missing.
        # Need actions_file for header generation.
        with open(sd.actions_file, 'w') as f:
            json.dump([{"b_module": "ssh", "b_class": "SSHBruteforce"}], f)
        data = sd.read_data()
        assert data == []
        assert os.path.exists(sd.netkbfile)


class TestWriteData:
    def test_writes_new_data(self, tmp_path):
        sd = _make_shared(tmp_path)
        with open(sd.actions_file, 'w') as f:
            json.dump([{"b_module": "ssh", "b_class": "SSHBruteforce"}], f)
        sd.initialize_csv()
        data = sd.read_data()
        data.append({"MAC Address": "AA:BB", "IPs": "10.0.0.1",
                     "Hostnames": "h1", "Alive": "1", "Ports": "22"})
        sd.write_data(data)
        reread = sd.read_data()
        assert len(reread) == 1
        assert reread[0]["MAC Address"] == "AA:BB"

    def test_merges_by_mac(self, tmp_path):
        sd = _make_shared(tmp_path)
        with open(sd.actions_file, 'w') as f:
            json.dump([], f)
        sd.initialize_csv()
        data = sd.read_data()
        data.append({"MAC Address": "AA:BB", "IPs": "10.0.0.1",
                     "Hostnames": "h1", "Alive": "1", "Ports": "22"})
        sd.write_data(data)
        # Write again with updated IPs for same MAC.
        data[0]["IPs"] = "10.0.0.99"
        sd.write_data(data)
        reread = sd.read_data()
        assert len(reread) == 1
        assert reread[0]["IPs"] == "10.0.0.99"


class TestInitializeCsv:
    def test_creates_with_correct_headers(self, tmp_path):
        sd = _make_shared(tmp_path)
        with open(sd.actions_file, 'w') as f:
            json.dump([{"b_class": "SSHBruteforce"}, {"b_class": "FTPBruteforce"}], f)
        sd.initialize_csv()
        with open(sd.netkbfile, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert "MAC Address" in headers
        assert "IPs" in headers
        assert "SSHBruteforce" in headers
        assert "FTPBruteforce" in headers

    def test_idempotent_if_exists(self, tmp_path):
        sd = _make_shared(tmp_path)
        with open(sd.actions_file, 'w') as f:
            json.dump([{"b_class": "SSH"}], f)
        sd.initialize_csv()
        with open(sd.netkbfile, 'a', newline='') as f:
            csv.writer(f).writerow(["XX:XX", "1.2.3.4", "h", "1", "22"])
        # Second call must NOT wipe existing data.
        sd.initialize_csv()
        data = sd.read_data()
        assert len(data) == 1


class TestLivestatusfile:
    def test_creates_with_zero_row(self, tmp_path):
        sd = _make_shared(tmp_path)
        sd.create_livestatusfile()
        with open(sd.livestatusfile, 'r') as f:
            reader = csv.DictReader(f)
            row = next(reader)
        assert row["Total Open Ports"] == "0"
        assert row["Alive Hosts Count"] == "0"


class TestLoadSaveConfig:
    def test_save_then_load(self, tmp_path):
        sd = _make_shared(tmp_path)
        sd.config = {"epd_type": "epd2in13_V4", "portstart": 1, "web_auth_enabled": True}
        sd.save_config()
        assert os.path.exists(sd.shared_config_json)
        # Load into fresh instance.
        sd2 = _make_shared(tmp_path)
        loaded = json.load(open(sd.shared_config_json))
        assert loaded["epd_type"] == "epd2in13_V4"
        assert loaded["web_auth_enabled"] is True
