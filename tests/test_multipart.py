import os
import json
from unittest.mock import MagicMock

import pytest


class TestMultipartParser:
    def _make_web_utils(self, mock_shared_data):
        from utils import WebUtils
        return WebUtils(mock_shared_data, MagicMock())

    def _build_multipart(self, filename, content, boundary=b"----Boundary123"):
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"\r\n'
            b"Content-Type: application/zip\r\n"
            b"\r\n"
            + content +
            b"\r\n--" + boundary + b"--\r\n"
        )
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
            "Content-Length": str(len(body)),
        }
        return body, headers

    def test_parse_multipart_extracts_filename_and_content(self, mock_shared_data):
        web_utils = self._make_web_utils(mock_shared_data)
        body, headers = self._build_multipart("backup.zip", b"PK\x03\x04zipcontent")
        filename, content = web_utils._parse_multipart(body, headers)
        assert filename == "backup.zip"
        assert content == b"PK\x03\x04zipcontent"

    def test_parse_multipart_with_unicode_filename(self, mock_shared_data):
        web_utils = self._make_web_utils(mock_shared_data)
        body, headers = self._build_multipart("резерв.zip", b"data")
        filename, content = web_utils._parse_multipart(body, headers)
        assert "резерв" in filename
        assert content == b"data"

    def test_parse_multipart_no_file_returns_none(self, mock_shared_data):
        web_utils = self._make_web_utils(mock_shared_data)
        body = b"------Boundary123\r\n\r\nsome text\r\n------Boundary123--\r\n"
        headers = {"Content-Type": "multipart/form-data; boundary=----Boundary123"}
        filename, content = web_utils._parse_multipart(body, headers)
        assert filename is None
        assert content is None

    def test_parse_multipart_empty_file(self, mock_shared_data):
        web_utils = self._make_web_utils(mock_shared_data)
        body, headers = self._build_multipart("empty.zip", b"")
        filename, content = web_utils._parse_multipart(body, headers)
        assert filename == "empty.zip"
        assert content == b""

    def test_utils_does_not_import_cgi(self):
        import ast
        with open("utils.py") as f:
            tree = ast.parse(f.read())
        imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]
        from_imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        all_imports = imports + from_imports
        assert "cgi" not in all_imports, "utils.py still imports deprecated cgi module"

    def test_restore_uses_parse_multipart(self, mock_handler, mock_shared_data, tmp_path):
        mock_shared_data.upload_dir = str(tmp_path)
        mock_shared_data.currentdir = str(tmp_path)

        web_utils = self._make_web_utils(mock_shared_data)

        body, headers = self._build_multipart("test.zip", b"PK\x03\x04fake")
        mock_handler.headers = headers
        mock_handler.rfile = MagicMock()
        mock_handler.rfile.read.return_value = body

        web_utils.restore(mock_handler)

        assert mock_handler.response_code == 200, f"Expected 200, got {mock_handler.response_code}"
        saved = os.path.join(str(tmp_path), "test.zip")
        assert os.path.exists(saved), "Uploaded file should be saved"
        with open(saved, 'rb') as f:
            assert f.read() == b"PK\x03\x04fake"
