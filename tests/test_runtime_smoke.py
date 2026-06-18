"""Runtime smoke tests: catch regressions that AST/source checks can
detect before they cause crash-loops on real hardware.

Each test guards against a specific bug discovered during v1.3.x
deployment on real RPi hardware (BCM2712). Source-level checks cannot
catch every runtime bug, but they catch the cheap-to-detect structural
mistakes that caused three consecutive hotfix releases (v1.3.1, v1.3.2,
v1.3.3).
"""
import subprocess
import textwrap

import pytest


# ---------------------------------------------------------------------------
# v1.3.2 regression: executable bit on systemd Exec* scripts
# ---------------------------------------------------------------------------


class TestExecutableBitsInGit:
    """v1.3.2: scripts referenced in bjorn.service ExecStartPre/ExecStart
    must be executable (100755) in git index. Otherwise systemd fails
    with status=203/EXEC before Python even starts.

    Discovered when 'git checkout v1.3.0' on the RPi SD card reset the
    executable bit that install_bjorn.sh had set via 'chmod -R 755'.
    Fix: 'git update-index --chmod=+x' on each script.
    """

    SCRIPTS = [
        "kill_port_8000.sh",  # ExecStartPre — canonical offender
        "wifi_fix.sh",
        "Bjorn.py",
    ]

    @pytest.mark.parametrize("path", SCRIPTS)
    def test_script_has_executable_mode_in_git(self, path):
        """git ls-files -s must show 100755, not 100644.

        On the dev machine the working-tree file may be 0644 even when
        git mode is 100755 (git doesn't apply index mode to existing
        files). What matters for production is the git mode, because
        'git checkout' on the RPi will create the file with that mode.
        install_bjorn.sh additionally runs 'chmod -R 755' as belt-and-
        braces.
        """
        result = subprocess.run(
            ["git", "ls-files", "-s", path],
            capture_output=True, text=True, check=True,
        )
        if not result.stdout.strip():
            pytest.skip(f"{path} is not tracked by git")
        mode = result.stdout.split()[0]
        assert mode == "100755", (
            f"{path} must be 100755 in git index (was {mode}). Without "
            f"the executable bit, systemd ExecStartPre fails with "
            f"status=203/EXEC before Python starts. "
            f"Fix: git update-index --chmod=+x {path}")


# ---------------------------------------------------------------------------
# v1.3.3 regression: main thread must wait (join) for worker threads
# ---------------------------------------------------------------------------


class TestThreadingLifecycle:
    """v1.3.3: main thread must call .join() on a worker thread, otherwise
    the process exits immediately after __main__ finishes registering
    signal handlers and the daemon worker threads die with it. Symptom:
    crash-loop every ~8 seconds, black screen, 'Starting the web server...'
    as the last entry in Bjorn.py.log.
    """

    def test_main_block_has_join_call(self):
        """Bjorn.py __main__ must call .join() on a worker thread."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        assert 'if __name__ == "__main__"' in src, (
            "Bjorn.py must have a __main__ block")
        main_block = src[src.index('if __name__ == "__main__":'):]
        assert ".join(" in main_block, (
            "__main__ block must call .join() on a worker thread — "
            "otherwise main exits immediately and worker threads die "
            "with it (crash-loop on real hardware, fixed in v1.3.3).")

    def test_no_daemon_on_bjorn_thread(self):
        """The core worker thread must NOT be created with daemon=True.
        Daemon + no main join = process exits immediately."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        normalized_src = " ".join(src.split())
        forbidden = " ".join(
            "bjorn_thread = threading.Thread(target=bjorn.run, daemon=True)".split())
        assert forbidden not in normalized_src, (
            "Found daemon=True on bjorn_thread. This caused a crash-loop "
            "in v1.3.0 (hotfixed in v1.3.3): the main thread exited "
            "immediately after registering signal handlers, and the daemon "
            "bjorn_thread died with the process. Use non-daemon + "
            "bjorn_thread.join() instead.")

    def test_no_daemon_on_display_thread(self):
        """The display thread must NOT be created with daemon=True."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        # Find start_display method body
        assert "def start_display" in src
        start = src.index("def start_display")
        # End at the next @staticmethod or def at class level
        end_candidates = []
        for marker in ["\n    @staticmethod", "\n    def ", "\ndef "]:
            pos = src.find(marker, start + 20)
            if pos != -1:
                end_candidates.append(pos)
        end = min(end_candidates) if end_candidates else len(src)
        method_src = src[start:end]
        # Normalize whitespace
        normalized = " ".join(method_src.split())
        # Forbidden: threading.Thread(target=display.run, daemon=True)
        assert "daemon=True" not in normalized, (
            f"start_display creates a daemon thread. This caused a "
            f"crash-loop in v1.3.0 (hotfixed in v1.3.3). Use non-daemon "
            f"thread + main join. Method:\n{textwrap.dedent(method_src)}")

    def test_no_daemon_on_web_thread(self):
        """WebThread.__init__ must NOT call super().__init__(daemon=True)."""
        with open("webapp.py", encoding="utf-8") as f:
            src = f.read()
        assert "class WebThread" in src
        # Slice WebThread class up to the first def _bind_address or similar
        start = src.index("class WebThread")
        end_marker_candidates = [
            src.find("\n    def _bind_address", start),
            src.find("\n    def run", start),
            src.find("\ndef handle_exit_web", start),
        ]
        end_marker_candidates = [e for e in end_marker_candidates if e != -1]
        end = min(end_marker_candidates) if end_marker_candidates else len(src)
        class_src = src[start:end]
        normalized = " ".join(class_src.split())
        forbidden = "super().__init__(daemon=True)"
        assert forbidden not in normalized, (
            f"WebThread.__init__ uses super().__init__(daemon=True). "
            f"This caused a crash-loop in v1.3.0 (hotfixed in v1.3.3). "
            f"Use super().__init__() (non-daemon) + main join.")


# ---------------------------------------------------------------------------
# v1.3.1 regression: platform detection must be multi-source
# ---------------------------------------------------------------------------


class TestPlatformDetection:
    """v1.3.1: /proc/cpuinfo no longer contains 'Raspberry' on RPi 5 with
    firmware 2024+. Platform detection that checks only one source falls
    through to JetsonNano, which crashes on missing sysfs_software_spi.so.
    """

    def test_is_raspberry_pi_helper_exists(self):
        """resources/waveshare_epd/epdconfig.py must define
        _is_raspberry_pi() helper that checks multiple sources."""
        with open("resources/waveshare_epd/epdconfig.py", encoding="utf-8") as f:
            src = f.read()
        assert "def _is_raspberry_pi()" in src, (
            "epdconfig.py must define _is_raspberry_pi() helper. "
            "Discovered in v1.3.1: single-source /proc/cpuinfo check "
            "breaks on RPi 5 with firmware 2024+.")

    def test_helper_checks_rpi_issue(self):
        """The helper must check /etc/rpi-issue (present on every official
        RPi OS image, regardless of firmware version)."""
        with open("resources/waveshare_epd/epdconfig.py", encoding="utf-8") as f:
            src = f.read()
        assert "/etc/rpi-issue" in src, (
            "Platform detection must check /etc/rpi-issue. This file "
            "exists on every RPi OS image generated by pi-gen and is "
            "not affected by firmware upgrades.")


# ---------------------------------------------------------------------------
# General structural checks
# ---------------------------------------------------------------------------


class TestBjornServiceReferences:
    """Verify that paths referenced in the bjorn.service template
    (in install_bjorn.sh) correspond to files that exist in the repo."""

    def test_kill_port_8000_script_exists(self):
        """kill_port_8000.sh is referenced in ExecStartPre and is the
        canonical offender when executable bits get reset. Make sure it
        exists in the repo."""
        import os
        assert os.path.isfile("kill_port_8000.sh"), (
            "kill_port_8000.sh must exist in repo root — it is referenced "
            "as ExecStartPre in bjorn.service.")

    def test_bjorn_py_exists(self):
        import os
        assert os.path.isfile("Bjorn.py"), (
            "Bjorn.py must exist in repo root — it is the ExecStart target.")

    def test_wifi_fix_script_exists(self):
        """wifi_fix.sh is referenced in install_bjorn.sh and runs on boot
        to fix Wi-Fi country-code issues. Must exist and be +x."""
        import os
        assert os.path.isfile("wifi_fix.sh"), (
            "wifi_fix.sh must exist in repo root — it is invoked during "
            "install and on boot.")


# ---------------------------------------------------------------------------
# Installer apt dependencies — guards against silent CLI tool removal
# ---------------------------------------------------------------------------


class TestInstallerDeps:
    """Verify install_bjorn.sh apt list includes CLI tools the Python code
    shells out to. Without these the runtime fails with FileNotFoundError
    even though pip install succeeded.

    Each entry below is a CLI tool invoked via subprocess in the Python
    code. If someone refactors the packages array and accidentally drops
    one, this test fails with a clear message pointing at the call site.
    """

    @pytest.mark.parametrize("pkg,reason", [
        ("smbclient",       "actions/smb_connector.py:128 (smbclient -L fallback)"),
        ("wireless-tools",  "utils.py:532,538 (iwlist scan, iwgetid -r)"),
        ("nmap",            "scanning.py + nmap_vuln_scanner.py (already required)"),
        ("lsof",            "bjorn.service ExecStartPost FD monitor (already required)"),
    ])
    def test_apt_package_listed(self, pkg, reason):
        """Each CLI tool invoked via subprocess must have its apt package
        declared in install_bjorn.sh's packages array."""
        with open("install_bjorn.sh", encoding="utf-8") as f:
            src = f.read()
        # The packages array uses double-quoted strings; check exact match
        # to avoid partial hits like 'lsof' inside 'libopenblas'.
        pattern = f'"{pkg}"'
        assert pattern in src, (
            f"install_bjorn.sh must include {pattern} in its apt packages "
            f"list. Reason: {reason}. The Python code shells out to this "
            f"CLI tool via subprocess; without the apt package the runtime "
            f"fails with FileNotFoundError even though pip install succeeded.")
