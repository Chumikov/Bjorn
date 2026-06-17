"""WEB-4: security headers + gzip mode="wb".

Adds three security headers (X-Content-Type-Options, X-Frame-Options, CSP)
via a send_response override so every response carries them automatically.
Also fixes the deprecated gzip mode="w" (text-mode alias) -> mode="wb".
"""
import ast
import inspect
import io
import sys
import textwrap
import zlib
from unittest.mock import MagicMock

import pytest


class TestSecurityHeaders:
    def _make_handler(self):
        """Build a handler with send_response override INTACT.

        We must NOT mock send_response — that's the override we're testing.
        Instead we mock only the low-level send_header/end_headers/wfile
        so the override can run and call _send_security_headers naturally.
        The parent send_response calls log_request + sends Server/Date via
        send_header, so we need send_header to swallow those too.
        """
        sys.modules.pop('webapp', None)
        import webapp

        handler = webapp.CustomHandler.__new__(webapp.CustomHandler)
        sent = []
        # Mock only the primitives. send_response (our override) will call
        # super().send_response which calls send_header('Server', ...) and
        # send_header('Date', ...); then our override calls
        # _send_security_headers which calls send_header three more times.
        # super().send_response also writes the response line via
        # self.wfile, so we need a mock wfile.
        handler.wfile = MagicMock()
        # capture_command captures the request line for logging via
        # super().send_response -> log_request -> log_request uses
        # self.requestline and self.client_address.
        handler.requestline = "GET / HTTP/1.1"
        handler.request_version = "HTTP/1.1"
        handler.client_address = ("127.0.0.1", 12345)
        handler.log_date_time_string = lambda: "01/Jan/2026 00:00:00"
        handler.log_request = lambda code="-", size=None: None
        handler.send_header = lambda k, v: sent.append(("header", k, v))
        handler.end_headers = lambda: sent.append(("end",))
        handler._sent = sent
        return handler

    def test_security_headers_method_exists(self):
        sys.modules.pop('webapp', None)
        import webapp
        assert hasattr(webapp.CustomHandler, "_send_security_headers"), (
            "CustomHandler must define _send_security_headers() helper.")

    def test_send_response_overridden(self):
        """AST: CustomHandler.send_response must call _send_security_headers."""
        sys.modules.pop('webapp', None)
        import webapp
        assert "_send_security_headers" in inspect.getsource(
            webapp.CustomHandler.send_response), (
            "send_response() override must invoke _send_security_headers()")

    def test_security_headers_present_on_every_response(self):
        h = self._make_handler()
        h._sent.clear()
        h.send_response(200)
        headers = {item[1]: item[2] for item in h._sent if item[0] == "header"}
        assert headers.get("X-Content-Type-Options") == "nosniff", (
            f"Missing/no-sniff X-Content-Type-Options; got {headers}")
        assert headers.get("X-Frame-Options") == "DENY", (
            f"Missing/denied X-Frame-Options; got {headers}")
        assert "Content-Security-Policy" in headers, (
            f"Missing Content-Security-Policy; got {headers}")
        assert "default-src" in headers["Content-Security-Policy"]

    def test_security_headers_on_error_response(self):
        h = self._make_handler()
        h._sent.clear()
        h.send_response(500)
        headers = {item[1]: item[2] for item in h._sent if item[0] == "header"}
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_redirect(self):
        h = self._make_handler()
        h._sent.clear()
        h.send_response(302)
        headers = {item[1]: item[2] for item in h._sent if item[0] == "header"}
        assert headers.get("X-Content-Type-Options") == "nosniff"


class TestGzipModeBinary:
    """WEB-4 (sidecar): gzip_encode must use mode='wb' not mode='w'."""

    def test_gzip_uses_wb_not_w(self):
        sys.modules.pop('webapp', None)
        import webapp
        src = inspect.getsource(webapp.CustomHandler.gzip_encode)
        assert 'mode="wb"' in src or "mode='wb'" in src, (
            "gzip_encode must use mode='wb' (binary). Source was:\n" + src)
        assert 'mode="w"' not in src.replace('mode="wb"', ''), (
            "gzip_encode still contains mode='w' (text mode, deprecated). "
            "Source was:\n" + src.replace('mode="wb"', ''))

    def test_gzip_encode_produces_valid_gzip(self):
        sys.modules.pop('webapp', None)
        import webapp
        handler = webapp.CustomHandler.__new__(webapp.CustomHandler)
        original = b"hello world " * 100
        compressed = handler.gzip_encode(original)
        # zlib can decode gzip-formatted data with wbits=16 + gzip magic
        decompressed = zlib.decompress(compressed, 16 + zlib.MAX_WBITS)
        assert decompressed == original, (
            "gzip roundtrip failed; the bytes we wrote are not what we got back."
        )
