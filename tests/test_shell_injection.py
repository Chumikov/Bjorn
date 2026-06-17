import os
import importlib
import glob
import subprocess
from unittest.mock import MagicMock, patch, call

import pytest


class TestNoShellInjection:
    def _get_popen_calls(self, mock_popen):
        calls = mock_popen.call_args_list
        results = []
        for c in calls:
            args = c[0]
            if args:
                results.append(args[0])
        return results

    def test_clear_files_uses_list_args(self, mock_handler, mock_shared_data):
        with patch("utils.subprocess.run") as mock_run, \
             patch("utils.glob.glob", return_value=["/tmp/fake"]):
            mock_run.return_value = MagicMock(returncode=0)

            from utils import WebUtils
            web_utils = WebUtils(mock_shared_data, MagicMock())
            web_utils.clear_files(mock_handler)

            for c in mock_run.call_args_list:
                args = c[0]
                assert isinstance(args[0], list), f"clear_files still uses shell=True: {args!r}"

    def test_clear_files_light_uses_list_args(self, mock_handler, mock_shared_data):
        with patch("utils.subprocess.run") as mock_run, \
             patch("utils.glob.glob", return_value=["/tmp/fake"]):
            mock_run.return_value = MagicMock(returncode=0)

            from utils import WebUtils
            web_utils = WebUtils(mock_shared_data, MagicMock())
            web_utils.clear_files_light(mock_handler)

            for c in mock_run.call_args_list:
                args = c[0]
                assert isinstance(args[0], list), f"clear_files_light still uses shell=True: {args!r}"

    def test_reboot_uses_list_args(self, mock_handler, mock_shared_data):
        # UTL-3: reboot_system now uses subprocess.run (was Popen).
        # Patch run() and verify the args are a list (no shell=True).
        with patch("utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            from utils import WebUtils
            web_utils = WebUtils(mock_shared_data, MagicMock())
            web_utils.reboot_system(mock_handler)

            for c in mock_run.call_args_list:
                args = c[0]
                assert isinstance(args[0], list), (
                    f"reboot still uses shell=True: {args!r}")

    def test_shutdown_uses_list_args(self, mock_handler, mock_shared_data):
        # UTL-3: shutdown_system now uses subprocess.run.
        with patch("utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            from utils import WebUtils
            web_utils = WebUtils(mock_shared_data, MagicMock())
            web_utils.shutdown_system(mock_handler)

            for c in mock_run.call_args_list:
                args = c[0]
                assert isinstance(args[0], list), (
                    f"shutdown still uses shell=True: {args!r}")

    def test_restart_service_uses_list_args(self, mock_handler, mock_shared_data):
        # UTL-3: restart_bjorn_service now uses subprocess.run.
        with patch("utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            from utils import WebUtils
            web_utils = WebUtils(mock_shared_data, MagicMock())
            web_utils.restart_bjorn_service(mock_handler)

            for c in mock_run.call_args_list:
                args = c[0]
                assert isinstance(args[0], list), (
                    f"restart still uses shell=True: {args!r}")

    def test_connect_wifi_uses_list_args(self, mock_handler, mock_shared_data):
        with patch("utils.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            mock_handler.headers = {"Content-Length": "42"}
            mock_handler.rfile = MagicMock()
            mock_handler.rfile.read.return_value = b'{"ssid":"test","password":"pass"}'

            from utils import WebUtils
            web_utils = WebUtils(mock_shared_data, MagicMock())
            with patch.object(web_utils, 'update_nmconnection'):
                web_utils.connect_wifi(mock_handler)

            for args in self._get_popen_calls(mock_popen):
                assert isinstance(args, list), f"connect_wifi still uses shell=True: {args!r}"

    def test_disconnect_wifi_uses_list_args(self, mock_handler, mock_shared_data):
        with patch("utils.subprocess.Popen") as mock_popen, \
             patch("builtins.open", MagicMock()):
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            from utils import WebUtils
            web_utils = WebUtils(mock_shared_data, MagicMock())
            web_utils.disconnect_and_clear_wifi(mock_handler)

            for args in self._get_popen_calls(mock_popen):
                assert isinstance(args, list), f"disconnect_wifi still uses shell=True: {args!r}"


class TestSmbclientNoShellInjection:
    def test_smbclient_uses_list_args(self, mock_shared_data):
        import sys
        if 'actions.smb_connector' not in sys.modules:
            sys.modules['smb'] = MagicMock()
            sys.modules['smb.SMBConnection'] = MagicMock()
        with patch("actions.smb_connector.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 1
            mock_popen.return_value = mock_proc

            from actions.smb_connector import SMBConnector
            connector = SMBConnector.__new__(SMBConnector)
            connector.shared_data = mock_shared_data

            malicious_user = "admin; rm -rf /"
            malicious_password = "pass$(cat /etc/shadow)"
            connector.smbclient_l("192.168.1.1", malicious_user, malicious_password)

            for c in mock_popen.call_args_list:
                args = c[0]
                assert isinstance(args[0], list), "smbclient_l still uses shell=True"

    def test_smbclient_does_not_execute_semicolon(self, mock_shared_data):
        import sys
        if 'actions.smb_connector' not in sys.modules:
            sys.modules['smb'] = MagicMock()
            sys.modules['smb.SMBConnection'] = MagicMock()
        with patch("actions.smb_connector.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"Sharename\n---------\nshare1", b"")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            from actions.smb_connector import SMBConnector
            connector = SMBConnector.__new__(SMBConnector)
            connector.shared_data = mock_shared_data

            connector.smbclient_l("192.168.1.1", "admin; id", "pass")

            cmd_args = mock_popen.call_args_list[0][0][0]
            assert isinstance(cmd_args, list)
            assert ";" not in cmd_args[3] or cmd_args[3].count(";") <= 1


class TestRdpConnectNoShellInjection:
    def test_rdp_connect_uses_list_args(self, mock_shared_data):
        with patch("actions.rdp_connector.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 1
            mock_popen.return_value = mock_proc

            from actions.rdp_connector import RDPConnector
            connector = RDPConnector.__new__(RDPConnector)
            connector.shared_data = mock_shared_data

            connector.rdp_connect("192.168.1.1", "admin; id", "pass$(whoami)")

            for c in mock_popen.call_args_list:
                args = c[0]
                assert isinstance(args[0], list), "rdp_connect still uses shell=True"

    def test_rdp_special_chars_not_interpreted(self, mock_shared_data):
        with patch("actions.rdp_connector.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 1
            mock_popen.return_value = mock_proc

            from actions.rdp_connector import RDPConnector
            connector = RDPConnector.__new__(RDPConnector)
            connector.shared_data = mock_shared_data

            connector.rdp_connect("192.168.1.1", "user`id`", "p@ss; rm -rf /")

            cmd_args = mock_popen.call_args_list[0][0][0]
            assert isinstance(cmd_args, list)
            user_found = any("`" in str(a) for a in cmd_args)
            assert user_found, "Special chars should be preserved as literal args, not interpreted"


class TestStealFilesRdpNoShellInjection:
    def test_steal_file_uses_list_args(self, mock_shared_data):
        with patch("actions.steal_files_rdp.subprocess.Popen") as mock_popen, \
             patch("actions.steal_files_rdp.os.makedirs"):
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            from actions.steal_files_rdp import StealFilesRDP
            stealer = StealFilesRDP.__new__(StealFilesRDP)
            stealer.shared_data = mock_shared_data

            stealer.steal_file("/mnt/shared/secret; rm -rf /", "/tmp/out")

            for c in mock_popen.call_args_list:
                args = c[0]
                assert isinstance(args[0], list), "steal_file still uses shell=True"
