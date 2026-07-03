"""SMB-1, SMB-2, SMB-3: SMB connection leaks + progress context bug.

SMB-1: SMBConnection.close() was only called on the success path. On
exception paths (refused, timeout, auth failure) the socket leaked. Fixed
by wrapping in try/finally in both smb_connector.py and steal_files_smb.py.

SMB-2: Port 445 requires is_direct_tcp=True per pysmb docs (otherwise the
client tries NetBIOS on 139). Folded into SMB-1 commit.

SMB-3: progress.update(task_id, ...) was called OUTSIDE the
with Progress(...) context in the smbclient fallback path, raising
NameError whenever direct SMB failed. The fallback is now inside the same
with-block.
"""
import ast
import inspect
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# SMB-1 + SMB-2
# ---------------------------------------------------------------------------


class TestSmbConnectionClose:
    def test_smb_connect_closes_in_finally(self):
        """AST: smb_connect must close conn in a finally block."""
        with open("actions/smb_connector.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        # Find smb_connect method
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "smb_connect":
                # Must contain at least one Try with a finally that closes
                closes_in_finally = False
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Try) and sub.finalbody:
                        for stmt in sub.finalbody:
                            for s in ast.walk(stmt):
                                if (isinstance(s, ast.Call)
                                        and isinstance(s.func, ast.Attribute)
                                        and s.func.attr == "close"):
                                    closes_in_finally = True
                assert closes_in_finally, (
                    "smb_connect must call conn.close() in a finally block")
                return
        pytest.fail("smb_connect method not found")

    def test_smb_connect_closes_on_exception(self, mock_shared_data):
        """Behavioral: when connect() raises, close() must still be called."""
        sys.modules.pop("actions.smb_connector", None)
        from actions import smb_connector as smb_mod

        instance = smb_mod.SMBConnector.__new__(smb_mod.SMBConnector)
        instance.shared_data = mock_shared_data

        # Mock SMBConnection so connect() raises
        with patch.object(smb_mod, "SMBConnection") as mock_conn_cls:
            mock_conn = MagicMock()
            mock_conn.connect.side_effect = ConnectionRefusedError("refused")
            mock_conn_cls.return_value = mock_conn

            result = instance.smb_connect("10.0.0.1", "user", "pass")

            # Result is [] on exception
            assert result == []
            # close() MUST have been called even though connect() raised
            mock_conn.close.assert_called(), (
                "SMBConnection.close() must be called even when connect() raises")

    def test_smb_connect_closes_on_success(self, mock_shared_data):
        sys.modules.pop("actions.smb_connector", None)
        from actions import smb_connector as smb_mod

        instance = smb_mod.SMBConnector.__new__(smb_mod.SMBConnector)
        instance.shared_data = mock_shared_data

        with patch.object(smb_mod, "SMBConnection") as mock_conn_cls:
            mock_conn = MagicMock()
            mock_conn.listShares.return_value = []
            mock_conn_cls.return_value = mock_conn

            instance.smb_connect("10.0.0.1", "user", "pass")

            mock_conn.close.assert_called(), (
                "SMBConnection.close() must be called on success path too")

    def test_is_direct_tcp_true_present(self):
        """SMB-2: SMBConnection() must include is_direct_tcp=True."""
        with open("actions/smb_connector.py", encoding="utf-8") as f:
            src = f.read()
        # Find smb_connect body and verify is_direct_tcp=True is passed
        # to the SMBConnection() constructor.
        smb_connect_start = src.index("def smb_connect")
        smb_connect_end = src.find("\n    def ", smb_connect_start + 20)
        method_src = src[smb_connect_start:smb_connect_end]
        assert "is_direct_tcp=True" in method_src, (
            f"smb_connect must pass is_direct_tcp=True to SMBConnection(). "
            f"Method source:\n{method_src}")


class TestStealFilesSmbCloses:
    def test_steal_files_smb_close_in_finally(self):
        """AST: steal_files_smb execute() must close conn in finally."""
        with open("actions/steal_files_smb.py", encoding="utf-8") as f:
            src = f.read()
        # Search for "finally:" blocks that close conn
        tree = ast.parse(src)
        close_in_finally_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Try) and node.finalbody:
                for stmt in node.finalbody:
                    for s in ast.walk(stmt):
                        if (isinstance(s, ast.Call)
                                and isinstance(s.func, ast.Attribute)
                                and s.func.attr == "close"):
                            close_in_finally_count += 1
        assert close_in_finally_count >= 1, (
            "steal_files_smb must close conn in a finally block")


# ---------------------------------------------------------------------------
# SMB-3
# ---------------------------------------------------------------------------


class TestSmbProgressContext:
    """PORT-9: SMB bruteforce progress reporting via ProgressTracker.

    The original SMB-3 bug was a NameError: the smbclient-fallback
    ``progress.update(task_id, ...)`` ran OUTSIDE the ``with Progress(...)``
    scope, so ``progress``/``task_id`` were undefined. PORT-9 replaced the
    rich Progress bar with a module-level ``ProgressTracker`` — there is no
    ``with`` scope to escape, so the NameError is now STRUCTURALLY
    impossible. These tests pin the new contract.
    """

    def test_no_rich_progress_in_smb_connector(self):
        """The rich Progress bar must be gone (replaced by ProgressTracker)."""
        with open("actions/smb_connector.py", encoding="utf-8") as f:
            src = f.read()
        assert "from rich.progress import" not in src, (
            "rich.progress import must be removed (PORT-9 ProgressTracker).")
        assert "with Progress(" not in src, (
            "No 'with Progress(' block should remain in smb_connector.")

    def test_smbclient_fallback_uses_tracker_advance(self):
        """The smbclient-fallback loop must still report progress via the
        tracker (so progress % keeps updating during the fallback)."""
        with open("actions/smb_connector.py", encoding="utf-8") as f:
            src = f.read()
        # Slice the smbclient fallback region (after 'smbclient -L for').
        marker = "Trying smbclient -L for"
        assert marker in src, "Expected smbclient fallback block."
        fallback_src = src[src.index(marker):]
        assert "tracker.advance()" in fallback_src, (
            "smbclient fallback must call tracker.advance() to report progress.")

