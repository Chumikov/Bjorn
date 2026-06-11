import os
import threading
import sys
from unittest.mock import MagicMock

import pytest
from PIL import ImageFont

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(PROJECT_ROOT, "resources", "fonts")


def _load_font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def _run_wrap_text_in_thread(sd, text, font, max_width, result_container):
    try:
        result_container["result"] = sd.wrap_text(text, font, max_width)
    except Exception as e:
        result_container["error"] = e


class TestWrapTextInfiniteLoop:
    def _call_with_timeout(self, sd, text, font, max_width, timeout=3):
        container = {"result": None, "error": None}
        t = threading.Thread(target=_run_wrap_text_in_thread,
                             args=(sd, text, font, max_width, container))
        t.daemon = True
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            pytest.fail(f"wrap_text hung for >{timeout}s with text: {text!r}")
        if container["error"]:
            raise container["error"]
        return container["result"]

    def test_long_word_does_not_hang(self, mock_shared_data):
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.config = {"debug_mode": False}

        font = _load_font("Arial.ttf", 12)
        max_width = 50

        result = self._call_with_timeout(
            sd, "VeryLongWordThatDoesNotFit short", font, max_width
        )

        assert isinstance(result, list)
        assert len(result) > 0

    def test_normal_text_wraps_correctly(self, mock_shared_data):
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.config = {"debug_mode": False}

        font = _load_font("Arial.ttf", 12)
        max_width = 200

        result = self._call_with_timeout(
            sd, "Hello world this is a test", font, max_width
        )

        assert isinstance(result, list)
        assert len(result) > 0
        full_text = " ".join(line.strip() for line in result)
        assert "Hello" in full_text
        assert "test" in full_text

    def test_single_long_word_returns_something(self, mock_shared_data):
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.config = {"debug_mode": False}

        font = _load_font("Arial.ttf", 12)
        max_width = 50

        result = self._call_with_timeout(
            sd, "Supercalifragilisticexpialidocious", font, max_width
        )

        assert isinstance(result, list)
        assert len(result) >= 1
        for line in result:
            assert isinstance(line, str)

    def test_empty_string_returns_empty_list(self, mock_shared_data):
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.config = {"debug_mode": False}

        font = _load_font("Arial.ttf", 12)

        result = sd.wrap_text("", font, 200)

        assert result == []

    def test_mixed_long_and_short_words(self, mock_shared_data):
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.config = {"debug_mode": False}

        font = _load_font("Arial.ttf", 12)
        max_width = 60

        result = self._call_with_timeout(
            sd, "antidisestablishmentarianism ok hi", font, max_width
        )

        assert isinstance(result, list)
        assert len(result) >= 1
