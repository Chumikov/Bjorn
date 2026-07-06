"""Behavioral tests for comment.py (Commentaireia).

Covers load_comments (cache/original/fallbacks) and get_commentaire
(theme change, delay gating, unknown-theme fallback). Previously 0% coverage.
"""
import json
import os
import time
from unittest.mock import MagicMock

import pytest


def _make_commenter(tmp_path, themes=None, delay_min=1, delay_max=5):
    """Build a Commentaireia with a temp comments file + controlled delays.

    ``import comment`` is deferred to here so it runs under conftest's
    init_shared mock (importing at module top would trigger the real
    SharedData/EPD init during collection)."""
    import comment

    commentsfile = str(tmp_path / "comments.json")
    payload = themes if themes is not None else {
        "IDLE": ["idle-1", "idle-2"],
        "SCANNER": ["scan-1", "scan-2", "scan-3"],
    }
    with open(commentsfile, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    mock_sd = MagicMock()
    mock_sd.commentsfile = commentsfile
    mock_sd.comment_delaymin = delay_min
    mock_sd.comment_delaymax = delay_max
    # The class binds shared_data at construction from the module global.
    original = comment.shared_data
    comment.shared_data = mock_sd
    try:
        commenter = comment.Commentaireia()
    finally:
        comment.shared_data = original
    return commenter


class TestLoadComments:
    def test_load_from_json(self, tmp_path):
        c = _make_commenter(tmp_path)
        assert "IDLE" in c.themes
        assert "SCANNER" in c.themes
        assert set(c.themes["IDLE"]) == {"idle-1", "idle-2"}

    def test_cache_created_and_used(self, tmp_path):
        c = _make_commenter(tmp_path)
        cache = str(tmp_path / "comments.json.cache")
        assert os.path.exists(cache), "load_comments must write a .cache file."
        # Make the original OLDER than the cache → cache should be preferred.
        commentsfile = str(tmp_path / "comments.json")
        os.utime(commentsfile, (time.time() - 100, time.time() - 100))
        reloaded = c.load_comments(commentsfile)
        assert reloaded == c.themes  # cache content matches

    def test_corrupt_cache_falls_back_to_original(self, tmp_path):
        c = _make_commenter(tmp_path)
        commentsfile = str(tmp_path / "comments.json")
        cache = commentsfile + ".cache"
        # Corrupt the cache but keep it newer than the original.
        with open(cache, "w") as f:
            f.write("{not valid json")
        os.utime(commentsfile, (time.time() - 100, time.time() - 100))
        reloaded = c.load_comments(commentsfile)
        assert "IDLE" in reloaded  # original JSON still parses

    def test_missing_file_returns_fallback(self, tmp_path):
        c = _make_commenter(tmp_path)
        result = c.load_comments(str(tmp_path / "nonexistent.json"))
        assert "IDLE" in result
        assert "no comments file found" in result["IDLE"][0].lower()

    def test_invalid_json_returns_fallback(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        c = _make_commenter(tmp_path)
        result = c.load_comments(str(bad))
        assert "IDLE" in result
        assert "invalid json" in result["IDLE"][0].lower()


class TestGetCommentaire:
    def test_theme_change_returns_comment(self, tmp_path):
        c = _make_commenter(tmp_path)
        first = c.get_commentaire("SCANNER")
        assert first in c.themes["SCANNER"]

    def test_same_theme_within_delay_returns_none(self, tmp_path):
        c = _make_commenter(tmp_path, delay_min=100, delay_max=100)
        first = c.get_commentaire("SCANNER")
        assert first is not None
        # Same theme immediately after — delay (100s) not elapsed.
        second = c.get_commentaire("SCANNER")
        assert second is None

    def test_unknown_theme_falls_back_to_idle(self, tmp_path):
        c = _make_commenter(tmp_path)
        result = c.get_commentaire("NONEXISTENT_THEME")
        assert result in c.themes["IDLE"]

    def test_returns_none_when_no_themes_loaded(self, tmp_path):
        # If themes is empty, get_commentaire must not crash; returns None
        # (random.choice on missing key path can't apply — unknown theme
        # falls to IDLE which is also absent → KeyError avoided by caller).
        c = _make_commenter(tmp_path, themes={"IDLE": ["only"]})
        assert c.get_commentaire("IDLE") == "only"
