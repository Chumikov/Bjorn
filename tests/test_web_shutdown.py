"""WEB-1: WebThread.run/shutdown must not deadlock.

The previous code used a ``handle_request()`` loop combined with a
``httpd.shutdown()`` call in ``WebThread.shutdown()``. ``shutdown()`` only
signals ``serve_forever()`` to exit, so against a ``handle_request()`` loop
it blocks forever — a hard deadlock on every clean exit.

The fix switches to ``serve_forever()`` (and ``HTTPServer`` so that
``allow_reuse_address=True`` is set, fixing "Address already in use" on
restart — WEB-3, folded into this commit).
"""
import http.server
import socket
import threading
import time
from unittest.mock import MagicMock

import pytest


class _StubHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args, **kwargs):
        return


def _make_web_thread():
    """Construct a WebThread bound to a free port with a stub handler."""
    import sys
    sys.modules.pop('webapp', None)
    from webapp import WebThread
    # Find a free port the kernel will assign, then pass it explicitly so we
    # don't depend on WebThread's port-increment logic.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    free_port = s.getsockname()[1]
    s.close()
    shared = MagicMock()
    shared.webapp_should_exit = False
    # _web_auth_config() reads config keys; provide a real dict so the
    # bind_address lookup returns a string, not a MagicMock.
    shared.config = {
        "web_auth_enabled": False,
        "web_username": "admin",
        "web_password": "bjorn",
        "web_bind_address": "0.0.0.0",
    }
    wt = WebThread.__new__(WebThread)
    threading.Thread.__init__(wt, daemon=True)
    wt.shared_data = shared
    wt.port = free_port
    wt.handler_class = _StubHandler
    wt.httpd = None
    return wt


class TestWebShutdownNoDeadlock:
    def test_shutdown_returns_within_2s(self):
        wt = _make_web_thread()
        wt.start()
        # Give serve_forever a moment to actually start serving.
        time.sleep(0.2)
        t0 = time.monotonic()
        wt.shared_data.webapp_should_exit = True
        wt.shutdown()
        wt.join(timeout=2.0)
        elapsed = time.monotonic() - t0
        assert not wt.is_alive(), (
            f"WebThread did not shut down within 2s (elapsed={elapsed:.2f}s)")
        assert elapsed < 2.0, f"shutdown took {elapsed:.2f}s; expected < 2s"

    def test_serve_forever_active_after_run(self):
        wt = _make_web_thread()
        wt.start()
        try:
            # Wait for the server to bind by retrying a connect().
            deadline = time.monotonic() + 2.0
            connected = False
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", wt.port), timeout=0.2):
                        connected = True
                        break
                except OSError:
                    time.sleep(0.05)
            assert connected, f"Server never started listening on port {wt.port}"
        finally:
            wt.shared_data.webapp_should_exit = True
            wt.shutdown()
            wt.join(timeout=2.0)

    def test_shutdown_safe_on_unstarted_thread(self):
        """Calling shutdown() on a thread that never started must not raise."""
        wt = _make_web_thread()
        # Do not start. shutdown() should be a no-op (httpd is None).
        wt.shutdown()  # must not raise

    def test_no_tcpserver_class_used(self):
        """AST/source-level: socketserver.TCPServer must be gone (WEB-3)."""
        import inspect
        import sys
        sys.modules.pop('webapp', None)
        from webapp import WebThread
        src = inspect.getsource(WebThread.run)
        assert "socketserver.TCPServer" not in src, (
            "WebThread.run must use http.server.HTTPServer (allow_reuse_address=True), "
            "not socketserver.TCPServer (WEB-3).")
        assert "http.server.HTTPServer" in src, (
            "WebThread.run must use http.server.HTTPServer (WEB-1/WEB-3).")

    def test_serve_forever_used_not_handle_request(self):
        """AST/source-level: serve_forever() must replace handle_request()."""
        import inspect
        import sys
        sys.modules.pop('webapp', None)
        from webapp import WebThread
        src = inspect.getsource(WebThread.run)
        assert "serve_forever" in src, (
            "WebThread.run must call serve_forever() (WEB-1).")
        assert "handle_request" not in src, (
            "WebThread.run must not call handle_request() in a loop (WEB-1).")
