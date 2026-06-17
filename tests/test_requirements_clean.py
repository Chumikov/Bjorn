"""DEP-1..6: dependency cleanup and dead-code removal.

DEP-1: remove unused packages (RPi.GPIO, ping3, smbprotocol, numpy,
       netifaces).
DEP-2: add gpiozero (used in epdconfig.py but not previously listed).
DEP-3: upgrade Pillow 9.4.0 -> 12.2.0 (CVE-2024-28219), plus spidev,
       pysmb, pymysql, sqlalchemy.
DEP-3b: pin transitive security fixes (cryptography, zipp, pyasn1).
DEP-4: remove DevExtreme CDN (3 MB of unused JS/CSS loaded via CDN with
       no SRI hash).
DEP-5: verify manifest icon paths resolve.
DEP-6: remove dead `from rich.console import Console` imports from 6 files.
"""
import os
import re

import pytest


def _read_requirements():
    with open("requirements.txt", encoding="utf-8") as f:
        return f.read()


def _parse_requirements():
    """Return dict of package -> pinned version string (or None if loose)."""
    pkgs = {}
    for line in _read_requirements().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z0-9_\-.]+)\s*(==|>=|<=|>|<|~=)?\s*([^\s;#]+)?", line)
        if m:
            name = m.group(1).lower()
            op = m.group(2) or ""
            ver = m.group(3) or ""
            pkgs[name] = (op + ver).strip()
    return pkgs


# ---------------------------------------------------------------------------
# DEP-1: unused packages removed
# ---------------------------------------------------------------------------


class TestRemovedPackages:
    @pytest.mark.parametrize("pkg", [
        "rpi.gpio", "ping3", "smbprotocol", "numpy", "netifaces",
    ])
    def test_package_not_in_requirements(self, pkg):
        pkgs = _parse_requirements()
        assert pkg not in pkgs, (
            f"{pkg} should be removed from requirements.txt (DEP-1). "
            f"It is not imported anywhere in the codebase.")

    @pytest.mark.parametrize("pkg", [
        "rpi.gpio", "ping3", "smbprotocol", "numpy", "netifaces",
    ])
    def test_package_not_imported_in_codebase(self, pkg):
        """Sanity: confirm the removed packages are not imported anywhere."""
        pkg_module = pkg.replace("-", "_")
        for root, _, files in os.walk("."):
            if root.startswith(("./.git", "./.pytest_cache", "./__pycache__",
                                "./coverage_html_report", "./backup",
                                "./resources/waveshare_epd")):
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    src = fh.read()
                # Match 'import <pkg>' or 'from <pkg>' (loose)
                pattern = rf"(^|\n)\s*(import|from)\s+{re.escape(pkg_module)}(\.|\s|$)"
                assert not re.search(pattern, src), (
                    f"{pkg} is still imported in {path} — cannot remove from "
                    f"requirements.txt (DEP-1).")


# ---------------------------------------------------------------------------
# DEP-2: gpiozero added
# ---------------------------------------------------------------------------


class TestGpiozeroAdded:
    def test_gpiozero_in_requirements(self):
        pkgs = _parse_requirements()
        assert "gpiozero" in pkgs, (
            "gpiozero must be in requirements.txt (DEP-2). It is imported "
            "in resources/waveshare_epd/epdconfig.py.")


# ---------------------------------------------------------------------------
# DEP-3 + DEP-3b: version upgrades and transitive security pins
# ---------------------------------------------------------------------------


class TestVersionUpgrades:
    @pytest.mark.parametrize("pkg,min_version", [
        ("pillow", "12.2.0"),
        ("spidev", "3.8"),
        ("pysmb", "1.2.14"),
        ("pymysql", "1.2.0"),
        ("sqlalchemy", "2.0.50"),
    ])
    def test_package_upgraded(self, pkg, min_version):
        pkgs = _parse_requirements()
        assert pkg in pkgs, f"{pkg} missing from requirements.txt (DEP-3)."
        ver = pkgs[pkg]
        # Strip operator prefix
        ver_digits = re.sub(r"^[<>=!~]+", "", ver)
        assert ver_digits >= min_version, (
            f"{pkg} must be >= {min_version}; got {ver}")


class TestTransitiveSecurityPins:
    """DEP-3b: transitive deps with security findings must be pinned."""

    @pytest.mark.parametrize("pkg,min_version", [
        ("cryptography", "46.0.5"),
        ("zipp", "3.19.1"),
        ("pyasn1", "0.6.2"),
    ])
    def test_package_pinned(self, pkg, min_version):
        pkgs = _parse_requirements()
        assert pkg in pkgs, (
            f"{pkg} must be in requirements.txt (DEP-3b).")
        ver = pkgs[pkg]
        ver_digits = re.sub(r"^[<>=!~]+", "", ver)
        assert ver_digits >= min_version, (
            f"{pkg} must be >= {min_version}; got {ver}")


# ---------------------------------------------------------------------------
# DEP-4: DevExtreme CDN removed
# ---------------------------------------------------------------------------


class TestDevExtremeRemoved:
    def test_no_devexpress_cdn_in_index_html(self):
        with open("web/index.html", encoding="utf-8") as f:
            src = f.read()
        assert "devexpress" not in src.lower(), (
            "web/index.html must not load DevExtreme from CDN (DEP-4). "
            "It's ~3 MB of unused JS/CSS loaded without SRI hash.")

    def test_no_dx_all_js_in_index_html(self):
        with open("web/index.html", encoding="utf-8") as f:
            src = f.read()
        assert "dx.all.js" not in src, (
            "web/index.html must not reference dx.all.js (DEP-4).")


# ---------------------------------------------------------------------------
# DEP-5: manifest icon paths verify
# ---------------------------------------------------------------------------


class TestManifestIcons:
    def test_all_manifest_icons_exist(self):
        """Manifest references 9 icon sizes; all must exist on disk."""
        import json
        with open("web/manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        for icon in manifest.get("icons", []):
            src_path = icon.get("src", "")
            # Path is relative to manifest.json (web/manifest.json)
            full_path = os.path.join("web", src_path)
            assert os.path.isfile(full_path), (
                f"Manifest icon path does not resolve: {src_path} "
                f"(looked for {full_path})")


# ---------------------------------------------------------------------------
# DEP-6: dead Console imports removed
# ---------------------------------------------------------------------------


class TestNoDeadConsoleImports:
    FILES = [
        "actions/steal_files_ssh.py",
        "actions/steal_files_smb.py",
        "actions/steal_files_rdp.py",
        "actions/steal_files_telnet.py",
        "actions/steal_files_ftp.py",
        "actions/IDLE.py",
    ]

    @pytest.mark.parametrize("path", FILES)
    def test_no_console_import_or_instantiation(self, path):
        with open(path, encoding="utf-8") as f:
            src = f.read()
        assert "from rich.console import Console" not in src, (
            f"{path}: dead 'from rich.console import Console' must be "
            f"removed (DEP-6).")
        assert "Console()" not in src, (
            f"{path}: dead Console() instantiation must be removed (DEP-6).")
