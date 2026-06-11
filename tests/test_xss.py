import os
import csv
from unittest.mock import MagicMock
from io import StringIO

import pytest


class TestGenerateHtmlEscapesXSS:
    def _make_web_utils(self, mock_shared_data):
        from utils import WebUtils
        return WebUtils(mock_shared_data, MagicMock())

    def test_generate_html_for_csv_escapes_script_tags(self, mock_shared_data, tmp_path):
        csv_file = tmp_path / "ssh.csv"
        csv_file.write_text("User,Password\n<script>alert(1)</script>,p@ss\n")
        mock_shared_data.crackedpwddir = str(tmp_path)

        web_utils = self._make_web_utils(mock_shared_data)
        html = web_utils.generate_html_for_csv_files(str(tmp_path))

        assert "<script>" not in html, "Unescaped <script> tag found in HTML output"
        assert "&lt;script&gt;" in html, "Script tag should be escaped"

    def test_generate_html_for_csv_escapes_img_onerror(self, mock_shared_data, tmp_path):
        csv_file = tmp_path / "ftp.csv"
        csv_file.write_text('User,Password\nadmin,<img src=x onerror=alert(1)>\n')
        mock_shared_data.crackedpwddir = str(tmp_path)

        web_utils = self._make_web_utils(mock_shared_data)
        html = web_utils.generate_html_for_csv_files(str(tmp_path))

        assert "onerror" not in html or "&lt;img" in html, \
            "Unescaped <img onerror> found — XSS vulnerability"

    def test_generate_html_for_csv_escapes_cell_with_html_entity(self, mock_shared_data, tmp_path):
        csv_file = tmp_path / "ssh.csv"
        csv_file.write_text('User,Password\n"<b>bold</b>",p@ss\n')
        mock_shared_data.crackedpwddir = str(tmp_path)

        web_utils = self._make_web_utils(mock_shared_data)
        html = web_utils.generate_html_for_csv_files(str(tmp_path))

        assert "<b>bold</b>" not in html, "HTML in cell values should be escaped"
        assert "&lt;b&gt;bold&lt;/b&gt;" in html

    def test_generate_html_table_escapes_cells(self, mock_shared_data, tmp_path):
        csv_file = tmp_path / "result_test.csv"
        csv_file.write_text("IP,Port,Status\n10.0.0.1,22,<script>alert('xss')</script>\n")

        web_utils = self._make_web_utils(mock_shared_data)
        html = web_utils.generate_html_table(str(csv_file))

        assert "<script>" not in html, "Unescaped script tag in scan results table"
        assert "&lt;script&gt;" in html

    def test_generate_html_table_escapes_headers(self, mock_shared_data, tmp_path):
        csv_file = tmp_path / "result_test.csv"
        csv_file.write_text('<img src=x onerror=alert(1)>,Port\nvalue,22\n')

        web_utils = self._make_web_utils(mock_shared_data)
        html = web_utils.generate_html_table(str(csv_file))

        assert "onerror" not in html or "&lt;img" in html

    def test_generate_html_table_netkb_escapes_cells(self, mock_shared_data, tmp_path):
        csv_file = tmp_path / "netkb.csv"
        csv_file.write_text("IPs,MAC,Hostname,Alive,Ports\n10.0.0.1,aa:bb,<script>alert(1)</script>,1,22\n")

        web_utils = self._make_web_utils(mock_shared_data)
        html = web_utils.generate_html_table_netkb(str(csv_file))

        assert "<script>" not in html, "Unescaped script tag in netkb table"
        assert "&lt;script&gt;" in html

    def test_generate_html_table_netkb_escapes_ip_with_html(self, mock_shared_data, tmp_path):
        csv_file = tmp_path / "netkb.csv"
        csv_file.write_text('IPs,MAC,Hostname,Alive,Ports\n"<b onmouseover=alert(1)>10.0.0.1</b>",aa:bb,host1,1,22\n')

        web_utils = self._make_web_utils(mock_shared_data)
        result = web_utils.generate_html_table_netkb(str(csv_file))

        assert "<b " not in result, "Unescaped <b> tag in netkb"
        assert "</b>" not in result, "Unescaped </b> tag in netkb"
        assert "&lt;b " in result, "Tag should be escaped"
