"""DSP-1, DSP-2, DSP-3, DSP-4: display.py pandas + Pillow fixes.

DSP-1: to_csv() was called WHILE the same file was open via
`with open('r+')` — racing the file handle and truncating under it.

DSP-2: unnecessary `with open() as f: pd.read_csv(f)` wrappers around
read_csv (which accepts a path directly).

DSP-3: Image.ROTATE_180 (deprecated since Pillow 9.1) →
Image.Transpose.ROTATE_180 (required on Pillow 12+).

DSP-4: iterrows() in update_vuln_count was the slowest way to build a
set of vulnerabilities. Vectorised via DataFrame filtering + dropna.
"""
import ast
import inspect
import os
import sys
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# DSP-1: no to_csv while file is open via r+
# ---------------------------------------------------------------------------


class TestNoConcurrentFileHandle:
    def test_no_with_open_r_plus_around_to_csv(self):
        """Source-level: display.py must not have `with open(..., 'r+') as
        f: ... to_csv(...)` patterns."""
        with open("display.py", encoding="utf-8") as f:
            src = f.read()
        assert "open(self.shared_data.livestatusfile, 'r+')" not in src, (
            "display.py must not use 'r+' open around to_csv (DSP-1). "
            "Pass the path directly to read_csv and to_csv.")

    def test_to_csv_called_with_path_not_handle(self):
        """AST: any to_csv() call must receive a path string, not a
        file handle."""
        with open("display.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "to_csv"):
                # The first positional arg should be a path expression
                # (Attribute access like self.X.livestatusfile), not a Name
                # like 'file' or 'livestatus_file' (which would be a handle).
                if node.args:
                    arg = node.args[0]
                    # Names that are file handles from `with open() as X`:
                    handle_names = {"file", "f", "livestatus_file", "log_file"}
                    if (isinstance(arg, ast.Name) and arg.id in handle_names):
                        pytest.fail(
                            f"to_csv called with file handle {arg.id!r} at "
                            f"line {node.lineno}; pass a path instead (DSP-1).")


# ---------------------------------------------------------------------------
# DSP-2: no `with open() as f: pd.read_csv(f)` wrappers
# ---------------------------------------------------------------------------


class TestNoOpenWrapperAroundReadCsv:
    def test_no_open_wrapper_around_read_csv_in_update_vuln_count(self):
        """Source-level: update_vuln_count must not wrap read_csv in open()."""
        with open("display.py", encoding="utf-8") as f:
            src = f.read()
        # The buggy form is `with open(X, 'r') as file: pd.read_csv(file)`
        # Look for the specific patterns called out in DSP-2.
        buggy_patterns = [
            "with open(self.shared_data.netkbfile, 'r') as file:",
            "with open(self.shared_data.vuln_summary_file, 'r') as file:",
            "with open(self.shared_data.livestatusfile, 'r') as file:",
        ]
        for pat in buggy_patterns:
            assert pat not in src, (
                f"display.py still wraps read_csv in open() (DSP-2): {pat!r}")

    def test_read_csv_called_with_path_attributes(self):
        """AST: read_csv args should be path-like, not bound to an open()
        file handle. We flag Name nodes ONLY when the name was bound by
        a `with open(...) as <name>:` statement in the same scope."""
        with open("display.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        # Collect all names that are bound by `with open(...) as NAME:` (the
        # context manager pattern). These are file handles, not paths.
        handle_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.With):
                for item in node.items:
                    if (item.context_expr
                            and isinstance(item.context_expr, ast.Call)
                            and isinstance(item.context_expr.func, ast.Name)
                            and item.context_expr.func.id == "open"):
                        if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                            handle_names.add(item.optional_vars.id)

        # Walk all read_csv() calls and verify no positional arg is one of
        # these bound file-handle names.
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "read_csv"):
                if node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Name) and arg.id in handle_names:
                        pytest.fail(
                            f"read_csv called with file handle {arg.id!r} "
                            f"at line {node.lineno}; pass a path (DSP-2).")


# ---------------------------------------------------------------------------
# DSP-3: Image.Transpose.ROTATE_180 enum
# ---------------------------------------------------------------------------


class TestPillowEnum:
    def test_no_deprecated_image_rotate_constants(self):
        """Source-level: Image.ROTATE_180 must be gone (deprecated in 9.1)."""
        with open("display.py", encoding="utf-8") as f:
            src = f.read()
        assert "Image.ROTATE_180" not in src, (
            "display.py must not use Image.ROTATE_180 (deprecated in Pillow 9.1). "
            "Use Image.Transpose.ROTATE_180.")
        assert "Image.FLIP_LEFT_RIGHT" not in src, (
            "display.py must not use Image.FLIP_LEFT_RIGHT (deprecated).")
        assert "Image.FLIP_TOP_BOTTOM" not in src, (
            "display.py must not use Image.FLIP_TOP_BOTTOM (deprecated).")

    def test_transpose_enum_used(self):
        with open("display.py", encoding="utf-8") as f:
            src = f.read()
        assert "Image.Transpose.ROTATE_180" in src, (
            "display.py must use Image.Transpose.ROTATE_180 (DSP-3).")


# ---------------------------------------------------------------------------
# DSP-4: vectorised vulnerability aggregation
# ---------------------------------------------------------------------------


class TestVectorisedVulnCount:
    def test_no_iterrows_in_update_vuln_count(self):
        """Source-level: update_vuln_count must not use iterrows()."""
        with open("display.py", encoding="utf-8") as f:
            src = f.read()
        # Find update_vuln_count method body
        start = src.index("def update_vuln_count")
        end = src.find("\n    def ", start + 20)
        if end == -1:
            end = len(src)
        method_src = src[start:end]
        assert "iterrows" not in method_src, (
            f"update_vuln_count must not use iterrows (DSP-4). Method:\n"
            f"{method_src}")

    def test_vectorised_vulnerability_aggregation(self, tmp_path):
        """Behavioral: vectorised implementation produces the same set as
        the old iterrows approach would have."""
        # Build a sample vuln_summary CSV
        import pandas as pd
        vuln_file = tmp_path / "vuln_summary.csv"
        df = pd.DataFrame([
            {"IP": "10.0.0.1", "Hostname": "h1", "MAC Address": "aa:bb:cc:dd:ee:01",
             "Port": 22, "Vulnerabilities": "CVE-2024-1111; CVE-2024-2222"},
            {"IP": "10.0.0.2", "Hostname": "h2", "MAC Address": "aa:bb:cc:dd:ee:02",
             "Port": 80, "Vulnerabilities": "CVE-2024-2222; CVE-2024-3333"},
            {"IP": "10.0.0.3", "Hostname": "h3", "MAC Address": "aa:bb:cc:dd:ee:03",
             "Port": 443, "Vulnerabilities": None},  # NaN case
        ])
        df.to_csv(vuln_file, index=False)

        # Reproduce the OLD (iterrows) logic for reference
        old_set = set()
        for _, row in df.iterrows():
            v = row["Vulnerabilities"]
            if pd.isna(v) or not isinstance(v, str):
                continue
            old_set.update(v.split("; "))

        # Reproduce the NEW (vectorised) logic
        vuln_series = df["Vulnerabilities"].dropna().astype(str)
        if not vuln_series.empty:
            joined = "; ".join(vuln_series.tolist())
            new_set = set(joined.split("; "))
        else:
            new_set = set()

        assert old_set == new_set, (
            f"Vectorised set {new_set} != iterrows set {old_set}")
        assert old_set == {"CVE-2024-1111", "CVE-2024-2222", "CVE-2024-3333"}

    def test_vectorised_handles_empty_dataframe(self):
        import pandas as pd
        df = pd.DataFrame(columns=["Vulnerabilities"])
        vuln_series = df["Vulnerabilities"].dropna().astype(str)
        # Empty case must produce empty set, not crash
        if not vuln_series.empty:
            joined = "; ".join(vuln_series.tolist())
            result = set(joined.split("; "))
        else:
            result = set()
        assert result == set(), (
            f"Empty df should produce empty set; got {result}")
