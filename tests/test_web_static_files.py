"""WEB-2: CustomHandler must pass directory= to SimpleHTTPRequestHandler.

Without it, the fallback ``super().do_GET()`` (used for any static asset
not matched by an explicit route) serves from ``os.getcwd()`` instead of
the configured web directory. On a systemd-launched service cwd is ``/``,
so all non-routed static assets would 404.
"""
import http.server
import inspect
import os
import sys
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
