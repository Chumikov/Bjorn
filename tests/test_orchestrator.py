"""Behavioral tests for orchestrator.py — the core scheduling/execution logic.

Tests the action lifecycle: port matching, parent-child dependencies,
retry delays (success/failed), actual execution + write_data, standalone
actions. The Orchestrator is constructed via __new__ (bypassing load_actions
which imports real action modules); mock actions are injected directly.
"""
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


def _make_orchestrator(actions=None, standalone=None, shared_data=None):
    """Build an Orchestrator without load_actions (no real module imports)."""
    from orchestrator import Orchestrator
    orch = Orchestrator.__new__(Orchestrator)
    orch.shared_data = shared_data or MagicMock()
    orch.shared_data.retry_success_actions = False
    orch.shared_data.failed_retry_delay = 600
    orch.shared_data.success_retry_delay = 900
    orch.actions = actions or []
    orch.standalone_actions = standalone or []
    orch.semaphore = threading.Semaphore(10)
    orch.failed_scans_count = 0
    return orch


def _mock_action(name="SSHBruteforce", port=22, parent=None, result="success"):
    a = MagicMock()
    a.action_name = name
    a.port = port
    a.b_parent_action = parent
    a.execute.return_value = result
    return a


def _alive_row(ip="192.168.1.10", ports="22;80;445", **action_statuses):
    row = {
        "MAC Address": "AA:BB:CC:DD:EE:FF",
        "IPs": ip,
        "Hostnames": "test",
        "Alive": "1",
        "Ports": ports,
    }
    row.update(action_statuses)
    return row


class TestExecuteAction:
    def test_port_not_matching_skips(self):
        orch = _make_orchestrator()
        action = _mock_action(port=3389)
        row = _alive_row(ports="22;80")
        result = orch.execute_action(action, "192.168.1.10", ["22", "80"], row, "RDPBruteforce", [row])
        assert result is False
        action.execute.assert_not_called()

    def test_parent_not_succeeded_skips(self):
        orch = _make_orchestrator()
        action = _mock_action(name="StealFilesSSH", parent="SSHBruteforce")
        row = _alive_row(SSHBruteforce="failed_20260101_120000")
        result = orch.execute_action(action, "192.168.1.10", ["22"], row, "StealFilesSSH", [row])
        assert result is False
        action.execute.assert_not_called()

    def test_parent_succeeded_executes(self):
        orch = _make_orchestrator()
        action = _mock_action(name="StealFilesSSH", parent="SSHBruteforce", result="success")
        row = _alive_row(SSHBruteforce="success_20260101_120000")
        result = orch.execute_action(action, "192.168.1.10", ["22"], row, "StealFilesSSH", [row])
        assert result is True
        action.execute.assert_called_once()

    def test_success_retry_disabled_skips(self):
        orch = _make_orchestrator()
        orch.shared_data.retry_success_actions = False
        action = _mock_action()
        row = _alive_row(SSHBruteforce="success_20260101_120000")
        result = orch.execute_action(action, "192.168.1.10", ["22"], row, "SSHBruteforce", [row])
        assert result is False
        action.execute.assert_not_called()

    def test_success_retry_enabled_recent_skips(self):
        orch = _make_orchestrator()
        orch.shared_data.retry_success_actions = True
        action = _mock_action()
        now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        row = _alive_row(SSHBruteforce=f"success_{now_ts}")
        result = orch.execute_action(action, "192.168.1.10", ["22"], row, "SSHBruteforce", [row])
        assert result is False
        action.execute.assert_not_called()

    def test_failed_retry_recent_skips(self):
        orch = _make_orchestrator()
        action = _mock_action()
        now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        row = _alive_row(SSHBruteforce=f"failed_{now_ts}")
        result = orch.execute_action(action, "192.168.1.10", ["22"], row, "SSHBruteforce", [row])
        assert result is False
        action.execute.assert_not_called()

    def test_executes_and_writes_success(self):
        orch = _make_orchestrator()
        action = _mock_action(result="success")
        row = _alive_row()
        data = [row]
        result = orch.execute_action(action, "192.168.1.10", ["22"], row, "SSHBruteforce", data)
        assert result is True
        assert "success_" in row["SSHBruteforce"]
        orch.shared_data.write_data.assert_called_once_with(data)

    def test_executes_and_writes_failed(self):
        orch = _make_orchestrator()
        action = _mock_action(result="failed")
        row = _alive_row()
        data = [row]
        result = orch.execute_action(action, "192.168.1.10", ["22"], row, "SSHBruteforce", data)
        assert result is False
        assert "failed_" in row["SSHBruteforce"]
        orch.shared_data.write_data.assert_called_once_with(data)

    def test_action_exception_writes_failed(self):
        orch = _make_orchestrator()
        action = _mock_action()
        action.execute.side_effect = RuntimeError("boom")
        row = _alive_row()
        data = [row]
        result = orch.execute_action(action, "192.168.1.10", ["22"], row, "SSHBruteforce", data)
        assert result is False
        assert "failed_" in row["SSHBruteforce"]
        orch.shared_data.write_data.assert_called_once_with(data)


class TestExecuteStandaloneAction:
    def test_creates_standalone_row_if_missing(self):
        orch = _make_orchestrator()
        action = _mock_action(name="LogStandalone", port=0, result="success")
        data = []
        result = orch.execute_standalone_action(action, data)
        assert result is True
        assert len(data) == 1
        assert data[0]["MAC Address"] == "STANDALONE"
        assert "success_" in data[0]["LogStandalone"]

    def test_success_retry_disabled_skips(self):
        orch = _make_orchestrator()
        action = _mock_action(name="LogStandalone", port=0)
        data = [{"MAC Address": "STANDALONE", "IPs": "", "Hostnames": "", "Ports": "0",
                 "Alive": "0", "LogStandalone": "success_20260101_120000"}]
        result = orch.execute_standalone_action(action, data)
        assert result is False
        action.execute.assert_not_called()

    def test_executes_and_writes(self):
        orch = _make_orchestrator()
        action = _mock_action(name="LogStandalone", port=0, result="success")
        data = [{"MAC Address": "STANDALONE", "IPs": "", "Hostnames": "", "Ports": "0",
                 "Alive": "0"}]
        result = orch.execute_standalone_action(action, data)
        assert result is True
        assert "success_" in data[0]["LogStandalone"]
        orch.shared_data.write_data.assert_called_once()


class TestProcessAliveIPs:
    def test_skips_dead_hosts(self):
        action = _mock_action()
        orch = _make_orchestrator(actions=[action])
        dead_row = _alive_row()
        dead_row["Alive"] = "0"
        result = orch.process_alive_ips([dead_row])
        action.execute.assert_not_called()

    def test_executes_on_alive_host(self):
        action = _mock_action()
        orch = _make_orchestrator(actions=[action])
        row = _alive_row()
        result = orch.process_alive_ips([row])
        action.execute.assert_called_once()
        assert result is True

    def test_child_action_runs_after_parent_success(self):
        parent = _mock_action(name="SSHBruteforce")
        child = _mock_action(name="StealFilesSSH", parent="SSHBruteforce")
        orch = _make_orchestrator(actions=[parent, child])
        row = _alive_row()
        orch.process_alive_ips([row])
        parent.execute.assert_called_once()
        # Child should also execute since parent succeeded
        child.execute.assert_called_once()
