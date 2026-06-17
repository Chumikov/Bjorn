"""UTL-2: tail -f process and file handle leak in serve_logs().

Popen(['tail', '-f', ...]) and open(path, 'w') were never tracked or
closed. Every call to /get_logs (where the log file didn't yet exist)
spawned an immortal tail process and a leaked file descriptor. On a
long-running service this directly caused OSError: [Errno 24] Too many
open files.

The fix tracks the process and file handle on the instance and adds
cleanup_tail() to terminate them.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestTailProcessTracking:
    def test_cleanup_tail_method_exists(self):
        from utils import WebUtils
        assert hasattr(WebUtils, "cleanup_tail"), (
            "WebUtils must define cleanup_tail() so serve_logs() resources "
            "can be released.")

    def test_serve_logs_tracks_tail_process_attribute(self):
        """Source-level: serve_logs must assign self._tail_process."""
        with open("utils.py", encoding="utf-8") as f:
            src = f.read()
        assert "self._tail_process" in src, (
            "serve_logs() must track the tail process as self._tail_process")
        assert "self._tail_log_fh" in src, (
            "serve_logs() must track the file handle as self._tail_log_fh")

    def test_cleanup_tail_terminates_process(self):
        """cleanup_tail must call terminate() + wait() on the process."""
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        # Build a fake process
        proc = MagicMock()
        proc.terminate = MagicMock()
        proc.wait = MagicMock()
        proc.kill = MagicMock()
        fh = MagicMock()
        fh.close = MagicMock()
        web_utils._tail_process = proc
        web_utils._tail_log_fh = fh

        web_utils.cleanup_tail()

        proc.terminate.assert_called_once()
        proc.wait.assert_called_once()
        fh.close.assert_called_once()
        # Both attributes must be cleared so a second call is a no-op
        assert web_utils._tail_process is None
        assert web_utils._tail_log_fh is None

    def test_cleanup_tail_safe_when_nothing_tracked(self):
        """cleanup_tail on a fresh instance must not raise."""
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        # No _tail_process / _tail_log_fh attributes set
        web_utils.cleanup_tail()  # must not raise

    def test_cleanup_tail_falls_back_to_kill_if_terminate_hangs(self):
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        proc = MagicMock()
        proc.terminate = MagicMock()
        proc.wait.side_effect = TimeoutError("simulated hang")
        proc.kill = MagicMock()
        web_utils._tail_process = proc

        web_utils.cleanup_tail()  # must not raise

        proc.terminate.assert_called_once()
        proc.kill.assert_called_once(), (
            "cleanup_tail must fall back to kill() if terminate+wait times out")

    def test_serve_logs_does_not_spawn_repeated_tail_processes(
            self, mock_shared_data, tmp_path):
        """Calling serve_logs() twice should not spawn two tail processes.

        We verify by patching subprocess.Popen to count invocations."""
        # Set up: log file doesn't exist initially, and glob returns at
        # least one log file so the spawn branch fires.
        log_target = tmp_path / "console.log"
        mock_shared_data.webconsolelog = str(log_target)
        # Stub glob return so we don't depend on /home/bjorn/Bjorn/...
        with patch("utils.glob.glob", return_value=[str(tmp_path / "x.log")]):
            from utils import WebUtils
            web_utils = WebUtils(mock_shared_data, MagicMock())
            popen_calls = []
            with patch("utils.subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_popen.return_value = mock_proc
                # Wrap Popen to count and capture
                def _popen(*args, **kw):
                    popen_calls.append(args)
                    return mock_proc
                mock_popen.side_effect = _popen

                # First call: log file doesn't exist yet -> spawns tail
                handler1 = MagicMock()
                handler1.headers = {}
                handler1.rfile = MagicMock()
                web_utils.serve_logs(handler1)
                assert len(popen_calls) == 1, (
                    f"First serve_logs should spawn 1 tail; got {len(popen_calls)}")
                # The instance must now have _tail_process set
                assert web_utils._tail_process is mock_proc

                # Second call: cleanup_tail between calls should leave
                # _tail_process cleared so a subsequent spawn is allowed
                web_utils.cleanup_tail()
                assert web_utils._tail_process is None

                # Third call: log file exists now (we wrote to it), so
                # the spawn branch should not fire again.
                handler2 = MagicMock()
                web_utils.serve_logs(handler2)
                # Still only 1 spawn total (the log file now exists)
                assert len(popen_calls) == 1, (
                    f"Second serve_logs (after log exists) should not spawn; "
                    f"got {len(popen_calls)} total calls")
