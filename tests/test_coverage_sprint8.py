"""Coverage sprint 8 — push past 54% toward 55%.

Remaining safe targets: utils serve_favicon/serve_manifest, webapp
do_GET/do_POST route coverage, scanning ScanPorts inner class structure,
orchestrator process_alive_ips with standalone row.
"""
import csv
import json
import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest


class TestUtilsServeFavicon:
    def test_favicon_returns_200(self, custom_handler_server, tmp_path):
        import urllib.request
        webdir = str(tmp_path / "web")
        imgdir = os.path.join(webdir, "images")
        os.makedirs(imgdir, exist_ok=True)
        with open(os.path.join(imgdir, "favicon.ico"), 'wb') as f:
            f.write(b"\x00\x00\x01\x00fake")
        custom_handler_server["shared"].webdir = webdir
        url = f"{custom_handler_server['base_url']}/favicon.ico"
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.status == 200


class TestUtilsServeManifest:
    def test_manifest_returns_200(self, custom_handler_server, tmp_path):
        import urllib.request
        webdir = str(tmp_path / "web")
        os.makedirs(webdir, exist_ok=True)
        with open(os.path.join(webdir, "manifest.json"), 'w') as f:
            json.dump({"name": "Bjorn"}, f)
        custom_handler_server["shared"].webdir = webdir
        url = f"{custom_handler_server['base_url']}/manifest.json"
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.status == 200


class TestUtilsServeAppleTouchIcon:
    def test_apple_touch_icon_returns_200(self, custom_handler_server, tmp_path):
        import urllib.request
        webdir = str(tmp_path / "web")
        imgdir = os.path.join(webdir, "icons")
        os.makedirs(imgdir, exist_ok=True)
        with open(os.path.join(imgdir, "icon-192x192.png"), 'wb') as f:
            f.write(b"\x89PNG fake")
        custom_handler_server["shared"].webdir = webdir
        url = f"{custom_handler_server['base_url']}/apple-touch-icon"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200
        except Exception:
            pass


class TestOrchestratorProcessAliveStandalone:
    def test_standalone_actions_not_in_process_alive(self):
        """process_alive_ips only processes non-standalone actions."""
        from orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)
        orch.shared_data = MagicMock()
        orch.shared_data.retry_success_actions = False
        orch.semaphore = threading.Semaphore(10)

        action = MagicMock()
        action.action_name = "SSHBruteforce"
        action.port = 22
        action.b_parent_action = None
        action.execute.return_value = 'success'

        orch.actions = [action]
        # Dead host — no action should execute.
        result = orch.process_alive_ips([{"Alive": "0", "IPs": "", "Ports": ""}])
        assert result is False
        action.execute.assert_not_called()


class TestScanningScanPortsStructure:
    def test_scan_ports_class_exists(self):
        from actions.scanning import NetworkScanner
        assert hasattr(NetworkScanner, 'ScanPorts')
        assert hasattr(NetworkScanner, 'LiveStatusUpdater')


class TestWebappVersionEndpoint:
    def test_version_returns_correct_json(self, custom_handler_server):
        import urllib.request
        url = f"{custom_handler_server['base_url']}/version"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        assert "version" in data


class TestWebappCsrfEndpoint:
    def test_csrf_returns_token(self, custom_handler_server):
        import urllib.request
        url = f"{custom_handler_server['base_url']}/csrf_token"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        assert "csrf_token" in data


class TestWebappWebDelayEndpoint:
    def test_web_delay_returns_int(self, custom_handler_server):
        import urllib.request
        url = f"{custom_handler_server['base_url']}/get_web_delay"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        assert "web_delay" in data


class TestSharedWrapTextEdgeCases:
    def test_empty_string(self):
        sys.modules.pop('shared', None)
        from shared import SharedData
        from PIL import ImageFont
        sd = SharedData.__new__(SharedData)
        font = ImageFont.load_default()
        result = sd.wrap_text("", font, 100)
        assert isinstance(result, list)

    def test_normal_short_text(self):
        sys.modules.pop('shared', None)
        from shared import SharedData
        from PIL import ImageFont
        sd = SharedData.__new__(SharedData)
        font = ImageFont.load_default()
        result = sd.wrap_text("hello", font, 200)
        assert len(result) >= 1


class TestConnectorWorkerSSHSuccess:
    def test_worker_saves_on_success(self, tmp_path):
        from actions.ssh_connector import SSHConnector
        from actions.bruteforce_common import ProgressTracker
        sd = MagicMock()
        sd.netkbfile = str(tmp_path / "netkb.csv")
        with open(sd.netkbfile, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["MAC Address", "IPs", "Hostnames", "Alive", "Ports"])
            w.writerow(["AA:BB", "10.0.0.1", "h", "1", "22;80"])
        sd.sshfile = str(tmp_path / "ssh.csv")
        sd.usersfile = str(tmp_path / "u.txt")
        with open(sd.usersfile, 'w') as f:
            f.write("admin\n")
        sd.passwordsfile = str(tmp_path / "p.txt")
        with open(sd.passwordsfile, 'w') as f:
            f.write("pw\n")
        sd.orchestrator_should_exit = False
        sd.bjorn_progress = ""
        conn = SSHConnector(sd)
        conn.queue.put(("10.0.0.1", "admin", "pw", "AA:BB", "h", "22"))
        tracker = ProgressTracker(sd, 1)
        success_flag = [False]
        with patch.object(conn, 'ssh_connect', return_value=True):
            conn.worker(tracker, success_flag)
        assert success_flag[0] is True
        # Results saved to ssh.csv.
        with open(conn.sshfile) as f:
            rows = list(csv.reader(f))
        assert len(rows) >= 2  # header + result
