"""v1.3.1 hotfix: robust RPi platform detection in epdconfig.py.

After RPi OS Bookworm's `apt full-upgrade` (firmware 2024+), some boards
(notably RPi 5 with BCM2712) no longer include the string "Raspberry" in
/proc/cpuinfo. The legacy single-source detection in
resources/waveshare_epd/epdconfig.py fell through to JetsonNano, which
raised RuntimeError('Cannot find sysfs_software_spi.so') and crashed
bjorn.service at startup.

The fix: check multiple sources in order:
  1. /proc/cpuinfo (legacy)
  2. /etc/rpi-issue (every official RPi OS image)
  3. /proc/device-tree/model (new mainline kernels)

This test verifies the multi-source logic exists and is called.
"""
import ast
import os

import pytest


EPCONFIG_PATH = "resources/waveshare_epd/epdconfig.py"


class TestRobustPlatformDetection:
    def test_is_raspberry_pi_helper_exists(self):
        """The _is_raspberry_pi helper must be defined."""
        with open(EPCONFIG_PATH, encoding="utf-8") as f:
            src = f.read()
        assert "def _is_raspberry_pi()" in src, (
            "epdconfig.py must define _is_raspberry_pi() helper (v1.3.1).")

    def test_uses_helper_for_rpi_branch(self):
        """The RaspberryPi branch must be selected via _is_raspberry_pi()."""
        with open(EPCONFIG_PATH, encoding="utf-8") as f:
            src = f.read()
        assert "if _is_raspberry_pi():" in src, (
            "RaspberryPi branch must be selected via _is_raspberry_pi() call.")

    def test_helper_checks_multiple_sources(self):
        """The helper must check at least 3 sources for RPi identity."""
        with open(EPCONFIG_PATH, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        # Find _is_raspberry_pi function body
        for node in ast.walk(tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name == "_is_raspberry_pi"):
                # Collect all string literals / file paths it references
                src_snippet = ast.dump(node)
                # Must reference all three signals
                assert "/proc/cpuinfo" in src_snippet or "Raspberry" in src_snippet, (
                    "_is_raspberry_pi must consult /proc/cpuinfo")
                assert "/etc/rpi-issue" in src_snippet, (
                    "_is_raspberry_pi must check /etc/rpi-issue (firmware-2024+ "
                    "may drop 'Raspberry' from /proc/cpuinfo on RPi 5)")
                assert "/proc/device-tree/model" in src_snippet, (
                    "_is_raspberry_pi must check /proc/device-tree/model")
                return
        pytest.fail("_is_raspberry_pi helper not found")

    def test_no_legacy_single_source_check_only(self):
        """The old pattern 'if \"Raspberry\" in output:' alone must be gone."""
        with open(EPCONFIG_PATH, encoding="utf-8") as f:
            src = f.read()
        # The exact legacy line must NOT be a top-level branch selector
        # (it's still OK inside the helper, but not as the if/elif selector)
        assert "if \"Raspberry\" in output:\n    implementation = RaspberryPi()" not in src, (
            "Legacy single-source 'if \"Raspberry\" in output:' selector must "
            "be replaced by _is_raspberry_pi() helper.")

    def test_rpi_issue_present_on_this_machine(self):
        """Sanity: confirm /etc/rpi-issue is the right thing to check on RPi.
        On this dev host (not RPi) the file should not exist; on RPi it does."""
        # This test passes on any machine — it's a behavioural sanity check
        # of os.path.exists semantics. The point is to document where
        # /etc/rpi-issue comes from.
        rpi_issue_exists = os.path.exists("/etc/rpi-issue")
        # Document: on non-RPi (this dev host), should be False
        if not rpi_issue_exists:
            return  # expected on dev hosts
        # If it exists, sanity-check it looks like a pi-gen output
        with open("/etc/rpi-issue") as f:
            content = f.read()
        assert "pi-gen" in content or "Raspberry Pi" in content, (
            f"/etc/rpi-issue looks malformed: {content!r}")
