"""WEB-5: robust query-string parsing.

The previous ``handler.path.split('?path=')[1]`` breaks if the value
contains the substring ``path=`` itself (or ``&`` / ``+`` characters).
Replaced with urllib.parse.urlparse + parse_qs.
"""
import sys
from unittest.mock import MagicMock

import pytest


def _make_web_utils(mock_shared_data):
    from utils import WebUtils
    return WebUtils(mock_shared_data, MagicMock())


class TestQueryParamHelper:
    def test_helper_exists(self):
        from utils import WebUtils
        assert hasattr(WebUtils, "_query_param"), (
            "WebUtils must define _query_param() helper.")

    def test_basic_param(self):
        wu = _make_web_utils.__wrapped__ if hasattr(_make_web_utils, "__wrapped__") else None
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        assert web_utils._query_param("/download_file?path=foo.txt", "path") == "foo.txt"

    def test_param_with_embedded_param_name(self):
        """The bug: value contains 'path=' substring itself."""
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        # Value is 'path=evil' — under split('?path=')[1] this would yield
        # 'path=evil' (which is what we want), but if the URL had multiple
        # '?path=' the split would only grab the part after the first one
        # and drop the rest. parse_qs handles this correctly.
        result = web_utils._query_param("/download_file?path=path%3Devil", "path")
        assert result == "path=evil"

    def test_param_with_spaces(self):
        """parse_qs decodes '+' as space and %20 as space."""
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        assert web_utils._query_param("/x?path=foo+bar", "path") == "foo bar"
        assert web_utils._query_param("/x?path=foo%20bar", "path") == "foo bar"

    def test_param_with_ampersand_in_value(self):
        """Encoded ampersand (%26) must not be treated as param separator."""
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        assert web_utils._query_param("/x?path=a%26b", "path") == "a&b"

    def test_param_with_multiple_equals_in_value(self):
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        # URL-encode '=' as %3D
        assert web_utils._query_param("/x?path=x%3Dy", "path") == "x=y"

    def test_missing_param_returns_none(self):
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        assert web_utils._query_param("/download_file", "path") is None
        assert web_utils._query_param("/download_file?other=x", "path") is None

    def test_empty_param_value(self):
        from utils import WebUtils
        web_utils = WebUtils.__new__(WebUtils)
        # keep_blank_values=True — empty value returns "" not None
        assert web_utils._query_param("/x?path=", "path") == ""


class TestDownloadFileParsing:
    def test_download_file_accepts_path_with_equals(self, mock_handler, mock_shared_data, tmp_path):
        """End-to-end: download_file with a value containing '=' should
        be parsed correctly, not return 400."""
        import os
        stolen_dir = tmp_path / "data_stolen"
        stolen_dir.mkdir()
        mock_shared_data.datastolendir = str(stolen_dir)
        # Create a file whose name contains '='
        target = stolen_dir / "name=value.txt"
        target.write_text("data")
        mock_handler.path = f"/download_file?path=name%3Dvalue.txt"
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())
        web_utils.download_file(mock_handler)
        assert mock_handler.response_code == 200, (
            f"Expected 200 for filename with '='; got {mock_handler.response_code}")

    def test_download_backup_accepts_filename_with_special_chars(
            self, mock_handler, mock_shared_data, tmp_path):
        import os
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        mock_shared_data.backupdir = str(backup_dir)
        # Filename with %3D (=) and %26 (&)
        target = backup_dir / "weird=name&co.zip"
        target.write_bytes(b"PK")
        mock_handler.path = "/download_backup?filename=weird%3Dname%26co.zip"
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())
        web_utils.download_backup(mock_handler)
        assert mock_handler.response_code == 200, (
            f"Expected 200 for filename with special chars; got "
            f"{mock_handler.response_code}")


class TestSourceLevelGuarantees:
    def test_no_split_pattern_in_download_file(self):
        with open("utils.py", encoding="utf-8") as f:
            src = f.read()
        # The old fragile pattern must be gone from download_file and download_backup
        assert "handler.path.split('?path=')" not in src, (
            "utils.py still uses handler.path.split('?path=') in download_file.")
        assert "handler.path.split('?filename=')" not in src, (
            "utils.py still uses handler.path.split('?filename=') in download_backup.")

    def test_urlparse_imported(self):
        with open("utils.py", encoding="utf-8") as f:
            src = f.read()
        assert "urlparse" in src and "parse_qs" in src, (
            "utils.py must import urlparse and parse_qs from urllib.parse.")
