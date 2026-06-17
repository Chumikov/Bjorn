"""NMAP-1: nmap_vuln_scanner groupby crash on NaN.

save_summary() used 'lambda x: \"; \".join(x)' inside groupby.apply().
When the Vulnerabilities column contained any NaN (a float, arising from
empty cells in the source CSV), str.join raised
'TypeError: sequence item ...: expected str instance, float found'.
The exception was silently swallowed by the broad except clause, so the
final summary file was simply never written.

The fix: dropna() inside the lambda filters NaN values before joining.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest


class TestGroupbyHandlesNaN:
    def test_dropna_present_in_save_summary(self):
        """Source-level: save_summary must call x.dropna() before joining."""
        with open("actions/nmap_vuln_scanner.py", encoding="utf-8") as f:
            src = f.read()
        assert "x.dropna()" in src, (
            "save_summary must call x.dropna() inside the groupby lambda "
            "to filter NaN values (NMAP-1).")

    def test_save_summary_with_nan_vulnerabilities(self, tmp_path):
        """End-to-end: save_summary must NOT raise on a CSV with empty
        Vulnerabilities cells (was silently failing)."""
        import pandas as pd

        # Build a summary CSV with mixed real + NaN Vulnerabilities
        summary_file = tmp_path / "vuln_summary.csv"
        df = pd.DataFrame([
            {"IP": "10.0.0.1", "Hostname": "h1", "MAC Address": "aa:01",
             "Port": 22, "Vulnerabilities": "CVE-2024-1111; CVE-2024-2222"},
            {"IP": "10.0.0.1", "Hostname": "h1", "MAC Address": "aa:01",
             "Port": 80, "Vulnerabilities": None},  # NaN
            {"IP": "10.0.0.2", "Hostname": "h2", "MAC Address": "aa:02",
             "Port": 443, "Vulnerabilities": "CVE-2024-2222"},
            {"IP": "10.0.0.3", "Hostname": "h3", "MAC Address": "aa:03",
             "Port": 8080, "Vulnerabilities": None},  # all-NaN group
        ])
        df.to_csv(summary_file, index=False)

        # Construct an NmapVulnScanner via __new__ (skip __init__)
        sys.modules.pop("actions.nmap_vuln_scanner", None)
        from actions.nmap_vuln_scanner import NmapVulnScanner
        scanner = NmapVulnScanner.__new__(NmapVulnScanner)
        shared = MagicMock()
        shared.vulnerabilities_dir = str(tmp_path)
        scanner.shared_data = shared
        scanner.summary_file = str(summary_file)

        # Run save_summary — must not raise and must produce a CSV
        scanner.save_summary()

        out_path = os.path.join(str(tmp_path), "final_vulnerability_summary.csv")
        assert os.path.exists(out_path), (
            f"save_summary should write the final summary file; "
            f"{out_path} does not exist")

        # The output should have one row per (IP, Hostname, MAC) group.
        # Group 10.0.0.1: had 'CVE-2024-1111; CVE-2024-2222' and NaN -> the
        # 2 CVEs should be present.
        out_df = pd.read_csv(out_path)
        groups = out_df.set_index("IP")
        vuln_1 = groups.loc["10.0.0.1", "Vulnerabilities"]
        assert "CVE-2024-1111" in vuln_1, f"Missing CVE in group 1: {vuln_1}"
        assert "CVE-2024-2222" in vuln_1, f"Missing CVE in group 1: {vuln_1}"
        # Group 10.0.0.3 had only NaN — the join of an empty series is "".
        # (set("".split("; ")) = {''}, joined -> ''. Acceptable; the point
        # is no TypeError.)
        assert "10.0.0.3" in groups.index, (
            "All-NaN group should still be in output (NMAP-1 prevents crash)")

    def test_old_pattern_would_crash_on_nan(self):
        """Sanity: confirm the OLD pattern actually crashes on NaN, so the
        new pattern's dropna() is necessary."""
        import pandas as pd
        df = pd.DataFrame([
            {"IP": "10.0.0.1", "Vulnerabilities": "CVE-X"},
            {"IP": "10.0.0.1", "Vulnerabilities": None},
        ])
        # The old lambda (no dropna) WOULD crash:
        with pytest.raises(TypeError) as exc_info:
            df.groupby("IP")["Vulnerabilities"].apply(
                lambda x: "; ".join(set("; ".join(x).split("; ")))
            )
        # Confirm it's the TypeError we expect (sequence item is float)
        assert "float" in str(exc_info.value) or "str instance" in str(exc_info.value)

        # The NEW lambda (with dropna) handles it:
        result = df.groupby("IP")["Vulnerabilities"].apply(
            lambda x: "; ".join(set("; ".join(x.dropna()).split("; ")))
        )
        assert "10.0.0.1" in result.index
        assert "CVE-X" in result.loc["10.0.0.1"]
