"""ARCH-1, ARCH-2, ARCH-3 (v1.3.3): thread lifecycle + signal handler.

ARCH-1 (v1.3.0, REVERTED in v1.3.3): marked all top-level threads
daemon=True. On real hardware this caused a crash-loop: main thread
exited the __main__ block immediately after registering signal handlers
(no join/wait), and since all worker threads were daemon, the process
exited too. systemd Restart=always re-spawned the service every ~8s.

v1.3.3 reverts ARCH-1: display_thread, bjorn_thread, orchestrator_thread
and WebThread are all non-daemon (matching the original v1.2.0 behaviour).
The __main__ block now ends with bjorn_thread.join() so the main thread
blocks until the core worker exits — providing a clean shutdown path
without the crash-loop.

ARCH-2 (v1.3.0, kept): handle_exit signal handler must not call join()
or sys.exit(). Set flags only.
"""
import ast
import pytest


# ---------------------------------------------------------------------------
# ARCH-1 (v1.3.3): non-daemon worker threads
# ---------------------------------------------------------------------------


class TestNonDaemonThreads:
    def test_display_thread_is_non_daemon(self):
        """start_display must NOT pass daemon=True (caused crash-loop)."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        start = src.index("def start_display")
        end = src.find("\n    @staticmethod", start + 20)
        if end == -1:
            end = src.find("\ndef ", start + 20)
        if end == -1:
            end = len(src)
        method_src = src[start:end]
        assert "daemon=True" not in method_src, (
            f"start_display must NOT use daemon=True (v1.3.3 revert of "
            f"ARCH-1; daemon threads caused the process to exit immediately "
            f"on real hardware). Method:\n{method_src}")

    def test_bjorn_thread_is_non_daemon(self):
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        assert "bjorn_thread = threading.Thread(target=bjorn.run)\n" in src, (
            "bjorn_thread must be created WITHOUT daemon=True (v1.3.3). "
            "It's the core worker; daemonising it caused crash-loop.")
        assert "bjorn_thread = threading.Thread(target=bjorn.run, daemon=True)" not in src, (
            "Found daemon=True on bjorn_thread — must be removed (v1.3.3).")

    def test_orchestrator_thread_is_non_daemon(self):
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        # Find start_orchestrator body
        start = src.index("def start_orchestrator")
        end = src.find("\n    def ", start + 20)
        if end == -1:
            end = len(src)
        method_src = src[start:end]
        assert "daemon=True" not in method_src, (
            f"orchestrator_thread must NOT be daemon (v1.3.3). "
            f"Method:\n{method_src}")

    def test_web_thread_is_non_daemon(self):
        """WebThread.__init__ must NOT call super().__init__(daemon=True)."""
        with open("webapp.py", encoding="utf-8") as f:
            src = f.read()
        # Find WebThread.__init__ body
        start = src.index("class WebThread")
        end = src.find("def _bind_address", start)
        method_src = src[start:end]
        assert "super().__init__(daemon=True)" not in method_src, (
            f"WebThread must NOT use super().__init__(daemon=True) (v1.3.3). "
            f"Section:\n{method_src}")
        assert "super().__init__()" in method_src, (
            "WebThread.__init__ must call super().__init__() (non-daemon)")

    def test_main_block_joins_bjorn_thread(self):
        """The __main__ block must end with bjorn_thread.join() so the
        main thread doesn't exit while worker threads are still running.
        Without this join, even non-daemon threads would print 'Starting
        the web server...' and exit before the service does any work."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        # Find the __main__ block
        main_start = src.index('if __name__ == "__main__":')
        main_body = src[main_start:]
        assert "bjorn_thread.join()" in main_body, (
            "__main__ must call bjorn_thread.join() so main thread blocks "
            "until the core worker exits (prevents the v1.3.0 crash-loop).")


# ---------------------------------------------------------------------------
# ARCH-2 (kept): signal handler sets flags only
# ---------------------------------------------------------------------------


class TestSignalHandlerNoJoinNoExit:
    def _handle_exit_body(self, src):
        """Slice Bjorn.handle_exit method body, bounded by the next
        top-level def OR the __main__ block."""
        start = src.index("def handle_exit(")
        end_candidates = []
        for marker in ["\ndef ", "\nif __name__"]:
            pos = src.find(marker, start + 20)
            if pos != -1:
                end_candidates.append(pos)
        end = min(end_candidates) if end_candidates else len(src)
        return src[start:end]

    def test_handle_exit_does_not_call_join(self):
        """handle_exit must not call .join() — signal handlers must not
        block on thread joins (deadlock risk)."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        method_src = self._handle_exit_body(src)
        assert ".join()" not in method_src, (
            f"handle_exit must not call .join() (ARCH-2). Method:\n{method_src}")

    def test_handle_exit_does_not_call_sys_exit(self):
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        method_src = self._handle_exit_body(src)
        assert "sys.exit" not in method_src, (
            f"handle_exit must not call sys.exit (ARCH-2). Method:\n{method_src}")

    def test_handle_exit_does_not_call_handle_exit_display(self):
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        method_src = self._handle_exit_body(src)
        assert "handle_exit_display" not in method_src, (
            f"handle_exit must not call handle_exit_display (ARCH-2). "
            f"Method:\n{method_src}")

    def test_handle_exit_display_does_not_sys_exit(self):
        """display.handle_exit_display must not call sys.exit (was making
        caller's subsequent code unreachable via SystemExit)."""
        with open("display.py", encoding="utf-8") as f:
            src = f.read()
        start = src.index("def handle_exit_display(")
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
