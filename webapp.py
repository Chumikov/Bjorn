#webapp.py
import base64
import json
import threading
import http.server
import socketserver
import logging
import sys
import signal
import os
import gzip
import io
from logger import Logger
from init_shared import shared_data
from utils import WebUtils

# Initialize the logger
logger = Logger(name="webapp.py", level=logging.DEBUG)

# Default credentials (used when shared_data.config doesn't override). The
# username/password are also stored in config/shared_config.json so the user
# can rotate them via the web UI.
DEFAULT_WEB_USERNAME = "admin"
DEFAULT_WEB_PASSWORD = "bjorn"
DEFAULT_WEB_BIND_ADDRESS = "0.0.0.0"

# Set the path to the favicon. NOTE: a leading slash on the second arg would
# make os.path.join() discard webdir entirely (absolute path semantics), so
# the favicon would resolve to /images/favicon.ico at the filesystem root.
favicon_path = os.path.join(shared_data.webdir, 'images/favicon.ico')


def _web_auth_config(shared):
    """Read auth-related config from shared_data with safe defaults.

    Returns a dict with: auth_enabled, username, password, bind_address.
    Works whether shared.config is a real dict (production) or a MagicMock
    (tests) — falls back to module-level defaults.
    """
    config = getattr(shared, "config", None) or {}
    try:
        auth_enabled = bool(config.get("web_auth_enabled", True))
    except Exception:
        auth_enabled = True
    try:
        username = config.get("web_username") or DEFAULT_WEB_USERNAME
    except Exception:
        username = DEFAULT_WEB_USERNAME
    try:
        password = config.get("web_password") or DEFAULT_WEB_PASSWORD
    except Exception:
        password = DEFAULT_WEB_PASSWORD
    try:
        bind_address = config.get("web_bind_address") or DEFAULT_WEB_BIND_ADDRESS
    except Exception:
        bind_address = DEFAULT_WEB_BIND_ADDRESS
    return {
        "auth_enabled": auth_enabled,
        "username": username,
        "password": password,
        "bind_address": bind_address,
    }

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.shared_data = shared_data
        self.web_utils = WebUtils(shared_data, logger)
        # Pass directory= so SimpleHTTPRequestHandler.do_GET() fallback (used
        # for any static file not matched by our explicit routes) serves from
        # webdir instead of os.getcwd().
        super().__init__(*args, directory=self.shared_data.webdir, **kwargs)

    def log_message(self, format, *args):
        # Override to suppress logging of GET requests.
        if 'GET' not in format % args:
            logger.info("%s - - [%s] %s\n" %
                        (self.client_address[0],
                         self.log_date_time_string(),
                         format % args))

    def send_response(self, code, message=None):
        """Override to attach security headers (WEB-4) to every response.

        The base implementation adds Server + Date headers; we follow it
        with X-Content-Type-Options, X-Frame-Options, and a permissive CSP.
        Every endpoint (including WebUtils methods in utils.py that call
        handler.send_response) gets the headers automatically.
        """
        super().send_response(code, message)
        self._send_security_headers()

    def gzip_encode(self, content):
        """Gzip compress the given content."""
        out = io.BytesIO()
        # Binary mode is required on Python 3.13+. The previous text-mode
        # alias is deprecated and will be removed in a future version.
        with gzip.GzipFile(fileobj=out, mode="wb") as f:
            f.write(content)
        return out.getvalue()

    def _send_security_headers(self):
        """Attach standard security headers to the in-flight response.

        Call after send_response() and before end_headers(). Protects
        against MIME-sniffing (X-Content-Type-Options), clickjacking
        (X-Frame-Options), and limits injection vectors via CSP.
        """
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        # 'unsafe-inline' because the existing HTML/JS uses inline scripts
        # and styles; tightening this requires refactoring web/.
        self.send_header("Content-Security-Policy",
                         "default-src 'self' 'unsafe-inline'; img-src 'self' data:;")

    def _check_auth(self):
        """HTTP Basic Auth gate (WEB-8).

        Returns True if the request is authorised (or auth is disabled).
        Sends a 401 response and returns False otherwise. Must be called
        at the very top of do_GET/do_POST, before any other work.
        """
        cfg = _web_auth_config(self.shared_data)
        if not cfg["auth_enabled"]:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8", errors="replace")
                user, _, pw = decoded.partition(":")
                if user == cfg["username"] and pw == cfg["password"]:
                    return True
            except Exception:
                pass
        # Not authorised — send 401 with WWW-Authenticate so the browser
        # shows its built-in Basic auth dialog.
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Bjorn"')
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        try:
            self.wfile.write(b"Authentication required.\n")
        except Exception:
            pass
        return False

    def send_gzipped_response(self, content, content_type):
        """Send a gzipped HTTP response."""
        gzipped_content = self.gzip_encode(content)
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(gzipped_content)))
        self.end_headers()
        self.wfile.write(gzipped_content)

    def serve_file_gzipped(self, file_path, content_type):
        """Serve a file with gzip compression."""
        with open(file_path, 'rb') as file:
            content = file.read()
        self.send_gzipped_response(content, content_type)

    def do_GET(self):
        # Auth gate (WEB-8). Applies to every GET including static assets.
        if not self._check_auth():
            return
        # Handle GET requests. Serve the HTML interface and the EPD image.
        if self.path == '/index.html' or self.path == '/':
            self.serve_file_gzipped(os.path.join(self.shared_data.webdir, 'index.html'), 'text/html')
        elif self.path == '/config.html':
            self.serve_file_gzipped(os.path.join(self.shared_data.webdir, 'config.html'), 'text/html')
        elif self.path == '/network.html':
            self.serve_file_gzipped(os.path.join(self.shared_data.webdir, 'network.html'), 'text/html')
        elif self.path == '/netkb.html':
            self.serve_file_gzipped(os.path.join(self.shared_data.webdir, 'netkb.html'), 'text/html')
        elif self.path == '/bjorn.html':
            self.serve_file_gzipped(os.path.join(self.shared_data.webdir, 'bjorn.html'), 'text/html')
        elif self.path == '/loot.html':
            self.serve_file_gzipped(os.path.join(self.shared_data.webdir, 'loot.html'), 'text/html')
        elif self.path == '/credentials.html':
            self.serve_file_gzipped(os.path.join(self.shared_data.webdir, 'credentials.html'), 'text/html')
        elif self.path == '/load_config':
            self.web_utils.serve_current_config(self)
        elif self.path == '/restore_default_config':
            self.web_utils.restore_default_config(self)
        elif self.path == '/get_web_delay':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response = json.dumps({"web_delay": self.shared_data.web_delay})
            self.wfile.write(response.encode('utf-8'))
        elif self.path == '/version':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"version": self.shared_data.version}).encode('utf-8'))
        elif self.path == '/scan_wifi':
            self.web_utils.scan_wifi(self)
        elif self.path == '/network_data':
            self.web_utils.serve_network_data(self)
        elif self.path == '/netkb_data':
            self.web_utils.serve_netkb_data(self)
        elif self.path == '/netkb_data_json':
            self.web_utils.serve_netkb_data_json(self)
        elif self.path == '/csrf_token':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"csrf_token": self.shared_data.csrf_token}).encode('utf-8'))
        elif self.path.startswith('/screen.png'):
            self.web_utils.serve_image(self)
        elif self.path == '/favicon.ico':
            self.web_utils.serve_favicon(self)
        elif self.path == '/manifest.json':
            self.web_utils.serve_manifest(self)
        elif self.path == '/apple-touch-icon':
            self.web_utils.serve_apple_touch_icon(self)
        elif self.path == '/get_logs':
            self.web_utils.serve_logs(self)
        elif self.path == '/list_credentials':
            self.web_utils.serve_credentials_data(self)
        elif self.path.startswith('/list_files'):
            self.web_utils.list_files_endpoint(self)
        elif self.path.startswith('/download_file'):
            self.web_utils.download_file(self)
        elif self.path.startswith('/download_backup'):
            self.web_utils.download_backup(self)
        else:
            super().do_GET()

    def do_POST(self):
        # Auth gate (WEB-8). Must precede CSRF check — unauthorised callers
        # should not even learn whether a CSRF token exists.
        if not self._check_auth():
            return
        csrf_token = self.headers.get('X-CSRF-Token', '')
        if csrf_token != self.shared_data.csrf_token:
            self.send_response(403)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": "CSRF token missing or invalid"}).encode('utf-8'))
            return

        # Handle POST requests for saving configuration, connecting to Wi-Fi, clearing files, rebooting, and shutting down.
        if self.path == '/save_config':
            self.web_utils.save_configuration(self)
        elif self.path == '/connect_wifi':
            self.web_utils.connect_wifi(self)
            self.shared_data.wifichanged = True  # Set the flag when Wi-Fi is connected
        elif self.path == '/disconnect_wifi':  # New route to disconnect Wi-Fi
            self.web_utils.disconnect_and_clear_wifi(self)
        elif self.path == '/clear_files':
            self.web_utils.clear_files(self)
        elif self.path == '/clear_files_light':
            self.web_utils.clear_files_light(self)
        elif self.path == '/initialize_csv':
            self.web_utils.initialize_csv(self)
        elif self.path == '/reboot':
            self.web_utils.reboot_system(self)
        elif self.path == '/shutdown':
            self.web_utils.shutdown_system(self)
        elif self.path == '/restart_bjorn_service':
            self.web_utils.restart_bjorn_service(self)
        elif self.path == '/backup':
            self.web_utils.backup(self)
        elif self.path == '/restore':
            self.web_utils.restore(self)
        elif self.path == '/stop_orchestrator':  # New route to stop the orchestrator
            self.web_utils.stop_orchestrator(self)
        elif self.path == '/start_orchestrator':  # New route to start the orchestrator
            self.web_utils.start_orchestrator(self)
        elif self.path == '/execute_manual_attack':  # New route to execute a manual attack
            self.web_utils.execute_manual_attack(self)
        else:
            self.send_response(404)
            self.end_headers()

class WebThread(threading.Thread):
    """
    Thread to run the web server serving the EPD display interface.
    """
    def __init__(self, handler_class=CustomHandler, port=8000):
        # WebThread is non-daemon — the service stays alive while it runs.
        # Reverted ARCH-1 daemon=True; combined with daemon bjorn_thread
        # it caused the whole process to exit immediately after main
        # finished setting up signal handlers (crash-loop on RPi).
        super().__init__()
        self.shared_data = shared_data
        self.port = port
        self.handler_class = handler_class
        self.httpd = None

    def _bind_address(self):
        """Read bind address from config at runtime (WEB-9).

        Default '0.0.0.0' keeps Bjorn accessible on the LAN (the primary
        use case). Users who want loopback-only can set
        web_bind_address='127.0.0.1' in shared_config.json.
        """
        return _web_auth_config(self.shared_data)["bind_address"]

    def run(self):
        """
        Run the web server in a separate thread.
        """
        # Soft enforcement (WEB-8): warn loudly if the default password is
        # still in place. We do NOT block access — Basic Auth has no good
        # 'force-change' flow — but the journal entry surfaces the issue.
        cfg = _web_auth_config(self.shared_data)
        if cfg["auth_enabled"] and cfg["password"] == DEFAULT_WEB_PASSWORD:
            logger.warning(
                "Web UI is using the default password 'bjorn'. "
                "Rotate it via the config page (web_password key in "
                "shared_config.json) before exposing Bjorn on untrusted "
                "networks.")

        while not self.shared_data.webapp_should_exit:
            try:
                bind_addr = self._bind_address()
                with http.server.HTTPServer((bind_addr, self.port), self.handler_class) as httpd:
                    self.httpd = httpd
                    logger.info(f"Serving at {bind_addr}:{self.port}")
                    # Blocks until httpd.shutdown() is called from another
                    # thread (WebThread.shutdown). Previously the loop here
                    # picked requests off one at a time, which caused
                    # BaseServer.shutdown() to deadlock since it only knows
                    # how to interrupt the forever-serving loop.
                    httpd.serve_forever(poll_interval=0.5)
            except OSError as e:
                if e.errno == 98:  # Address already in use error
                    logger.warning(f"Port {self.port} is in use, trying the next port...")
                    self.port += 1
                else:
                    logger.error(f"Error in web server: {e}")
                    break
            finally:
                if self.httpd:
                    # server_close() releases the listening socket. The `with`
                    # block above already does this on clean exit; this is a
                    # fallback for the OSError path.
                    try:
                        self.httpd.server_close()
                    except Exception:
                        pass
                    self.httpd = None
                    logger.info("Web server closed.")

    def shutdown(self):
        """
        Shutdown the web server gracefully.

        httpd.shutdown() signals serve_forever() to exit. Must be called from
        a different thread than the one running serve_forever().
        """
        if self.httpd:
            try:
                self.httpd.shutdown()
                logger.info("Web server shutdown initiated.")
            except Exception as e:
                logger.error(f"Error during web server shutdown: {e}")

def handle_exit_web(signum, frame):
    """
    Handle exit signals to shutdown the web server cleanly.
    """
    shared_data.webapp_should_exit = True
    if web_thread.is_alive():
        web_thread.shutdown()
        web_thread.join()  # Wait until the web_thread is finished
    logger.info("Server shutting down...")
    sys.exit(0)

# Initialize the web thread
web_thread = WebThread(port=8000)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit_web)
    signal.signal(signal.SIGTERM, handle_exit_web)
    try:
        # Start the web server thread
        web_thread.start()
        logger.info("Web server thread started.")
    except Exception as e:
        logger.error(f"An exception occurred during web server start: {e}")
        handle_exit_web(signal.SIGINT, None)
        sys.exit(1)
