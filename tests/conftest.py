import sys
import os
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(autouse=True)
def mock_shared_data(monkeypatch):
    shared_mock = MagicMock()
    shared_mock.currentdir = PROJECT_ROOT
    shared_mock.configdir = os.path.join(PROJECT_ROOT, 'config')
    shared_mock.datadir = os.path.join(PROJECT_ROOT, 'data')
    shared_mock.actions_dir = os.path.join(PROJECT_ROOT, 'actions')
    shared_mock.webdir = os.path.join(PROJECT_ROOT, 'web')
    shared_mock.resourcesdir = os.path.join(PROJECT_ROOT, 'resources')
    shared_mock.backupbasedir = os.path.join(PROJECT_ROOT, 'backup')
    shared_mock.backupdir = os.path.join(PROJECT_ROOT, 'backup', 'backups')
    shared_mock.upload_dir = os.path.join(PROJECT_ROOT, 'backup', 'uploads')
    shared_mock.logsdir = os.path.join(PROJECT_ROOT, 'data', 'logs')
    shared_mock.output_dir = os.path.join(PROJECT_ROOT, 'data', 'output')
    shared_mock.input_dir = os.path.join(PROJECT_ROOT, 'data', 'input')
    shared_mock.crackedpwddir = os.path.join(PROJECT_ROOT, 'data', 'output', 'crackedpwd')
    shared_mock.datastolendir = os.path.join(PROJECT_ROOT, 'data', 'output', 'data_stolen')
    shared_mock.zombiesdir = os.path.join(PROJECT_ROOT, 'data', 'output', 'zombies')
    shared_mock.vulnerabilities_dir = os.path.join(PROJECT_ROOT, 'data', 'output', 'vulnerabilities')
    shared_mock.scan_results_dir = os.path.join(PROJECT_ROOT, 'data', 'output', 'scan_results')
    shared_mock.picdir = os.path.join(PROJECT_ROOT, 'resources', 'images')
    shared_mock.fontdir = os.path.join(PROJECT_ROOT, 'resources', 'fonts')
    shared_mock.commentsdir = os.path.join(PROJECT_ROOT, 'resources', 'comments')
    shared_mock.statuspicdir = os.path.join(PROJECT_ROOT, 'resources', 'images', 'status')
    shared_mock.staticpicdir = os.path.join(PROJECT_ROOT, 'resources', 'images', 'static')
    shared_mock.dictionarydir = os.path.join(PROJECT_ROOT, 'data', 'input', 'dictionary')
    shared_mock.shared_config_json = os.path.join(PROJECT_ROOT, 'config', 'shared_config.json')
    shared_mock.actions_file = os.path.join(PROJECT_ROOT, 'config', 'actions.json')
    shared_mock.commentsfile = os.path.join(PROJECT_ROOT, 'resources', 'comments', 'comments.json')
    shared_mock.netkbfile = os.path.join(PROJECT_ROOT, 'data', 'netkb.csv')
    shared_mock.livestatusfile = os.path.join(PROJECT_ROOT, 'data', 'livestatus.csv')
    shared_mock.vuln_summary_file = os.path.join(PROJECT_ROOT, 'data', 'output', 'vulnerabilities', 'vulnerability_summary.csv')
    shared_mock.vuln_scan_progress_file = os.path.join(PROJECT_ROOT, 'data', 'output', 'vulnerabilities', 'scan_progress.json')
    shared_mock.usersfile = os.path.join(PROJECT_ROOT, 'data', 'input', 'dictionary', 'users.txt')
    shared_mock.passwordsfile = os.path.join(PROJECT_ROOT, 'data', 'input', 'dictionary', 'passwords.txt')
    shared_mock.sshfile = os.path.join(PROJECT_ROOT, 'data', 'output', 'crackedpwd', 'ssh.csv')
    shared_mock.smbfile = os.path.join(PROJECT_ROOT, 'data', 'output', 'crackedpwd', 'smb.csv')
    shared_mock.telnetfile = os.path.join(PROJECT_ROOT, 'data', 'output', 'crackedpwd', 'telnet.csv')
    shared_mock.ftpfile = os.path.join(PROJECT_ROOT, 'data', 'output', 'crackedpwd', 'ftp.csv')
    shared_mock.sqlfile = os.path.join(PROJECT_ROOT, 'data', 'output', 'crackedpwd', 'sql.csv')
    shared_mock.rdpfile = os.path.join(PROJECT_ROOT, 'data', 'output', 'crackedpwd', 'rdp.csv')
    shared_mock.webconsolelog = os.path.join(PROJECT_ROOT, 'data', 'logs', 'temp_log.txt')
    shared_mock.version = "test"
    shared_mock.config = {"websrv": True}
    shared_mock.web_delay = 2
    shared_mock.csrf_token = "test-csrf-token-12345"

    mock_module = MagicMock()
    mock_module.shared_data = shared_mock
    sys.modules['init_shared'] = mock_module

    mock_epd = MagicMock()
    sys.modules['epd_helper'] = mock_epd
    sys.modules['resources'] = MagicMock()
    sys.modules['resources.waveshare_epd'] = MagicMock()

    yield shared_mock

    for mod in ['init_shared', 'epd_helper', 'resources', 'resources.waveshare_epd']:
        sys.modules.pop(mod, None)


@pytest.fixture
def mock_handler():
    handler = MagicMock()
    handler.response_code = None
    handler.headers = {}
    handler.wfile = MagicMock()
    handler.client_address = ('127.0.0.1', 12345)
    handler.path = ''
    sent_headers = []

    def mock_send_response(code):
        handler.response_code = code

    def mock_send_header(key, value):
        sent_headers.append((key, value))

    def mock_end_headers():
        pass

    handler.send_response = mock_send_response
    handler.send_header = mock_send_header
    handler.end_headers = mock_end_headers
    handler._sent_headers = sent_headers
    return handler
