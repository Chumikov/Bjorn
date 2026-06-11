import signal
import sys
from unittest.mock import MagicMock

import pytest


class TestWebThreadSafety:
    def test_webapp_does_not_register_signal_handlers_at_import(self):
        original_handlers = {
            signal.SIGINT: signal.getsignal(signal.SIGINT),
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        }

        sys.modules.pop('webapp', None)
        import webapp

        sigint_handler = signal.getsignal(signal.SIGINT)
        sigterm_handler = signal.getsignal(signal.SIGTERM)

        assert sigint_handler in (original_handlers[signal.SIGINT], signal.SIG_DFL, signal.default_int_handler), \
            f"webapp.py should NOT register SIGINT handler at import time, got {sigint_handler}"
        assert sigterm_handler in (original_handlers[signal.SIGTERM], signal.SIG_DFL), \
            f"webapp.py should NOT register SIGTERM handler at import time, got {sigterm_handler}"

    def test_web_thread_not_started_at_import(self):
        sys.modules.pop('webapp', None)
        import webapp

        assert not webapp.web_thread.is_alive(), "web_thread should not be started at import"

    def test_shutdown_safe_on_unstarted_thread(self):
        sys.modules.pop('webapp', None)
        import webapp

        webapp.web_thread.shutdown()  # should not raise

