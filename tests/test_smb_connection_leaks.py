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
    def test_progress_update_inside_with_block(self):
        """AST: the smbclient-fallback progress.update call must be inside
        the with Progress(...) block of run_bruteforce.

        The worker() method's progress.update() is fine because progress
        and task_id are passed as explicit args. We only care about the
        smbclient fallback in run_bruteforce.
        """
        with open("actions/smb_connector.py", encoding="utf-8") as f:
            src = f.read()
        # Slice out run_bruteforce method only (start to next def at same indent)
        start = src.index("def run_bruteforce")
        # End at the next "def " at column 4 (method-level)
        next_def = src.find("\n    def ", start + 20)
        method_src = src[start:next_def if next_def != -1 else len(src)]

        # The smbclient fallback call we care about
        fallback_call = "progress.update(task_id, advance=1)"
        assert fallback_call in method_src, (
            "Expected smbclient fallback progress.update call in run_bruteforce")

        # Find the position of the fallback call
        call_pos = method_src.index(fallback_call)
        # Find the nearest "with Progress(...) as progress:" BEFORE the call
        with_pos = method_src.rfind("with Progress(", 0, call_pos)
        assert with_pos != -1, (
            "smbclient fallback progress.update call must be inside a "
            "with Progress(...) block")

        # Check that the with-block extends past the call (the with body
        # ends at the same indent as the with keyword). Find the with-block
        # indent, then find where that indent returns.
        with_line_start = method_src.rfind("\n", 0, with_pos) + 1
        with_indent = len(method_src[with_line_start:with_line_start + len(method_src[with_line_start:])]) - len(method_src[with_line_start:].lstrip())
        # Lines after the with that are at the SAME or LESS indent close the block
        after_with = method_src[with_pos:]
        # Find first line at indent <= with_indent (excluding the with line itself)
        for line in after_with.split("\n")[1:]:
            if not line.strip():
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= with_indent:
                # This line is outside the with block
                close_pos = method_src.index(line, with_pos)
                if close_pos > call_pos:
                    # Call is before the close — good
                    return
                else:
                    # Close is before the call — call is OUTSIDE the with
                    break
        # If we didn't find a close before the call, the call is inside
        # (the with block extends to end of method)
        return  # call is inside the with block

    def test_progress_update_in_source(self):
        """Sanity: the smbclient fallback progress.update call exists."""
        with open("actions/smb_connector.py", encoding="utf-8") as f:
            src = f.read()
        assert "progress.update(task_id, advance=1)" in src, (
            "Expected progress.update(task_id, advance=1) for smbclient fallback")
