"""WEB-8 + WEB-9: HTTP Basic Auth and configurable bind address.

The web UI on :8000 was completely open to anyone on the LAN. Anyone could
POST to /reboot, /shutdown, /restore, etc. CSRF tokens (P1.9) only stop
cross-site attacks, not direct access. This adds Basic Auth on every
endpoint (do_GET + do_POST gate) plus a configurable bind address.
"""
import base64
import sys
from unittest.mock import MagicMock

import pytest


def _make_handler_with_path(path, headers=None):
    """Construct a CustomHandler with mocked I/O for auth dispatch tests."""
    sys.modules.pop('webapp', None)
    import webapp

    handler = webapp.CustomHandler.__new__(webapp.CustomHandler)
    handler.path = path
    handler.headers = headers or {}
    handler.wfile = MagicMock()
    sent = []
    handler.requestline = path
    handler.request_version = "HTTP/1.1"
    handler.client_address = ("127.0.0.1", 12345)
    handler.log_date_time_string = lambda: "01/Jan/2026"
    handler.log_request = lambda *a, **kw: None
    handler.send_response = lambda code, msg=None: sent.append(("response", code))
    handler.send_header = lambda k, v: sent.append(("header", k, v))
    handler.end_headers = lambda: sent.append(("end",))
    handler._sent = sent
    return handler


def _set_config(mock_shared_data, **overrides):
    """Update mock_shared_data.config with the given overrides."""
    cfg = dict(mock_shared_data.config)
    cfg.update(overrides)
    mock_shared_data.config = cfg


def _auth_header(user, pw):
    creds = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


class TestBasicAuthGate:
    def test_check_auth_exists(self):
        sys.modules.pop('webapp', None)
        import webapp
        assert hasattr(webapp.CustomHandler, "_check_auth"), (
            "CustomHandler must define _check_auth().")

    def test_unauthenticated_returns_401(self, mock_handler, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=True,
                    web_username="admin", web_password="secret")
        h = _make_handler_with_path("/version")
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        result = h._check_auth()
        assert result is False, "Unauthenticated request must return False"
        codes = [s[1] for s in h._sent if s[0] == "response"]
        assert 401 in codes, f"Expected 401; got {codes}"

    def test_www_authenticate_header_present(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=True,
                    web_username="admin", web_password="secret")
        h = _make_handler_with_path("/version")
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        h._check_auth()
        headers = {s[1]: s[2] for s in h._sent if s[0] == "header"}
        assert "WWW-Authenticate" in headers, (
            f"401 response must include WWW-Authenticate for browser prompt; "
            f"got {headers}")
        assert "Basic" in headers["WWW-Authenticate"]

    def test_wrong_password_returns_401(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=True,
                    web_username="admin", web_password="secret")
        h = _make_handler_with_path("/version", _auth_header("admin", "wrong"))
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        result = h._check_auth()
        assert result is False
        codes = [s[1] for s in h._sent if s[0] == "response"]
        assert 401 in codes

    def test_wrong_username_returns_401(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=True,
                    web_username="admin", web_password="secret")
        h = _make_handler_with_path("/version", _auth_header("root", "secret"))
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        result = h._check_auth()
        assert result is False

    def test_correct_credentials_return_true(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=True,
                    web_username="admin", web_password="secret")
        h = _make_handler_with_path("/version", _auth_header("admin", "secret"))
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        result = h._check_auth()
        assert result is True, "Correct creds must pass"
        # No response code should have been sent (the gate just lets through)
        codes = [s[1] for s in h._sent if s[0] == "response"]
        assert codes == [], f"Auth pass-through must not send a response; got {codes}"

    def test_auth_disabled_lets_everything_through(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=False)
        h = _make_handler_with_path("/version")  # no Authorization header
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        result = h._check_auth()
        assert result is True, "Auth disabled must always pass"
        codes = [s[1] for s in h._sent if s[0] == "response"]
        assert codes == [], "Auth disabled must not send any response"

    def test_malformed_authorization_returns_401(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=True,
                    web_username="admin", web_password="secret")
        # Not "Basic ..." prefix
        h = _make_handler_with_path("/version", {"Authorization": "Bearer xyz"})
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        assert h._check_auth() is False

    def test_malformed_base64_returns_401(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=True,
                    web_username="admin", web_password="secret")
        # Valid prefix, invalid base64
        h = _make_handler_with_path("/version", {"Authorization": "Basic !!!notbase64!!!"})
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        assert h._check_auth() is False

    def test_do_GET_calls_check_auth_first(self, mock_shared_data):
        """Source-level: do_GET must invoke _check_auth before any branch."""
        sys.modules.pop('webapp', None)
        import webapp
        import inspect
        src = inspect.getsource(webapp.CustomHandler.do_GET)
        # _check_auth must appear before any serve_file_gzipped call
        check_pos = src.find("_check_auth")
        serve_pos = src.find("serve_file_gzipped")
        assert check_pos != -1 and serve_pos != -1, (
            "do_GET source must mention both _check_auth and serve_file_gzipped")
        assert check_pos < serve_pos, (
            "do_GET must call _check_auth before any serve_file_gzipped")

    def test_do_POST_calls_check_auth_first(self, mock_shared_data):
        """Source-level: do_POST must invoke _check_auth before CSRF check."""
        sys.modules.pop('webapp', None)
        import webapp
        import inspect
        src = inspect.getsource(webapp.CustomHandler.do_POST)
        check_pos = src.find("_check_auth")
        csrf_pos = src.find("csrf_token")
        assert check_pos != -1 and csrf_pos != -1
        assert check_pos < csrf_pos, (
            "do_POST must call _check_auth before the CSRF check (so "
            "unauthenticated callers cannot learn whether a CSRF token exists).")


class TestDefaultPasswordWarning:
    """Soft enforcement: warn on startup if password is still default."""

    def test_default_constants_present(self):
        sys.modules.pop('webapp', None)
        import webapp
        assert webapp.DEFAULT_WEB_PASSWORD == "bjorn"
        assert webapp.DEFAULT_WEB_USERNAME == "admin"

    def test_warning_emitted_in_run_source(self):
        sys.modules.pop('webapp', None)
        import webapp
        import inspect
        src = inspect.getsource(webapp.WebThread.run)
        assert "DEFAULT_WEB_PASSWORD" in src, (
            "WebThread.run must reference DEFAULT_WEB_PASSWORD to emit warning.")
        assert "logger.warning" in src


class TestBindAddress:
    """WEB-9: configurable bind address."""

    def test_bind_address_method_exists(self):
        sys.modules.pop('webapp', None)
        import webapp
        assert hasattr(webapp.WebThread, "_bind_address"), (
            "WebThread must define _bind_address().")

    def test_default_bind_address_is_0_0_0_0(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_bind_address="0.0.0.0")
        wt = webapp.WebThread.__new__(webapp.WebThread)
        wt.shared_data = mock_shared_data
        assert wt._bind_address() == "0.0.0.0"

    def test_loopback_only_when_configured(self, mock_shared_data):
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_bind_address="127.0.0.1")
        wt = webapp.WebThread.__new__(webapp.WebThread)
        wt.shared_data = mock_shared_data
        assert wt._bind_address() == "127.0.0.1"

    def test_run_uses_bind_address_not_empty_string(self):
        """Source-level: run() must use _bind_address(), not hard-coded ''."""
        sys.modules.pop('webapp', None)
        import webapp
        import inspect
        src = inspect.getsource(webapp.WebThread.run)
        assert "_bind_address()" in src, (
            "WebThread.run must call self._bind_address() to get the bind host.")
        # The old form (hard-coded empty string as host) must be gone
        assert 'HTTPServer(("", self.port)' not in src, (
            "WebThread.run must not bind to '' (hard-coded).")


class TestConfigDefaults:
    """WEB-8/9: shared_config.json + SharedData defaults must expose keys."""

    def test_default_config_has_auth_keys(self):
        sys.modules.pop('shared', None)
        import shared
        defaults = shared.SharedData().__get_default_config_helper() \
            if hasattr(shared.SharedData, "_SharedData__get_default_config_helper") \
            else None
        # The real default config method is get_default_config (public)
        sd = shared.SharedData.__new__(shared.SharedData)
        cfg = sd.get_default_config()
        for key in ("web_auth_enabled", "web_username",
                    "web_password", "web_bind_address"):
            assert key in cfg, f"Default config missing key: {key}"
        assert cfg["web_auth_enabled"] is True
        assert cfg["web_username"] == "admin"
        assert cfg["web_password"] == "bjorn"
        assert cfg["web_bind_address"] == "0.0.0.0"
