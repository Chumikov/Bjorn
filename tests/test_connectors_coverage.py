"""Behavioral tests for bruteforce connectors (COV-6).

Tests individual connector methods (connect, save_results, removeduplicates)
WITHOUT running run_bruteforce (which spawns threads). Mock the network
library at the connect level.
"""
import csv
import os
from unittest.mock import MagicMock, patch

import pytest


def _setup_files(tmp_path, proto="ssh", port="22"):
    """Create tmp netkb.csv (Ports with ';' for string dtype), users, passwords."""
    netkb = tmp_path / "netkb.csv"
    with open(netkb, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(["MAC Address", "IPs", "Hostnames", "Alive", "Ports"])
        w.writerow(["AA:BB:CC:DD:EE:FF", "10.0.0.1", "testhost", "1", f"{port};80"])
    users = tmp_path / "users.txt"
    users.write_text("admin\nroot\n")
    passwords = tmp_path / "passwords.txt"
    passwords.write_text("123456\npassword\n")
    proto_file = tmp_path / f"{proto}.csv"
    return str(netkb), str(users), str(passwords), str(proto_file)


def _mock_sd(tmp_path, proto, port):
    netkb, users, pw, proto_file = _setup_files(tmp_path, proto, port)
    sd = MagicMock()
    sd.netkbfile = netkb
    sd.usersfile = users
    sd.passwordsfile = pw
    setattr(sd, f"{proto}file", proto_file)
    sd.orchestrator_should_exit = False
    sd.bjorn_progress = ""
    for attr in ("timewait_ssh", "timewait_smb", "timewait_ftp",
                 "timewait_sql", "timewait_telnet", "timewait_rdp"):
        setattr(sd, attr, 0)
    return sd, proto_file


class TestSSHConnector:
    def test_init_reads_netkb_and_creates_output(self, tmp_path):
        from actions.ssh_connector import SSHConnector
        sd, ssh_file = _mock_sd(tmp_path, "ssh", "22")
        conn = SSHConnector(sd)
        assert conn.sshfile == ssh_file
        assert os.path.exists(ssh_file)
        assert "admin" in conn.users

    def test_ssh_connect_success(self, tmp_path):
        from actions.ssh_connector import SSHConnector
        sd, _ = _mock_sd(tmp_path, "ssh", "22")
        with patch("actions.ssh_connector.paramiko") as mock_paramiko:
            mock_client = MagicMock()
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.WarningPolicy = MagicMock
            conn = SSHConnector(sd)
            assert conn.ssh_connect("10.0.0.1", "admin", "123456") is True
            mock_client.connect.assert_called_once()

    def test_ssh_connect_auth_failure(self, tmp_path):
        from actions.ssh_connector import SSHConnector
        sd, _ = _mock_sd(tmp_path, "ssh", "22")
        with patch("actions.ssh_connector.paramiko") as mock_paramiko:
            mock_client = MagicMock()
            # Use a real Exception so the except clause can catch it.
            AuthExc = type("AuthenticationException", (Exception,), {})
            mock_client.connect.side_effect = AuthExc("auth fail")
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AuthenticationException = AuthExc
            mock_paramiko.SSHException = Exception
            mock_paramiko.WarningPolicy = MagicMock
            conn = SSHConnector(sd)
            assert conn.ssh_connect("10.0.0.1", "admin", "wrong") is False

    def test_save_results_and_dedup(self, tmp_path):
        from actions.ssh_connector import SSHConnector
        sd, ssh_file = _mock_sd(tmp_path, "ssh", "22")
        conn = SSHConnector(sd)
        conn.results = [["mac1", "10.0.0.1", "h1", "admin", "123456", "22"]]
        conn.save_results()
        conn.results = [["mac1", "10.0.0.1", "h1", "admin", "123456", "22"]]  # dup
        conn.save_results()
        conn.removeduplicates()
        with open(ssh_file, 'r') as f:
            rows = list(csv.reader(f))
        # Header + 1 unique row (deduped).
        assert len(rows) == 2


class TestFTPConnector:
    def test_init_and_save(self, tmp_path):
        from actions.ftp_connector import FTPConnector
        sd, ftp_file = _mock_sd(tmp_path, "ftp", "21")
        conn = FTPConnector(sd)
        assert conn.ftpfile == ftp_file
        conn.results = [["mac", "10.0.0.1", "h", "anon", "anon@", "21"]]
        conn.save_results()
        with open(ftp_file, 'r') as f:
            rows = list(csv.reader(f))
        assert len(rows) == 2  # header + 1


class TestTelnetConnector:
    def test_init_and_save(self, tmp_path):
        from actions.telnet_connector import TelnetConnector
        sd, telnet_file = _mock_sd(tmp_path, "telnet", "23")
        conn = TelnetConnector(sd)
        assert conn.telnetfile == telnet_file
        conn.results = [["mac", "10.0.0.1", "h", "admin", "pw", "23"]]
        conn.save_results()
        with open(telnet_file, 'r') as f:
            rows = list(csv.reader(f))
        assert len(rows) == 2


class TestSQLConnector:
    def test_init_and_save(self, tmp_path):
        from actions.sql_connector import SQLConnector
        sd, sql_file = _mock_sd(tmp_path, "sql", "3306")
        conn = SQLConnector(sd)
        assert conn.sqlfile == sql_file
        conn.results = [["10.0.0.1", "root", "pw", "3306", "mydb"]]
        conn.save_results()
        with open(sql_file, 'r') as f:
            rows = list(csv.reader(f))
        assert len(rows) == 2
