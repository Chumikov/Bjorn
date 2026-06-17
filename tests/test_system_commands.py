"""UTL-3, UTL-4, UTL-5: subprocess modernisation.

UTL-3: reboot_system / shutdown_system / restart_bjorn_service used
subprocess.Popen with stdout/stderr=PIPE but never read the pipes — and
the except CalledProcessError block was dead code because Popen never
raises CalledProcessError (only run(check=True) does). Switched to
subprocess.run with check=True.

UTL-4: scan_wifi's iwgetid call didn't pipe stderr, so communicate()
returned (stdout, None) and on failure the except clause raised
Exception(None).

UTL-5: Popen(...).communicate() is the legacy pattern. The 3 remaining
instances (chmod + nmcli reload x2, Bjorn.py nmcli wifi) switched to
subprocess.run.
"""
import ast
import inspect
import sys
import textwrap
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# UTL-3
# ---------------------------------------------------------------------------


class TestSystemCommandsUseRun:
    def test_reboot_uses_subprocess_run(self):
        from utils import WebUtils
        src = inspect.getsource(WebUtils.reboot_system)
        assert "subprocess.run(" in src, (
            "reboot_system must use subprocess.run (UTL-3).")
        assert "check=True" in src, (
            "reboot_system must use check=True so CalledProcessError fires.")
        # Popen must NOT be in this method anymore
        assert "subprocess.Popen" not in src, (
            "reboot_system must not use subprocess.Popen (UTL-3).")

    def test_shutdown_uses_subprocess_run(self):
        from utils import WebUtils
        src = inspect.getsource(WebUtils.shutdown_system)
        assert "subprocess.run(" in src
        assert "check=True" in src
        assert "subprocess.Popen" not in src

    def test_restart_bjorn_service_uses_subprocess_run(self):
        from utils import WebUtils
        src = inspect.getsource(WebUtils.restart_bjorn_service)
        assert "subprocess.run(" in src
        assert "check=True" in src
        assert "subprocess.Popen" not in src

    def test_reboot_called_process_error_handled(self, mock_handler, mock_shared_data):
        """When subprocess.run raises CalledProcessError, the handler must
        receive a 500 response with the error message (previously dead code)."""
        import subprocess
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        exc = subprocess.CalledProcessError(returncode=1, cmd=['sudo', 'reboot'])
        exc.stderr = "permission denied"
        with patch("utils.subprocess.run", side_effect=exc):
            web_utils.reboot_system(mock_handler)
        assert mock_handler.response_code == 500, (
            f"Expected 500 on CalledProcessError; got {mock_handler.response_code}")

    def test_reboot_success_returns_200(self, mock_handler, mock_shared_data):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())
        with patch("utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            web_utils.reboot_system(mock_handler)
        assert mock_handler.response_code == 200

    def test_shutdown_called_process_error_handled(self, mock_handler, mock_shared_data):
        import subprocess
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())
        exc = subprocess.CalledProcessError(returncode=1, cmd=['sudo', 'shutdown'])
        exc.stderr = "permission denied"
        with patch("utils.subprocess.run", side_effect=exc):
            web_utils.shutdown_system(mock_handler)
        assert mock_handler.response_code == 500

    def test_restart_service_called_process_error_handled(self, mock_handler, mock_shared_data):
        import subprocess
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())
        exc = subprocess.CalledProcessError(returncode=1, cmd=['sudo', 'systemctl'])
        exc.stderr = "service not found"
        with patch("utils.subprocess.run", side_effect=exc):
            web_utils.restart_bjorn_service(mock_handler)
        assert mock_handler.response_code == 500


# ---------------------------------------------------------------------------
# UTL-4
# ---------------------------------------------------------------------------


class TestIwgetidStderrPiped:
    def test_iwgetid_pipes_stderr(self):
        """Source-level: iwgetid call must include stderr=subprocess.PIPE."""
        with open("utils.py", encoding="utf-8") as f:
            src = f.read()
        # Find the iwgetid line
        # The pattern we want: subprocess.Popen(['iwgetid', '-r'], stdout=..., stderr=subprocess.PIPE)
        # The old buggy form was: subprocess.Popen(['iwgetid', '-r'], stdout=PIPE)  -- no stderr
        assert "stderr=subprocess.PIPE" in src, (
            "utils.py must pipe stderr on subprocess calls (UTL-4).")
        # Locate the iwgetid call line specifically and confirm stderr= is on it
        lines = src.splitlines()
        iwgetid_lines = [i for i, line in enumerate(lines) if "iwgetid" in line]
        assert iwgetid_lines, "iwgetid call not found"
        # The call may span multiple lines; check the surrounding 2 lines
        for line_num in iwgetid_lines:
            window = "\n".join(lines[max(0, line_num-1):line_num+2])
            assert "stderr=subprocess.PIPE" in window, (
                f"iwgetid call at line {line_num+1} must include stderr=subprocess.PIPE. "
                f"Window:\n{window}")


# ---------------------------------------------------------------------------
# UTL-5
# ---------------------------------------------------------------------------


class TestNoPopenCommunicatePattern:
    """UTL-5: replace Popen(...).communicate() with subprocess.run()."""

    def test_utils_no_popen_communicate_for_chmod_or_nmcli_reload(self):
        """The specific patterns called out by UTL-5 must be gone from utils.py."""
        with open("utils.py", encoding="utf-8") as f:
            src = f.read()
        # The exact legacy patterns that were called out
        forbidden_patterns = [
            "subprocess.Popen(['sudo', 'chmod', '600', config_path]).communicate()",
            "subprocess.Popen(['sudo', 'nmcli', 'connection', 'reload']).communicate()",
        ]
        for pat in forbidden_patterns:
            assert pat not in src, (
                f"utils.py still contains legacy pattern: {pat!r}")

    def test_bjorn_no_popen_communicate_for_nmcli_wifi(self):
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        forbidden = "subprocess.Popen(['nmcli', '-t', '-f', 'active', 'dev', 'wifi'], stdout=subprocess.PIPE, text=True).communicate()"
        assert forbidden not in src, (
            "Bjorn.py is_wifi_connected must use subprocess.run, not Popen().communicate()")

    def test_bjorn_is_wifi_connected_uses_run(self):
        # AST parse the file directly — avoids the class/module name
        # collision where 'Bjorn' resolves to the class, not the module.
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        start = src.index("def is_wifi_connected")
        # End at the next method def
        end = src.find("\n    def ", start + 20)
        if end == -1:
            end = len(src)
        method_src = src[start:end]
        assert "subprocess.run(" in method_src, (
            "Bjorn.is_wifi_connected must use subprocess.run (UTL-5). "
            f"Source:\n{method_src}")
        assert ".communicate()" not in method_src, (
            "is_wifi_connected must not use the legacy .communicate() pattern.")

    def test_bjorn_is_wifi_connected_reads_stdout(self, mock_shared_data):
        """Behavioral: subprocess.run returns a CompletedProcess whose stdout
        is consulted (was .communicate()[0])."""
        # The project root has __init__.py, so 'Bjorn' is a package.
        # The actual entrypoint module is Bjorn.Bjorn (the .py file).
        import sys as _sys
        bjorn_mod = _sys.modules.get("Bjorn.Bjorn")
        if bjorn_mod is None or not hasattr(bjorn_mod, "Bjorn"):
            try:
                import Bjorn.Bjorn as bjorn_mod
            except ImportError:
                # Fall back to direct file load
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "Bjorn_py", "Bjorn.py")
                bjorn_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bjorn_mod)
        BjornClass = bjorn_mod.Bjorn
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "yes\nno\n"
            mock_run.return_value = mock_result

            b = BjornClass.__new__(BjornClass)
            b.shared_data = mock_shared_data
            result = b.is_wifi_connected()
            assert result is True, (
                "wifi_connected should be True when stdout contains 'yes'")
            mock_run.assert_called_once()

    def test_bjorn_is_wifi_connected_false_on_empty(self, mock_shared_data):
        import sys as _sys
        bjorn_mod = _sys.modules.get("Bjorn.Bjorn")
        if bjorn_mod is None or not hasattr(bjorn_mod, "Bjorn"):
            try:
                import Bjorn.Bjorn as bjorn_mod
            except ImportError:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "Bjorn_py", "Bjorn.py")
                bjorn_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bjorn_mod)
        BjornClass = bjorn_mod.Bjorn
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            b = BjornClass.__new__(BjornClass)
            b.shared_data = mock_shared_data
            assert b.is_wifi_connected() is False
