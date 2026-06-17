"""PND-1..PND-5: replace .values[0] with .iloc[0].

The pattern `df.loc[...].values[0]` was used in all 5 connectors
(ssh/ftp/smb/telnet/rdp) to look up a row by IP and grab a single cell.
.values[0] is not recommended per pandas docs and raises the wrong
exception type (IndexError on the indexing, not on the .loc filter).
.iloc[0] is canonical and behaves the same when at least one row matches.
"""
import os

import pytest


CONNECTOR_FILES = [
    "actions/ssh_connector.py",
    "actions/ftp_connector.py",
    "actions/smb_connector.py",
    "actions/telnet_connector.py",
    "actions/rdp_connector.py",
]


class TestNoValuesZeroPattern:
    @pytest.mark.parametrize("path", CONNECTOR_FILES)
    def test_no_values_zero_in_connector(self, path):
        """Source-level: .values[0] must be gone from each connector."""
        with open(path, encoding="utf-8") as f:
            src = f.read()
        assert ".values[0]" not in src, (
            f"{path} still uses .values[0] (PND task). Use .iloc[0] instead.")

    @pytest.mark.parametrize("path", CONNECTOR_FILES)
    def test_iloc_zero_present(self, path):
        """Each connector must use .iloc[0] for the MAC/hostname lookup."""
        with open(path, encoding="utf-8") as f:
            src = f.read()
        # The specific lookup pattern
        assert "'MAC Address'].iloc[0]" in src, (
            f"{path} must use 'MAC Address'].iloc[0] for the lookup (PND).")
        assert "'Hostnames'].iloc[0]" in src, (
            f"{path} must use 'Hostnames'].iloc[0] for the lookup (PND).")


class TestIlocBehaviorMatchesValues:
    """Sanity: confirm .iloc[0] produces the same value as .values[0] on
    a real DataFrame, so the swap is safe."""
    def test_iloc_and_values_agree_on_matching_filter(self):
        import pandas as pd
        df = pd.DataFrame({
            "IPs": ["10.0.0.1", "10.0.0.2"],
            "MAC Address": ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"],
            "Hostnames": ["host1", "host2"],
        })
        ip = "10.0.0.2"
        mac_iloc = df.loc[df['IPs'] == ip, 'MAC Address'].iloc[0]
        mac_values = df.loc[df['IPs'] == ip, 'MAC Address'].values[0]
        assert mac_iloc == mac_values == "aa:bb:cc:dd:ee:02"

    def test_iloc_raises_indexerror_on_missing_ip(self):
        """Both .iloc[0] and .values[0] raise IndexError when no row
        matches the filter. The swap preserves the failure mode."""
        import pandas as pd
        df = pd.DataFrame({"IPs": ["10.0.0.1"], "MAC Address": ["aa:bb"]})
        with pytest.raises(IndexError):
            df.loc[df['IPs'] == "10.0.0.99", 'MAC Address'].iloc[0]
