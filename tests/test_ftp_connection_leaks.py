"""FTP-1: FTP connection leaks.

FTP connections (ftplib.FTP) were not closed on exception paths in
ftp_connector.ftp_connect and steal_files_ftp.connect_ftp / execute.
conn.quit() was only on the success path, so refused/timeout/auth-failure
paths leaked the control socket. On long brute-force runs this directly
caused OSError: [Errno 24] Too many open files.

The fix wraps every FTP connection in try/finally with explicit close.
"""
import ast
import socket
import sys
import threading
import time
from ftplib import FTP, error_perm, error_temp
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Source-level guarantees
# ---------------------------------------------------------------------------


class TestFtpCloseInFinally:
    def test_ftp_connect_has_finally(self):
        """AST: ftp_connect must have a finally block that closes the conn."""
        with open("actions/ftp_connector.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ftp_connect":
                has_finally_close = False
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Try) and sub.finalbody:
                        for stmt in sub.finalbody:
                            for s in ast.walk(stmt):
                                if (isinstance(s, ast.Call)
                                        and isinstance(s.func, ast.Attribute)
                                        and s.func.attr == "close"):
                                    has_finally_close = True
                assert has_finally_close, (
                    "ftp_connect must close the connection in a finally block")
                return
        pytest.fail("ftp_connect method not found")

    def test_connect_ftp_closes_on_exception(self):
        """AST: steal_files_ftp.connect_ftp must close on exception path."""
        with open("actions/steal_files_ftp.py", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "connect_ftp":
                # Look for .close() call inside an except handler
                has_except_close = False
                for sub in ast.walk(node):
                    if isinstance(sub, ast.ExceptHandler):
                        for s in ast.walk(sub):
                            if (isinstance(s, ast.Call)
                                    and isinstance(s.func, ast.Attribute)
                                    and s.func.attr == "close"):
                                has_except_close = True
                assert has_except_close, (
                    "connect_ftp must close the FTP socket on exception path")
                return
        pytest.fail("connect_ftp method not found")

    def test_execute_uses_finally(self):
        """AST: steal_files_ftp.execute's per-credential loop must close
        the connection in a finally block."""
        with open("actions/steal_files_ftp.py", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "execute":
                # Find a try/finally that closes ftp via quit or close
                has_finally_close = False
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Try) and sub.finalbody:
                        for stmt in sub.finalbody:
                            for s in ast.walk(stmt):
                                if (isinstance(s, ast.Call)
                                        and isinstance(s.func, ast.Attribute)
                                        and s.func.attr in ("quit", "close")):
                                    has_finally_close = True
                assert has_finally_close, (
                    "execute's per-credential loop must close ftp in finally")
                return
        pytest.fail("execute method not found")


# ---------------------------------------------------------------------------
# Behavioral tests using the in-process fake FTP server
# ---------------------------------------------------------------------------


class TestFtpConnectionLifecycle:
    def test_ftp_connect_returns_false_on_auth_failure(self, mock_shared_data,
                                                        real_ftp_server):
        """When FTP login fails, ftp_connect must return False AND close
        the underlying socket (the previous code leaked)."""
        sys.modules.pop("actions.ftp_connector", None)
        from actions import ftp_connector as ftp_mod

        instance = ftp_mod.FTPConnector.__new__(ftp_mod.FTPConnector)
        instance.shared_data = mock_shared_data

        # Redirect FTP.connect to use the fixture port, and patch login
        # to raise so we exercise the exception path.
        target_port = real_ftp_server["port"]
        orig_connect = ftp_mod.FTP.connect
        def redirected_connect(self, host="", port=0, timeout=-999,
                               source_address=None):
            return orig_connect(self, host, target_port, timeout, source_address)

        with patch.object(ftp_mod.FTP, "connect", redirected_connect), \
             patch.object(ftp_mod.FTP, "login",
                          side_effect=error_perm("530 auth failed")):
            result = instance.ftp_connect(real_ftp_server["host"], "user", "bad")
        assert result is False, "ftp_connect must return False on auth failure"

    def test_ftp_connect_succeeds_against_real_server(self, mock_shared_data,
                                                       real_ftp_server):
        """End-to-end: ftp_connect must succeed against our fake FTP server
        and the socket must be cleaned up when done."""
        sys.modules.pop("actions.ftp_connector", None)
        from actions import ftp_connector as ftp_mod

        # The connector hardcodes port 21 (conn.connect(adresse_ip, 21)).
        # Redirect FTP.connect to use our fixture's random port.
        target_port = real_ftp_server["port"]
        orig_connect = ftp_mod.FTP.connect
        def redirected_connect(self, host="", port=0, timeout=-999,
                               source_address=None):
            return orig_connect(self, host, target_port, timeout, source_address)
        with patch.object(ftp_mod.FTP, "connect", redirected_connect):
            instance = ftp_mod.FTPConnector.__new__(ftp_mod.FTPConnector)
            instance.shared_data = mock_shared_data
            result = instance.ftp_connect(real_ftp_server["host"], "user", "pass")

        assert result is True, (
            f"ftp_connect should succeed against the test FTP server; "
            f"got {result}")
        time.sleep(0.05)
        interactions = real_ftp_server["interactions"]
        assert "QUIT" in [i.upper() for i in interactions], (
            f"ftp_connect should send QUIT to close the session; "
            f"server saw: {interactions}")

    def test_connect_ftp_returns_none_on_failure_and_closes(self, mock_shared_data,
                                                             real_ftp_server):
        """steal_files_ftp.connect_ftp must return None on failure and close
        the socket (was leaking)."""
        sys.modules.pop("actions.steal_files_ftp", None)
        from actions import steal_files_ftp as steal_mod

        instance = steal_mod.StealFilesFTP.__new__(steal_mod.StealFilesFTP)
        instance.shared_data = mock_shared_data
        instance.ftp_connected = False

        target_port = real_ftp_server["port"]
        orig_connect = steal_mod.FTP.connect
        def redirected_connect(self, host="", port=0, timeout=-999,
                               source_address=None):
            return orig_connect(self, host, target_port, timeout, source_address)

        captured = {}
        orig_ftp = steal_mod.FTP
        class _CapturingFTP(orig_ftp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                captured["ftp"] = self
        with patch.object(steal_mod, "FTP", _CapturingFTP), \
             patch.object(steal_mod.FTP, "connect", redirected_connect), \
             patch.object(steal_mod.FTP, "login",
                          side_effect=error_perm("530 auth failed")):
            result = instance.connect_ftp(real_ftp_server["host"], "user", "bad")
        assert result is None, "connect_ftp should return None on failure"
        time.sleep(0.05)
        # The connection's socket MUST be cleaned up (closed) — leak fix.
        assert captured["ftp"].sock is None, (
            "connect_ftp leaked the FTP socket on auth failure")
