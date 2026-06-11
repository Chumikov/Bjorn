import os
import csv
import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest


class TestServeNetkbDataJson:
    def _make_web_utils(self, mock_shared_data):
        from utils import WebUtils
        return WebUtils(mock_shared_data, MagicMock())

    def test_empty_csv_returns_200_not_500(self, mock_handler, mock_shared_data, tmp_path):
        netkb = tmp_path / "netkb.csv"
        netkb.write_text("IPs,MAC,Hostname,Alive,Ports,action1\n")
        mock_shared_data.netkbfile = str(netkb)

        web_utils = self._make_web_utils(mock_shared_data)
        web_utils.serve_netkb_data_json(mock_handler)

        assert mock_handler.response_code == 200

    def test_empty_csv_returns_empty_data(self, mock_handler, mock_shared_data, tmp_path):
        netkb = tmp_path / "netkb.csv"
        netkb.write_text("IPs,MAC,Hostname,Alive,Ports,action1\n")
        mock_shared_data.netkbfile = str(netkb)

        web_utils = self._make_web_utils(mock_shared_data)
        web_utils.serve_netkb_data_json(mock_handler)

        written = mock_handler.wfile.write.call_args[0][0]
        data = json.loads(written)
        assert data["ips"] == []
        assert data["ports"] == {}
        assert data["actions"] == ["action1"]

    def test_csv_with_data_returns_filtered_alive(self, mock_handler, mock_shared_data, tmp_path):
        netkb = tmp_path / "netkb.csv"
        netkb.write_text(
            "IPs,MAC,Hostname,Alive,Ports,action1\n"
            "10.0.0.1,aa:bb,host1,1,22;80,done\n"
            "10.0.0.2,cc:dd,host2,0,443,pending\n"
        )
        mock_shared_data.netkbfile = str(netkb)

        web_utils = self._make_web_utils(mock_shared_data)
        web_utils.serve_netkb_data_json(mock_handler)

        assert mock_handler.response_code == 200
        written = mock_handler.wfile.write.call_args[0][0]
        data = json.loads(written)
        assert data["ips"] == ["10.0.0.1"]
        assert data["ports"] == {"10.0.0.1": ["22", "80"]}

    def test_csv_with_no_rows_only_header(self, mock_handler, mock_shared_data, tmp_path):
        netkb = tmp_path / "netkb.csv"
        netkb.write_text("IPs,MAC,Hostname,Alive,Ports\n")
        mock_shared_data.netkbfile = str(netkb)

        web_utils = self._make_web_utils(mock_shared_data)
        web_utils.serve_netkb_data_json(mock_handler)

        assert mock_handler.response_code == 200
        written = mock_handler.wfile.write.call_args[0][0]
        data = json.loads(written)
        assert data["ips"] == []
        assert data["actions"] == []

    def test_nonexistent_csv_returns_500(self, mock_handler, mock_shared_data, tmp_path):
        mock_shared_data.netkbfile = str(tmp_path / "nonexistent.csv")

        web_utils = self._make_web_utils(mock_shared_data)
        web_utils.serve_netkb_data_json(mock_handler)

        assert mock_handler.response_code == 500

    def test_truly_empty_file_no_header_returns_200(self, mock_handler, mock_shared_data, tmp_path):
        netkb = tmp_path / "netkb.csv"
        netkb.write_text("")
        mock_shared_data.netkbfile = str(netkb)

        web_utils = self._make_web_utils(mock_shared_data)
        web_utils.serve_netkb_data_json(mock_handler)

        assert mock_handler.response_code == 200
        written = mock_handler.wfile.write.call_args[0][0]
        data = json.loads(written)
        assert data["ips"] == []
        assert data["actions"] == []
