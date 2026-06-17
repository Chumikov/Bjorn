"""ARCH-1, ARCH-2: thread daemon flag + signal handler cleanup.

ARCH-1: all three top-level threads (display, bjorn, web) were created
without daemon=True. A non-daemon thread blocks interpreter exit if the
main thread dies without going through the cleanup path (signal handler
crash, OOM kill, etc.). All three now use daemon=True.

ARCH-2: Bjorn.handle_exit signal handler called handle_exit_display(),
which ended with display_thread.join() + sys.exit(0). The sys.exit
raised SystemExit at the END of handle_exit_display, making the
bjorn_thread/web_thread joins in handle_exit unreachable. Worse,
calling join() from inside a signal handler risks deadlock (the signal
is delivered to the main thread, which is then expected to wait on
another thread while the GIL is held). The handler now only sets flags;
cleanup happens in the main loop / process exit. handle_exit_display
also drops its own join+sys.exit.
"""
import ast
import inspect
import sys
import threading
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# ARCH-1
# ---------------------------------------------------------------------------


class TestDaemonThreads:
    def test_display_thread_created_with_daemon(self):
        """Source-level: start_display must pass daemon=True."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        start = src.index("def start_display")
        end = src.find("\n    @staticmethod", start + 20)
        if end == -1:
            end = src.find("\ndef ", start + 20)
        if end == -1:
            end = len(src)
        method_src = src[start:end]
        assert "daemon=True" in method_src, (
            f"start_display must create the thread with daemon=True (ARCH-1). "
            f"Method:\n{method_src}")

    def test_bjorn_thread_created_with_daemon(self):
        """Source-level: __main__ block must pass daemon=True to bjorn_thread."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        # Find the bjorn_thread creation
        assert "bjorn_thread = threading.Thread(target=bjorn.run, daemon=True)" in src, (
            "bjorn_thread must be created with daemon=True (ARCH-1).")

    def test_web_thread_is_daemon(self):
        """Source-level: WebThread.__init__ must call super().__init__(daemon=True)."""
        with open("webapp.py", encoding="utf-8") as f:
            src = f.read()
        assert "super().__init__(daemon=True)" in src, (
            "WebThread must call super().__init__(daemon=True) (ARCH-1).")

    def test_no_non_daemon_thread_creation_at_top_level(self):
        """AST: in Bjorn.py, every threading.Thread() call at top-level
        (inside __main__ or classmethods) must include daemon=True."""
        with open("Bjorn.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Thread"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "threading"):
                # Look for daemon keyword
                has_daemon = any(
                    kw.arg == "daemon" and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                    for kw in node.keywords
                )
                assert has_daemon, (
                    f"threading.Thread() at line {node.lineno} of Bjorn.py "
                    f"must include daemon=True (ARCH-1).")


# ---------------------------------------------------------------------------
# ARCH-2
# ---------------------------------------------------------------------------


class TestSignalHandlerNoJoinNoExit:
    def _handle_exit_body(self, src):
        """Slice Bjorn.handle_exit method body, bounded by the next
        top-level def OR the __main__ block."""
        start = src.index("def handle_exit(")
        # End at the next top-level def OR __main__ block (whichever first)
        end_candidates = []
        for marker in ["\ndef ", "\nif __name__"]:
            pos = src.find(marker, start + 20)
            if pos != -1:
                end_candidates.append(pos)
        end = min(end_candidates) if end_candidates else len(src)
        return src[start:end]

    def test_handle_exit_does_not_call_join(self):
        """AST: Bjorn.handle_exit must not call .join() — signal handlers
        must not block on thread joins (deadlock risk)."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        method_src = self._handle_exit_body(src)
        assert ".join()" not in method_src, (
            f"handle_exit must not call .join() (ARCH-2). Method:\n{method_src}")

    def test_handle_exit_does_not_call_sys_exit(self):
        """AST: Bjorn.handle_exit must not call sys.exit()."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        method_src = self._handle_exit_body(src)
        assert "sys.exit" not in method_src, (
            f"handle_exit must not call sys.exit (ARCH-2). Method:\n{method_src}")

    def test_handle_exit_does_not_call_handle_exit_display(self):
        """handle_exit must not delegate to handle_exit_display (which used
        to do its own join+sys.exit)."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        method_src = self._handle_exit_body(src)
        assert "handle_exit_display" not in method_src, (
            f"handle_exit must not call handle_exit_display (ARCH-2). "
            f"Method:\n{method_src}")

    def test_handle_exit_display_does_not_sys_exit(self):
        """AST: handle_exit_display must not call sys.exit (the previous
        sys.exit(0) at the end raised SystemExit, making any caller's
        subsequent code unreachable)."""
        with open("display.py", encoding="utf-8") as f:
            src = f.read()
        start = src.index("def handle_exit_display(")
        # End at the next top-level statement
        end = src.find("\n# ", start + 20)
        if end == -1:
            end = src.find("\n\n", start + 20)
        if end == -1:
            end = len(src)
        method_src = src[start:end]
        assert "sys.exit" not in method_src, (
            f"handle_exit_display must not call sys.exit (ARCH-2). "
            f"Method:\n{method_src}")

    def test_handle_exit_display_does_not_join(self):
        """handle_exit_display must not call display_thread.join() (the
        join is the caller's responsibility, and the previous join here
        was dead-redundant with the one in Bjorn.handle_exit)."""
        with open("display.py", encoding="utf-8") as f:
            src = f.read()
        start = src.index("def handle_exit_display(")
        end = src.find("\n# ", start + 20)
        if end == -1:
            end = src.find("\n\n", start + 20)
        if end == -1:
            end = len(src)
        method_src = src[start:end]
        assert ".join()" not in method_src, (
            f"handle_exit_display must not call display_thread.join() "
            f"(ARCH-2). Method:\n{method_src}")
