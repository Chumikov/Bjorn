"""WEB-6: favicon path bug.

os.path.join(webdir, '/images/favicon.ico') discards webdir because the
second argument is absolute (starts with /). The result is the literal
'/images/favicon.ico' at filesystem root, not the intended
'<webdir>/images/favicon.ico'. Removing the leading slash fixes it.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest


class TestFaviconPath:
    def test_webapp_no_leading_slash_in_favicon_path(self):
        """webapp.py module-level favicon_path must not have leading slash."""
        with open("webapp.py", encoding="utf-8") as f:
            src = f.read()
        # Must NOT contain the buggy form
        assert "os.path.join(shared_data.webdir, '/images/favicon.ico')" not in src, (
            "webapp.py still has buggy favicon path with leading '/'.")
        # Must contain the fixed form
        assert "os.path.join(shared_data.webdir, 'images/favicon.ico')" in src, (
            "webapp.py must construct favicon path without leading slash.")

    def test_utils_no_leading_slash_in_favicon_path(self):
        """utils.py serve_favicon must not have leading slash."""
        with open("utils.py", encoding="utf-8") as f:
            src = f.read()
        assert "os.path.join(self.shared_data.webdir, '/images/favicon.ico')" not in src, (
            "utils.py still has buggy favicon path with leading '/'.")
        assert "os.path.join(self.shared_data.webdir, 'images/favicon.ico')" in src, (
            "utils.py must construct favicon path without leading slash.")

    def test_os_path_join_semantics_demo(self):
        """Document why the leading slash was a bug."""
        webdir = "/home/bjorn/Bjorn/web"
        # Buggy form (leading slash): absolute path discards webdir
        buggy = os.path.join(webdir, '/images/favicon.ico')
        assert buggy == '/images/favicon.ico', (
            f"Leading-slash form should yield /images/favicon.ico; got {buggy}")
        # Fixed form: relative path appends to webdir
        fixed = os.path.join(webdir, 'images/favicon.ico')
        assert fixed == '/home/bjorn/Bjorn/web/images/favicon.ico', (
            f"Fixed form should yield <webdir>/images/favicon.ico; got {fixed}")

    def test_serve_favicon_finds_file(self, mock_handler, mock_shared_data, tmp_path):
        """End-to-end: serve_favicon should return 200 when the file exists
        in webdir/images/ — not 404 because of a wrong path."""
        # Build a fake webdir with images/favicon.ico
        webdir = tmp_path / "web"
        (webdir / "images").mkdir(parents=True)
        (webdir / "images" / "favicon.ico").write_bytes(b"\x00\x00\x01\x00fake-ico")
        mock_shared_data.webdir = str(webdir)
        mock_handler.path = "/favicon.ico"

        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())
        web_utils.serve_favicon(mock_handler)
        # The previous bug returned 404 because favicon_path resolved to
        # /images/favicon.ico (filesystem root), which doesn't exist.
        assert mock_handler.response_code == 200, (
            f"Expected 200 (favicon served from webdir); got "
            f"{mock_handler.response_code}. Path bug likely still present.")
