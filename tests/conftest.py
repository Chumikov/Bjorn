import base64
import io
import os
import socket
import sys
import threading
import time
import zipfile
from http.server import HTTPServer, SimpleHTTPRequestHandler
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
    shared_mock.config = {
        "websrv": True,
        "web_auth_enabled": False,
        "web_username": "admin",
        "web_password": "bjorn",
        "web_bind_address": "0.0.0.0",
    }
    shared_mock.web_delay = 2
    shared_mock.csrf_token = "test-csrf-token-12345"

    mock_module = MagicMock()
    mock_module.shared_data = shared_mock
    sys.modules['init_shared'] = mock_module

    mock_epd = MagicMock()
    sys.modules['epd_helper'] = mock_epd
    sys.modules['epd_manager'] = mock_epd
    sys.modules['resources'] = MagicMock()
    sys.modules['resources.waveshare_epd'] = MagicMock()
    # actions/scanning.py imports getmac + nmap (python-nmap) at module
    # top-level — mock both so tests that touch scanning.py don't require
    # the real packages.
    if 'getmac' not in sys.modules:
        sys.modules['getmac'] = MagicMock()
    if 'nmap' not in sys.modules:
        sys.modules['nmap'] = MagicMock()
    # actions/smb_connector.py + actions/steal_files_smb.py import pysmb
    # at module top-level.
    if 'smb' not in sys.modules:
        sys.modules['smb'] = MagicMock()
    if 'smb.SMBConnection' not in sys.modules:
        sys.modules['smb.SMBConnection'] = MagicMock()

    yield shared_mock

    for mod in ['init_shared', 'epd_helper', 'epd_manager', 'resources', 'resources.waveshare_epd',
                'getmac', 'nmap', 'smb', 'smb.SMBConnection']:
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


# ---------------------------------------------------------------------------
# Stage -1 fixtures: in-process servers + helpers for v1.3.0 tests
# ---------------------------------------------------------------------------


class _SilentHTTPRequestHandler(SimpleHTTPRequestHandler):
    """HTTP request handler that logs nothing and serves an empty directory."""

    def log_message(self, *args, **kwargs):
        return


@pytest.fixture
def real_http_server(tmp_path):
    """Spin up an in-process HTTP server on a random port.

    Yields a dict with keys: 'host', 'port', 'base_url', 'server', 'thread'.
    The server runs in a daemon thread; it is shut down on fixture teardown.
    """
    (tmp_path / "index.html").write_text("<html>ok</html>")
    httpd = HTTPServer(("127.0.0.1", 0), lambda *a, **kw: _SilentHTTPRequestHandler(
        *a, directory=str(tmp_path), **kw))
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
            "server": httpd,
            "thread": thread,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


@pytest.fixture
def custom_handler_server(mock_shared_data):
    """Spin up a real HTTPServer using webapp.CustomHandler against the
    REAL webdir (PROJECT_ROOT/web), so static assets (css/images/scripts)
    actually exist on disk.

    Auth is disabled by default (conftest config). Enable it per-test by
    mutating the yielded 'shared' mock's .config before issuing requests.

    Unlike real_http_server (which serves _SilentHTTPRequestHandler from a
    tmp dir), this drives the production CustomHandler.do_GET/do_POST
    dispatch end-to-end, including _check_auth and the directory= fallback.

    Yields dict: host, port, base_url, shared (the mock_shared_data).
    """
    sys.modules.pop('webapp', None)
    import webapp
    webapp.shared_data = mock_shared_data
    httpd = HTTPServer(("127.0.0.1", 0), webapp.CustomHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        yield {
            "host": "127.0.0.1",
            "port": port,
            "base_url": f"http://127.0.0.1:{port}",
            "shared": mock_shared_data,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


@pytest.fixture
def real_ftp_server():
    """Minimal in-process FTP control-channel server (raw sockets).

    Yields a dict with 'host', 'port', 'server_obj', 'thread', 'interactions'.
    Each accepted client is handled in its own daemon thread; the server
    records client commands in 'interactions' for assertion.

    The server speaks just enough of the FTP control protocol for connection
    lifecycle tests (USER/PASS/QUIT). It does NOT serve actual file transfers.
    """
    interactions = []

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(5)
    host, port = server_sock.getsockname()

    accept_stop = threading.Event()

    def handle_client(conn):
        try:
            conn.sendall(b"220 Bjorn test FTP ready\r\n")
            buf = b""
            while True:
                try:
                    data = conn.recv(1024)
                except OSError:
                    break
                if not data:
                    break
                buf += data
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    cmd = line.decode(errors="replace").strip()
                    interactions.append(cmd)
                    upper = cmd.upper()
                    if upper.startswith("USER"):
                        conn.sendall(b"331 need password\r\n")
                    elif upper.startswith("PASS"):
                        conn.sendall(b"230 logged in\r\n")
                    elif upper.startswith("QUIT"):
                        conn.sendall(b"221 bye\r\n")
                        conn.close()
                        return
                    else:
                        conn.sendall(b"502 not implemented\r\n")
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def accept_loop():
        while not accept_stop.is_set():
            try:
                server_sock.settimeout(0.2)
                conn, _ = server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()

    try:
        yield {
            "host": host,
            "port": port,
            "server_obj": server_sock,
            "thread": thread,
            "interactions": interactions,
        }
    finally:
        accept_stop.set()
        try:
            server_sock.close()
        except Exception:
            pass
        thread.join(timeout=3)


@pytest.fixture
def auth_headers():
    """Default Basic auth headers matching admin:bjorn (WEB-8)."""
    creds = base64.b64encode(b"admin:bjorn").decode("ascii")
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def sample_zip_with_traversal(tmp_path):
    """Factory: build a ZIP whose entry name attempts path traversal.

    Returns a callable taking (target_path, content) and returning the Path
    to the crafted .zip file under tmp_path.
    """
    def _make(target="../../tmp/bjorn_pwned.txt", content=b"pwned", name="evil.zip"):
        zip_path = tmp_path / name
        # Build raw ZIP bytes so we can inject an arbitrary member name
        # (ZipInfo normalises some sequences; writing bytes preserves our payload).
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(target, content)
        zip_path.write_bytes(buf.getvalue())
        return zip_path

    return _make


@pytest.fixture
def wait_for_flag():
    """Helper: poll a callable until it returns truthy or timeout (seconds)."""
    def _wait(predicate, timeout=2.0, interval=0.02):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return False
    return _wait
