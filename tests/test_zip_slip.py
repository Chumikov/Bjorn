"""UTL-1: Zip Slip vulnerability in WebUtils.restore().

zipfile.extractall() does not sanitise member paths. A crafted archive
containing '../../etc/crontab' would write outside the target dir.

Python 3.12+ adds filter='data' which blocks this. We use it with a manual
fallback for Python < 3.12.
"""
import os
import sys
import zipfile
from unittest.mock import MagicMock

import pytest


def _make_restore_handler(mock_shared_data, zip_path):
    """Build a handler mock with rfile returning the zip's bytes packaged
    as multipart form data."""
    handler = MagicMock()
    handler.headers = {"Content-Length": str(zip_path.stat().st_size + 200)}
    # The multipart wrapper is complex; we'll bypass it by patching
    # _parse_multipart to return the filename and raw zip bytes directly.
    with open(zip_path, "rb") as f:
        zip_bytes = f.read()
    handler.rfile = MagicMock()
    handler.rfile.read.return_value = zip_bytes  # Will be overridden per-test
    return handler, zip_bytes


class TestZipSlipGuard:
    def test_extractall_uses_filter_data(self):
        """AST/source: extractall must be called with filter='data'."""
        with open("utils.py", encoding="utf-8") as f:
            src = f.read()
        assert "filter='data'" in src, (
            "utils.py must call extractall with filter='data' (UTL-1).")

    def test_restore_blocks_path_traversal(self, mock_shared_data, tmp_path,
                                            sample_zip_with_traversal):
        """End-to-end: a crafted zip with ../../ entry must NOT write
        outside the target directory."""
        # Build the malicious zip
        evil_zip = sample_zip_with_traversal(
            target="../../../../../../tmp/bjorn_pwned_test.txt",
            content=b"PWNED",
            name="evil.zip",
        )

        # Set up shared_data paths so restore() extracts into tmp_path
        mock_shared_data.upload_dir = str(tmp_path / "uploads")
        mock_shared_data.currentdir = str(tmp_path / "extract")
        os.makedirs(mock_shared_data.upload_dir, exist_ok=True)
        os.makedirs(mock_shared_data.currentdir, exist_ok=True)

        # Clean any stale marker
        marker = "/tmp/bjorn_pwned_test.txt"
        if os.path.exists(marker):
            os.unlink(marker)

        # Build handler that returns the zip bytes from _parse_multipart
        handler = MagicMock()
        zip_bytes = evil_zip.read_bytes()
        handler.headers = {"Content-Length": str(len(zip_bytes))}
        handler.rfile.read.return_value = zip_bytes
        handler.wfile = MagicMock()
        sent = []
        handler.send_response = lambda c: sent.append(c)
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None

        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())
        # Patch _parse_multipart to short-circuit the multipart parsing
        web_utils._parse_multipart = lambda data, headers: ("evil.zip", data)

        web_utils.restore(handler)

        # The marker file must NOT exist at /tmp/bjorn_pwned_test.txt
        assert not os.path.exists(marker), (
            f"Zip Slip succeeded: {marker} was written outside target dir. "
            f"Code under test:\n{open('utils.py').read()[10000:11000]}")
        # The restore should have signalled an error (500) since filter='data'
        # raises on traversal entries, OR the manual fallback should have
        # raised ValueError. Either way, no 200.
        assert 200 not in sent, (
            f"restore() returned 200 despite traversal attempt; sent={sent}")

    def test_restore_allows_legitimate_zip(self, mock_shared_data, tmp_path):
        """Sanity check: a normal zip without traversal must extract fine."""
        # Build a benign zip
        benign_zip = tmp_path / "benign.zip"
        with zipfile.ZipFile(benign_zip, "w") as zf:
            zf.writestr("hello.txt", "hi")
            zf.writestr("sub/dir/file.txt", "nested")

        mock_shared_data.upload_dir = str(tmp_path / "uploads")
        mock_shared_data.currentdir = str(tmp_path / "extract")
        os.makedirs(mock_shared_data.upload_dir, exist_ok=True)
        os.makedirs(mock_shared_data.currentdir, exist_ok=True)

        handler = MagicMock()
        zip_bytes = benign_zip.read_bytes()
        handler.headers = {"Content-Length": str(len(zip_bytes))}
        handler.rfile.read.return_value = zip_bytes
        handler.wfile = MagicMock()
        sent = []
        handler.send_response = lambda c: sent.append(c)
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None

        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())
        web_utils._parse_multipart = lambda data, headers: ("benign.zip", data)

        web_utils.restore(handler)

        assert 200 in sent, f"Legitimate zip should restore successfully; got {sent}"
        # Files should be extracted to the target dir
        assert os.path.isfile(os.path.join(mock_shared_data.currentdir, "hello.txt"))
        assert os.path.isfile(os.path.join(mock_shared_data.currentdir, "sub", "dir", "file.txt"))
