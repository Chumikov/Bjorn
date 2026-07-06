"""WEB-8 + WEB-9: HTTP Basic Auth and configurable bind address.

The web UI on :8000 was completely open to anyone on the LAN. Anyone could
POST to /reboot, /shutdown, /restore, etc. CSRF tokens (P1.9) only stop
cross-site attacks, not direct access. This adds Basic Auth on every
endpoint (do_GET + do_POST gate) plus a configurable bind address.
"""
import base64
import json
import sys
import urllib.error
import urllib.request
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

    def test_unauthenticated_redirects_to_login(self, mock_handler, mock_shared_data):
        """PORT-8: no session + no Basic → 302 redirect to /login (not 401
        with a browser Basic dialog)."""
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
        assert 302 in codes, f"Expected 302 redirect to /login; got {codes}"

    def test_no_credentials_redirect_location(self, mock_shared_data):
        """The redirect must point at /login, and no WWW-Authenticate header
        is sent (PORT-8 removed the browser Basic dialog)."""
        sys.modules.pop('webapp', None)
        import webapp
        _set_config(mock_shared_data, web_auth_enabled=True,
                    web_username="admin", web_password="secret")
        h = _make_handler_with_path("/version")
        h.shared_data = mock_shared_data
        h.web_utils = MagicMock()
        h._check_auth()
        headers = {s[1]: s[2] for s in h._sent if s[0] == "header"}
        assert headers.get("Location") == "/login", (
            f"Redirect must target /login; got {headers}")
        assert "WWW-Authenticate" not in headers, (
            "PORT-8: WWW-Authenticate (browser Basic dialog) must be gone.")


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


class TestPasswordHashing:
    """PORT-8: _ensure_password_hashed — migration + password change.

    The key invariant: setting a plaintext ``web_password`` MUST always
    (re)hash it, even when a hash already exists. This is what makes
    password rotation a one-step operation (set web_password, restart)."""

    def test_first_migration_hashes_plaintext(self):
        sys.modules.pop('webapp', None)
        import webapp
        shared = MagicMock()
        shared.config = {"web_username": "admin", "web_password": "bjorn"}
        shared.save_config = MagicMock()
        cfg = {"username": "admin", "password": "bjorn"}
        webapp._ensure_password_hashed(shared, cfg)
        assert "web_password_hash" in shared.config
        assert "web_password_salt" in shared.config
        assert shared.config.get("web_password") is None, (
            "Plaintext must be removed once hashed.")
        assert cfg["password_hash"] and cfg["password_salt"]
        shared.save_config.assert_called_once()

    def test_password_change_rehashes_when_hash_exists(self):
        """Regression: previously setting web_password after the first
        migration was IGNORED (hash took precedence). Now it must re-hash."""
        sys.modules.pop('webapp', None)
        import webapp
        shared = MagicMock()
        # Simulate steady state: hash exists, no plaintext.
        old_hash, old_salt = webapp._hash_password("oldpw")
        shared.config = {"web_username": "admin",
                         "web_password_hash": old_hash,
                         "web_password_salt": old_salt}
        shared.save_config = MagicMock()

        # Operator sets a new plaintext password to rotate.
        shared.config["web_password"] = "newpw"
        cfg = {"username": "admin", "password": "newpw"}
        webapp._ensure_password_hashed(shared, cfg)

        assert shared.config["web_password_hash"] != old_hash, (
            "New plaintext MUST produce a different hash (re-hash happened).")
        assert webapp._verify_password("newpw", shared.config["web_password_hash"],
                                       shared.config["web_password_salt"]), (
            "After rotation the new password must verify against the new hash.")
        assert not webapp._verify_password("oldpw", shared.config["web_password_hash"],
                                           shared.config["web_password_salt"]), (
            "Old password must NO LONGER verify after rotation.")
        assert shared.config.get("web_password") is None

    def test_no_plaintext_uses_stored_hash(self):
        sys.modules.pop('webapp', None)
        import webapp
        shared = MagicMock()
        h, s = webapp._hash_password("bjorn")
        shared.config = {"web_password_hash": h, "web_password_salt": s}
        shared.save_config = MagicMock()
        cfg = {"username": "admin", "password": ""}
        webapp._ensure_password_hashed(shared, cfg)
        assert cfg["password_hash"] == h
        assert cfg["password_salt"] == s
        shared.save_config.assert_not_called(), "No re-hash when no plaintext."


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


class TestAuthGateBehavioral:
    """End-to-end auth-gate: drive the REAL do_GET/do_POST dispatch over a
    real HTTP socket with auth ENABLED and assert the gate fires before any
    file is served or any handler branch runs.

    The source-level ordering tests (test_do_GET_calls_check_auth_first /
    test_do_POST_calls_check_auth_first) only confirm that the string
    ``_check_auth`` lexically precedes ``serve_file_gzipped``/``csrf_token``
    in the source. They would still pass if the gate were reordered or
    bypassed as long as the textual order looked right. These behavioral
    tests issue actual requests and assert on the HTTP response, so a real
    bypass (e.g. someone moving _check_auth below the file-serving branch,
    or dropping the ``if not self._check_auth(): return`` guard) is caught.
    """

    @staticmethod
    def _enable_auth(mock_shared, user="admin", pw="secret"):
        cfg = dict(mock_shared.config)
        cfg.update(web_auth_enabled=True, web_username=user, web_password=pw)
        mock_shared.config = cfg

    @staticmethod
    def _basic(user, pw):
        creds = base64.b64encode(f"{user}:{pw}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}

    def test_get_without_credentials_redirects_to_login(self, custom_handler_server):
        """PORT-8: do_GET with auth on + no creds -> 302 redirect to /login."""
        self._enable_auth(custom_handler_server["shared"])
        url = f"{custom_handler_server['base_url']}/css/styles.css"
        opener = self._no_redirect_opener()
        with pytest.raises(urllib.error.HTTPError) as exc:
            opener.open(url, timeout=5)
        assert exc.value.code == 302, (
            f"Unauthenticated GET must redirect to /login; got {exc.value.code}")
        assert exc.value.headers.get("Location") == "/login"

    def test_get_with_wrong_password_returns_401(self, custom_handler_server):
        """do_GET with auth on + wrong Basic password -> 401 (clear API error)."""
        self._enable_auth(custom_handler_server["shared"])
        url = f"{custom_handler_server['base_url']}/css/styles.css"
        req = urllib.request.Request(url, headers=self._basic("admin", "wrong"))
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        assert exc.value.code == 401

    def test_get_with_correct_basic_credentials_returns_200(self, custom_handler_server):
        """Basic Auth (backward compat) still works against the salted hash."""
        self._enable_auth(custom_handler_server["shared"])
        url = f"{custom_handler_server['base_url']}/css/styles.css"
        req = urllib.request.Request(url, headers=self._basic("admin", "secret"))
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200, (
                f"Correct Basic creds must reach the file; got {resp.status}")
            assert b"background-color" in resp.read(), (
                "Correct creds must actually serve styles.css, not just pass the gate")

    def test_post_without_credentials_redirects_before_csrf(self, custom_handler_server):
        """do_POST with auth on + no creds -> 302 to /login BEFORE the CSRF check.

        Pins the ordering invariant: an unauthenticated caller must not learn
        whether a CSRF token exists (must NOT get 403)."""
        self._enable_auth(custom_handler_server["shared"])
        url = f"{custom_handler_server['base_url']}/save_config"
        req = urllib.request.Request(url, data=b"{}", method="POST")
        opener = self._no_redirect_opener()
        with pytest.raises(urllib.error.HTTPError) as exc:
            opener.open(req, timeout=5)
        assert exc.value.code == 302, (
            f"Unauthenticated POST must redirect (302), not reach CSRF (403); "
            f"got {exc.value.code}")

    # -------------------------------------------------- PORT-8 session flow

    def test_login_issues_cookie_and_session_grants_access(self, custom_handler_server):
        """POST /login with correct creds -> Set-Cookie; that cookie then
        authenticates a subsequent GET (no Basic needed)."""
        self._enable_auth(custom_handler_server["shared"])
        base = custom_handler_server["base_url"]
        login_req = urllib.request.Request(
            f"{base}/login", method="POST",
            data=json.dumps({"username": "admin", "password": "secret"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(login_req, timeout=5) as resp:
            assert resp.status == 200
            cookie = resp.headers.get("Set-Cookie", "")
        assert "bjorn_session=" in cookie, f"Login must set session cookie; got {cookie!r}"
        token = cookie.split("bjorn_session=")[1].split(";")[0]

        # The session cookie must grant access without Basic creds.
        req = urllib.request.Request(f"{base}/css/styles.css",
                                     headers={"Cookie": f"bjorn_session={token}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            assert b"background-color" in resp.read()

    def test_login_wrong_password_returns_401(self, custom_handler_server):
        self._enable_auth(custom_handler_server["shared"])
        base = custom_handler_server["base_url"]
        req = urllib.request.Request(
            f"{base}/login", method="POST",
            data=json.dumps({"username": "admin", "password": "nope"}).encode(),
            headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        assert exc.value.code == 401

    def test_logout_invalidates_session(self, custom_handler_server):
        """After POST /logout, the session cookie no longer grants access."""
        self._enable_auth(custom_handler_server["shared"])
        base = custom_handler_server["base_url"]
        login_req = urllib.request.Request(
            f"{base}/login", method="POST",
            data=json.dumps({"username": "admin", "password": "secret"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(login_req, timeout=5) as resp:
            token = resp.headers.get("Set-Cookie", "").split("bjorn_session=")[1].split(";")[0]

        logout_req = urllib.request.Request(
            f"{base}/logout", method="POST",
            headers={"Cookie": f"bjorn_session={token}"})
        urllib.request.urlopen(logout_req, timeout=5)  # 200

        # Revoked cookie -> redirect to /login (no longer authenticated).
        opener = self._no_redirect_opener()
        with pytest.raises(urllib.error.HTTPError) as exc:
            opener.open(urllib.request.Request(
                f"{base}/version", headers={"Cookie": f"bjorn_session={token}"}),
                timeout=5)
        assert exc.value.code == 302, "Logged-out session must no longer grant access."

    @staticmethod
    def _no_redirect_opener():
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        return urllib.request.build_opener(_NoRedirect)
