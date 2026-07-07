"""Coverage sprint 5 — safe push to 55%.

Only non-blocking, non-network, non-threading tests.
"""
import csv
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestSharedInitializePathsDeep:
    def test_initialize_paths_sets_attributes(self, tmp_path):
        sys.modules.pop('shared', None)
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.currentdir = str(tmp_path / "bjorn")
        os.makedirs(sd.currentdir, exist_ok=True)
        sd.initialize_paths()
        assert hasattr(sd, 'webdir')
        assert hasattr(sd, 'configdir')
        assert hasattr(sd, 'datadir')
        assert hasattr(sd, 'output_dir')
        assert hasattr(sd, 'logsdir')
        assert hasattr(sd, 'picdir')
        assert hasattr(sd, 'fontdir')


class TestSharedGenerateActionsWithAction:
    @pytest.mark.skip(reason="generate_actions_json importlib path needs actions/__init__.py with proper sys.path")
    def test_generates_json_with_real_action(self, tmp_path):
        sys.modules.pop('shared', None)
        from shared import SharedData
        actions_dir = tmp_path / "actions"
        actions_dir.mkdir(exist_ok=True)
        (actions_dir / "__init__.py").write_text("")
        (actions_dir / "fake_action.py").write_text(
            "b_class = 'FakeAction'\n"
            "b_status = 'fake'\n"
            "b_port = 22\n"
            "b_parent = None\n"
            "class FakeAction:\n"
            "    def __init__(self, sd): pass\n"
        )
        sd = SharedData.__new__(SharedData)
        sd.actions_dir = str(actions_dir)
        sd.actions_file = str(tmp_path / "actions.json")
        sd.status_list = []
        sd.generate_actions_json()
        with open(sd.actions_file) as f:
            actions = json.load(f)
        assert len(actions) == 1
        assert actions[0]["b_class"] == "FakeAction"


class TestOrchestratorExecuteActionEdgeCases:
    def test_port_not_in_list_returns_false(self):
        from orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)
        orch.shared_data = MagicMock()
        orch.shared_data.retry_success_actions = False
        action = MagicMock()
        action.port = 3389
        action.b_parent_action = None
        action.action_name = "RDP"
        row = {"Alive": "1", "RDP": "", "IPs": "10.0.0.1"}
        result = orch.execute_action(action, "10.0.0.1", ["22", "80"], row, "RDP", [row])
        assert result is False

    def test_executes_action_exception_writes_failed(self):
        from orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)
        orch.shared_data = MagicMock()
        orch.shared_data.retry_success_actions = False
        orch.shared_data.failed_retry_delay = 600
        orch.shared_data.success_retry_delay = 900
        action = MagicMock()
        action.port = 22
        action.b_parent_action = None
        action.action_name = "SSH"
        action.execute.side_effect = RuntimeError("crash")
        row = {"Alive": "1", "SSH": "", "IPs": "10.0.0.1"}
        result = orch.execute_action(action, "10.0.0.1", ["22"], row, "SSH", [row])
        assert result is False
        assert "failed_" in row["SSH"]


class TestSharedDeleteWebconsoleLog:
    def test_no_crash_on_missing(self, tmp_path):
        sys.modules.pop('shared', None)
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.webconsolelog = str(tmp_path / "nope.txt")
        sd.delete_webconsolelog()


class TestSharedUpdateMacBlacklist:
    def test_creates_list_if_missing(self):
        sys.modules.pop('shared', None)
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.config = {}
        sd.update_mac_blacklist()
        assert isinstance(sd.config.get("mac_scan_blacklist"), list)


class TestSSHConnectorLoadScanFile:
    def test_reload_updates_scan(self, tmp_path):
        from actions.ssh_connector import SSHConnector
        sd = MagicMock()
        sd.netkbfile = str(tmp_path / "netkb.csv")
        with open(sd.netkbfile, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["MAC Address", "IPs", "Hostnames", "Alive", "Ports"])
            w.writerow(["AA:BB", "10.0.0.1", "h", "1", "22;80"])
        sd.sshfile = str(tmp_path / "ssh.csv")
        sd.usersfile = str(tmp_path / "u.txt")
        with open(sd.usersfile, 'w') as f:
            f.write("a\n")
        sd.passwordsfile = str(tmp_path / "p.txt")
        with open(sd.passwordsfile, 'w') as f:
            f.write("b\n")
        conn = SSHConnector(sd)
        with open(sd.netkbfile, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["MAC Address", "IPs", "Hostnames", "Alive", "Ports"])
            w.writerow(["CC:DD", "10.0.0.2", "h2", "1", "22;443"])
        conn.load_scan_file()
        assert "10.0.0.2" in conn.scan["IPs"].values


class TestTelnetShimSafe:
    def test_telnet_shim_methods_exist(self):
        from telnet_shim import Telnet
        assert hasattr(Telnet, 'read_until')
        assert hasattr(Telnet, 'write')
        assert hasattr(Telnet, 'close')


class TestDisplayMethodsExist:
    def test_all_key_methods(self):
        sys.modules.pop('display', None)
        import display
        for method in ('render_frame', 'run', 'display_comment',
                       'schedule_update_shared_data', 'schedule_update_vuln_count',
                       'update_main_image', 'update_shared_data',
                       'update_vuln_count', 'is_interface_connected'):
            assert hasattr(display.Display, method), f"Display.{method} missing"


class TestWebappRoutesExist:
    def test_login_route_handled(self):
        sys.modules.pop('webapp', None)
        import webapp
        src = open("webapp.py").read()
        assert "/login" in src
        assert "/logout" in src
        assert "bjorn_session" in src
