import os
import csv
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestRDPConnectorNameError:
    def test_run_bruteforce_does_not_raise_nameerror(self, mock_shared_data, tmp_path):
        mock_shared_data.orchestrator_should_exit = False
        mock_shared_data.rdpfile = str(tmp_path / "rdp.csv")
        with open(mock_shared_data.rdpfile, "w") as f:
            f.write("MAC Address,IP Address,Hostname,User,Password,Port\n")

        users_file = tmp_path / "users.txt"
        users_file.write_text("admin\n")
        passwords_file = tmp_path / "passwords.txt"
        passwords_file.write_text("pass\n")
        mock_shared_data.usersfile = str(users_file)
        mock_shared_data.passwordsfile = str(passwords_file)

        netkb_file = tmp_path / "netkb.csv"
        with open(netkb_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["MAC Address", "IPs", "Hostnames", "Alive", "Ports"])
            writer.writerow(["AA:BB:CC:DD:EE:FF", "192.168.1.10", "testhost", "1", "3389"])
        mock_shared_data.netkbfile = str(netkb_file)

        mock_df = MagicMock()
        mock_df.__iter__ = MagicMock(return_value=iter([]))
        mock_loc = MagicMock()
        mock_loc.__getitem__ = MagicMock(return_value=MagicMock(
            values=MagicMock(return_value=["AA:BB:CC:DD:EE:FF"])
        ))
        type(mock_df).loc = PropertyMock(return_value=mock_loc)
        mock_df.str = MagicMock()

        with patch("actions.rdp_connector.pd.read_csv", return_value=mock_df), \
             patch("actions.rdp_connector.subprocess.Popen") as mock_popen, \
             patch("actions.rdp_connector.Progress"):
            mock_process = MagicMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 1
            mock_popen.return_value = mock_process

            from actions.rdp_connector import RDPConnector
            connector = RDPConnector(mock_shared_data)

            try:
                connector.run_bruteforce("192.168.1.10", "3389")
            except NameError as e:
                pytest.fail(f"NameError raised: {e}")
