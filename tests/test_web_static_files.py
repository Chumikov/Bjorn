"""WEB-2: CustomHandler must pass directory= to SimpleHTTPRequestHandler.

Without it, the fallback ``super().do_GET()`` (used for any static asset
not matched by an explicit route) serves from ``os.getcwd()`` instead of
the configured web directory. On a systemd-launched service cwd is ``/``,
so all non-routed static assets would 404.

History: the original tests here only inspected the *source* (AST /
inspect.getsource) to confirm the ``directory=`` kwarg was present. That
let a real regression through — the kwarg WAS passed, but the HTML
referenced assets with a redundant ``web/`` prefix, so requests resolved
to ``<webdir>/web/css/...`` (double-nested) and 404'd. The CSS, JS and
all icons silently failed to load.

The integration tests below (TestStaticAssetResolution) drive the real
CustomHandler over a real HTTP socket against the production webdir and
assert HTTP 200 + body content, so a path-resolution regression can no
longer pass silently.
"""
import http.server
import inspect
import sys
import urllib.error
import urllib.request
from unittest.mock import MagicMock

import pytest


class TestStaticFileDirectory:
    def test_init_passes_directory_kwarg(self):
        """AST check: super().__init__ must be called with directory=..."""
        sys.modules.pop('webapp', None)
        import webapp

        tree = inspect.getsource(webapp.CustomHandler.__init__)
        # Must reference the directory keyword
        assert "directory=" in tree, (
            "CustomHandler.__init__ must pass directory= to super().__init__ "
            "so the SimpleHTTPRequestHandler fallback serves from webdir.")

    def test_directory_kwarg_supported_by_parent(self):
        """Verify SimpleHTTPRequestHandler.__init__ accepts directory=."""
        sig = inspect.signature(http.server.SimpleHTTPRequestHandler.__init__)
        assert "directory" in sig.parameters, (
            "SimpleHTTPRequestHandler.__init__ must accept directory= (Python 3.7+). "
            f"Params: {list(sig.parameters)}")

    def test_directory_value_used_at_runtime(self):
        """End-to-end-ish: instantiate CustomHandler via real HTTPServer and
        check that .directory matches shared_data.webdir.

        We construct the handler through HTTPServer.get_request() so the
        BaseRequestHandler setup runs normally, then inspect .directory on
        the instance after it has dispatched one request (which we let 404
        on a non-routed path).
        """
        import socket
        import threading
        sys.modules.pop('webapp', None)
        import webapp

        # Use a real http.server.HTTPServer with a wrapper handler that
        # captures the constructed CustomHandler instance.
        captured = {}

        class _Capture(webapp.CustomHandler):
            def handle_one_request(self):
                # Run parent setup but skip the actual request dispatch (which
                # would try to serve files from the fake webdir).
                # Just record .directory then close the connection cleanly.
                captured["directory"] = getattr(self, "directory", None)
                # Send a 204 so handle_one_request doesn't loop.
                try:
                    self.send_response(204)
                    self.end_headers()
                except Exception:
                    pass

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)

        try:
            server = MagicMock()
            server.socket = sock
            server.server_address = ("127.0.0.1", port)

            # Patch shared_data with a known webdir.
            mock_shared = MagicMock()
            mock_shared.webdir = "/known/web/path"
            original = webapp.shared_data
            webapp.shared_data = mock_shared
            try:
                # Connect a client and send a single GET to drive the handler.
                def client():
                    try:
                        c = socket.create_connection(("127.0.0.1", port), timeout=1)
                        c.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
                        c.recv(1024)
                        c.close()
                    except Exception:
                        pass
                t = threading.Thread(target=client, daemon=True)
                t.start()

                conn, addr = sock.accept()
                try:
                    _Capture(conn, addr, server)
                finally:
                    conn.close()
                t.join(timeout=1)
            finally:
                webapp.shared_data = original

            assert captured.get("directory") == "/known/web/path", (
                f"directory attribute not propagated; got {captured.get('directory')!r}")
        finally:
            sock.close()

    def test_init_signature_accepts_directory(self):
        """Inspection-based: super().__init__ call must include directory=..."""
        sys.modules.pop('webapp', None)
        import webapp
        import ast

        src = inspect.getsource(webapp.CustomHandler.__init__)
        # Dedent because it's a method (indented inside class)
        import textwrap
        tree = ast.parse(textwrap.dedent(src))
        # Find the super().__init__() Call node
        super_call_found = False
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "__init__"
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Name)
                    and node.func.value.func.id == "super"):
                super_call_found = True
                kwarg_names = [kw.arg for kw in node.keywords]
                assert "directory" in kwarg_names, (
                    "super().__init__() must pass directory= keyword. "
                    f"Found kwargs: {kwarg_names}")
        assert super_call_found, "Could not find super().__init__() call"


class TestStaticAssetResolution:
    """Integration: real HTTP GET for static assets must return 200.

    These are the tests that the original WEB-2 suite lacked. They spin up
    a real CustomHandler over a real socket against the production webdir
    (PROJECT_ROOT/web) and assert that CSS / JS / image requests actually
    resolve to a file and come back with HTTP 200 + non-empty body.

    Regression guard for the v1.3.x bug where assets were referenced with a
    redundant ``web/`` prefix while the server root was already ``webdir``,
    causing every asset to 404.
    """

    def _get(self, server, path):
        url = f"{server['base_url']}{path}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-type", "")

    def test_static_css_returns_200(self, custom_handler_server):
        """GET /css/styles.css -> 200, real CSS body (not 404)."""
        status, body, _ = self._get(custom_handler_server, "/css/styles.css")
        assert status == 200, f"CSS must load; got {status}"
        assert b"background-color" in body, (
            "styles.css body missing expected CSS rule; got:\n" + body.decode("utf-8", "replace"))

    def test_static_image_returns_200(self, custom_handler_server):
        """GET /images/console_icon.png -> 200 with an image Content-Type."""
        status, body, ctype = self._get(custom_handler_server,
                                        "/images/console_icon.png")
        assert status == 200, f"icon must load; got {status}"
        assert ctype.startswith("image/"), (
            f"icon must be served as image/*; got Content-Type {ctype!r}")
        assert len(body) > 0, "icon body must not be empty"

    def test_static_js_returns_200(self, custom_handler_server):
        """GET /scripts/csrf.js -> 200 (JS loaded by every page)."""
        status, body, _ = self._get(custom_handler_server, "/scripts/csrf.js")
        assert status == 200, f"csrf.js must load; got {status}"
        assert len(body) > 0, "csrf.js body must not be empty"

    def test_old_web_prefixed_path_returns_404(self, custom_handler_server):
        """Regression guard: /web/css/styles.css must NOT resolve.

        The v1.3.x bug was that the HTML used ``web/``-prefixed URLs while
        the server root was already ``<webdir>`` (= ``web/``), so the path
        resolved to ``<webdir>/web/css/styles.css``. With the fix, asset
        URLs no longer carry the ``web/`` prefix and the double-nested
        path correctly 404s. This test pins that contract so the prefix
        cannot silently creep back.
        """
        url = f"{custom_handler_server['base_url']}/web/css/styles.css"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=5)
        assert exc.value.code == 404, (
            f"Double-nested /web/... path must 404; got {exc.value.code}")
