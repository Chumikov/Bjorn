import json
from unittest.mock import MagicMock

import pytest


class TestCSRFProtection:
    def _get_handler(self, mock_shared_data):
        sys_modules = {}
        import sys
        webapp_mod = sys.modules.get('webapp')
        if webapp_mod is None:
            sys_modules['__need_import__'] = True
        else:
            sys_modules['__need_import__'] = False
            sys_modules['webapp'] = webapp_mod

        if sys_modules['__need_import__']:
            import webapp
            sys_modules['webapp'] = webapp

        return sys_modules['webapp']

    def test_post_without_csrf_token_is_rejected(self, mock_handler, mock_shared_data):
        import sys
        sys.modules.pop('webapp', None)
        import webapp

        handler = webapp.CustomHandler.__new__(webapp.CustomHandler)
        handler.shared_data = mock_shared_data
        handler.web_utils = webapp.WebUtils(mock_shared_data, MagicMock())
        handler.path = '/reboot'
        handler.headers = {}
        handler.wfile = MagicMock()
        handler.client_address = ('127.0.0.1', 12345)

        sent = []
        handler.send_response = lambda code: sent.append(('response', code))
        handler.send_header = lambda k, v: sent.append(('header', k, v))
        handler.end_headers = lambda: sent.append(('end',))

        handler.do_POST()

        codes = [s[1] for s in sent if s[0] == 'response']
        assert 403 in codes, f"POST without CSRF token should return 403, got {codes}"

    def test_post_with_wrong_csrf_token_is_rejected(self, mock_handler, mock_shared_data):
        import sys
        sys.modules.pop('webapp', None)
        import webapp

        mock_shared_data.csrf_token = "correct-token-12345"

        handler = webapp.CustomHandler.__new__(webapp.CustomHandler)
        handler.shared_data = mock_shared_data
        handler.web_utils = webapp.WebUtils(mock_shared_data, MagicMock())
        handler.path = '/reboot'
        handler.headers = {'X-CSRF-Token': 'wrong-token'}
        handler.wfile = MagicMock()
        handler.client_address = ('127.0.0.1', 12345)

        sent = []
        handler.send_response = lambda code: sent.append(('response', code))
        handler.send_header = lambda k, v: sent.append(('header', k, v))
        handler.end_headers = lambda: sent.append(('end',))

        handler.do_POST()

        codes = [s[1] for s in sent if s[0] == 'response']
        assert 403 in codes, f"POST with wrong CSRF token should return 403, got {codes}"

    def test_post_with_valid_csrf_token_is_accepted(self, mock_handler, mock_shared_data):
        import sys
        sys.modules.pop('webapp', None)
        import webapp

        mock_shared_data.csrf_token = "correct-token-12345"

        handler = webapp.CustomHandler.__new__(webapp.CustomHandler)
        handler.shared_data = mock_shared_data
        handler.web_utils = webapp.WebUtils(mock_shared_data, MagicMock())
        handler.path = '/reboot'
        handler.headers = {'X-CSRF-Token': 'correct-token-12345'}
        handler.wfile = MagicMock()
        handler.client_address = ('127.0.0.1', 12345)

        sent = []
        handler.send_response = lambda code: sent.append(('response', code))
        handler.send_header = lambda k, v: sent.append(('header', k, v))
        handler.end_headers = lambda: sent.append(('end',))

        handler.do_POST()

        codes = [s[1] for s in sent if s[0] == 'response']
        assert 403 not in codes, f"POST with valid CSRF token should not return 403, got {codes}"

    def test_csrf_token_endpoint_returns_token(self, mock_handler, mock_shared_data):
        import sys
        sys.modules.pop('webapp', None)
        import webapp

        mock_shared_data.csrf_token = "test-token-abc"

        handler = webapp.CustomHandler.__new__(webapp.CustomHandler)
        handler.shared_data = mock_shared_data
        handler.web_utils = webapp.WebUtils(mock_shared_data, MagicMock())
        handler.path = '/csrf_token'
        handler.headers = {}
        handler.wfile = MagicMock()
        handler.client_address = ('127.0.0.1', 12345)

        sent = []
        handler.send_response = lambda code: sent.append(('response', code))
        handler.send_header = lambda k, v: sent.append(('header', k, v))
        handler.end_headers = lambda: sent.append(('end',))

        handler.do_GET()

        codes = [s[1] for s in sent if s[0] == 'response']
        assert 200 in codes, f"/csrf_token should return 200, got {codes}"

        written = handler.wfile.write.call_args[0][0]
        data = json.loads(written)
        assert data.get('csrf_token') == 'test-token-abc', \
            f"/csrf_token should return the token from shared_data, got {data}"
