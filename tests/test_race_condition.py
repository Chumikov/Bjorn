import csv
import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


class TestRaceCondition:
    def _setup_csv(self, mock_shared_data, tmp_path):
        netkb = tmp_path / "netkb.csv"
        actions = tmp_path / "actions.json"
        actions.write_text('[{"b_class": "SSHBruteforce", "b_module": "ssh_connector"}]')
        netkb.write_text(
            "MAC Address,IPs,Hostnames,Alive,Ports,SSHBruteforce\n"
            "aa:bb:cc:dd:ee:01,10.0.0.1,host1,1,22,\n"
            "aa:bb:cc:dd:ee:02,10.0.0.2,host2,1,22,\n"
        )
        mock_shared_data.netkbfile = str(netkb)
        mock_shared_data.actions_file = str(actions)
        mock_shared_data.currentdir = str(tmp_path)
        mock_shared_data.configdir = str(tmp_path)
        mock_shared_data.datadir = str(tmp_path)
        mock_shared_data.actions_dir = str(tmp_path / "actions")
        return netkb

    def _read_raw(self, path):
        with open(path, 'r') as f:
            return f.read()

    def test_concurrent_writes_do_not_lose_data(self, mock_shared_data, tmp_path):
        netkb = self._setup_csv(mock_shared_data, tmp_path)

        sys_modules = {}
        import sys
        sys.modules.pop('shared', None)

        from shared import SharedData

        with patch.object(SharedData, '__init__', lambda self: None):
            sd = SharedData.__new__(SharedData)
            sd.netkbfile = str(netkb)
            sd.actions_file = str(tmp_path / "actions.json")
            sd.currentdir = str(tmp_path)
            sd.configdir = str(tmp_path)
            sd.datadir = str(tmp_path)
            sd.actions_dir = str(tmp_path / "actions")

        errors = []

        def writer(action_key, value, mac):
            try:
                data = sd.read_data()
                time.sleep(0.01)
                for row in data:
                    if row["MAC Address"] == mac:
                        row[action_key] = value
                sd.write_data(data)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer, args=("SSHBruteforce", "success_t1", "aa:bb:cc:dd:ee:01"))
        t2 = threading.Thread(target=writer, args=("SSHBruteforce", "success_t2", "aa:bb:cc:dd:ee:02"))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert not errors, f"Errors during concurrent writes: {errors}"

        content = self._read_raw(netkb)
        assert "success_t1" in content, "Thread 1 result lost — race condition"
        assert "success_t2" in content, "Thread 2 result lost — race condition"

    def test_concurrent_read_write_no_empty_file(self, mock_shared_data, tmp_path):
        netkb = self._setup_csv(mock_shared_data, tmp_path)

        sys_modules = {}
        import sys
        sys.modules.pop('shared', None)

        from shared import SharedData

        with patch.object(SharedData, '__init__', lambda self: None):
            sd = SharedData.__new__(SharedData)
            sd.netkbfile = str(netkb)
            sd.actions_file = str(tmp_path / "actions.json")
            sd.currentdir = str(tmp_path)
            sd.configdir = str(tmp_path)
            sd.datadir = str(tmp_path)
            sd.actions_dir = str(tmp_path / "actions")

        empty_reads = []

        def reader():
            for _ in range(50):
                data = sd.read_data()
                if len(data) == 0:
                    empty_reads.append(True)
                time.sleep(0.002)

        def writer():
            for i in range(50):
                data = sd.read_data()
                for row in data:
                    row["SSHBruteforce"] = f"attempt_{i}"
                sd.write_data(data)
                time.sleep(0.002)

        tr = threading.Thread(target=reader)
        tw = threading.Thread(target=writer)
        tr.start()
        tw.start()
        tr.join(timeout=10)
        tw.join(timeout=10)

        assert len(empty_reads) == 0, f"Read returned empty data {len(empty_reads)} times during concurrent write"

    def test_data_lock_exists(self, mock_shared_data):
        import sys
        sys.modules.pop('shared', None)
        from shared import SharedData

        with patch.object(SharedData, '__init__', lambda self: None):
            sd = SharedData.__new__(SharedData)
            assert hasattr(sd, '_data_lock'), "SharedData should have _data_lock attribute"
            assert isinstance(sd._data_lock, type(threading.RLock())), "_data_lock should be an RLock"
