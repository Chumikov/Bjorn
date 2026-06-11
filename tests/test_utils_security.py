import os
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestPathTraversalDownloadFile:
    def test_blocks_parent_directory_traversal(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        stolen_dir = tmp_path / "data_stolen"
        stolen_dir.mkdir()
        mock_shared_data.datastolendir = str(stolen_dir)

        mock_handler.path = '/download_file?path=../../../etc/shadow'

        web_utils.download_file(mock_handler)

        assert mock_handler.response_code == 403

    def test_blocks_absolute_path_traversal(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        stolen_dir = tmp_path / "data_stolen"
        stolen_dir.mkdir()
        mock_shared_data.datastolendir = str(stolen_dir)

        mock_handler.path = '/download_file?path=/etc/shadow'

        web_utils.download_file(mock_handler)

        assert mock_handler.response_code == 403

    def test_blocks_encoded_traversal(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        stolen_dir = tmp_path / "data_stolen"
        stolen_dir.mkdir()
        mock_shared_data.datastolendir = str(stolen_dir)

        mock_handler.path = '/download_file?path=..%2F..%2F..%2Fetc%2Fshadow'

        web_utils.download_file(mock_handler)

        assert mock_handler.response_code == 403

    def test_allows_valid_file(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        stolen_dir = tmp_path / "data_stolen"
        stolen_dir.mkdir()
        test_file = stolen_dir / "report.csv"
        test_file.write_text("data")
        mock_shared_data.datastolendir = str(stolen_dir)

        mock_handler.path = '/download_file?path=report.csv'

        web_utils.download_file(mock_handler)

        assert mock_handler.response_code == 200

    def test_returns_404_for_nonexistent_file(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        stolen_dir = tmp_path / "data_stolen"
        stolen_dir.mkdir()
        mock_shared_data.datastolendir = str(stolen_dir)

        mock_handler.path = '/download_file?path=nonexistent.txt'

        web_utils.download_file(mock_handler)

        assert mock_handler.response_code == 404

    def test_blocks_null_byte_traversal(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        stolen_dir = tmp_path / "data_stolen"
        stolen_dir.mkdir()
        mock_shared_data.datastolendir = str(stolen_dir)

        mock_handler.path = '/download_file?path=../../../etc/shadow%00.txt'

        web_utils.download_file(mock_handler)

        assert mock_handler.response_code == 403


class TestPathTraversalDownloadBackup:
    def test_blocks_parent_directory_traversal(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        mock_shared_data.backupdir = str(backup_dir)

        mock_handler.path = '/download_backup?filename=../../../etc/shadow'

        web_utils.download_backup(mock_handler)

        assert mock_handler.response_code == 403

    def test_blocks_absolute_path(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        mock_shared_data.backupdir = str(backup_dir)

        mock_handler.path = '/download_backup?filename=/etc/passwd'

        web_utils.download_backup(mock_handler)

        assert mock_handler.response_code == 403

    def test_allows_valid_backup(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        test_backup = backup_dir / "backup_20260101_120000.zip"
        test_backup.write_bytes(b"PK fake zip content")
        mock_shared_data.backupdir = str(backup_dir)

        mock_handler.path = '/download_backup?filename=backup_20260101_120000.zip'

        web_utils.download_backup(mock_handler)

        assert mock_handler.response_code == 200

    def test_returns_404_for_nonexistent_backup(self, mock_handler, mock_shared_data, tmp_path):
        from utils import WebUtils
        web_utils = WebUtils(mock_shared_data, MagicMock())

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        mock_shared_data.backupdir = str(backup_dir)

        mock_handler.path = '/download_backup?filename=nonexistent.zip'

        web_utils.download_backup(mock_handler)

        assert mock_handler.response_code == 404
