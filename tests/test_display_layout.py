"""PORT-3: data-driven EPD layout (display_layout.py).

The DEFAULT_LAYOUT is populated with this fork's pre-PORT-3 coordinates, so
the rendering must be byte-identical before/after. These tests pin that
contract: if anyone edits a coordinate, the parity assertion fails. Real
pixel parity is confirmed by the side-by-side screenshot on the HW session.
"""
import json
import os
from unittest.mock import MagicMock

import pytest

import display_layout
from display_layout import DisplayLayout


def _shared(epd_type="epd2in13_V4", currentdir="."):
    sd = MagicMock()
    sd.epd_type = epd_type
    sd.currentdir = currentdir
    return sd


class TestLayoutLoad:
    def test_default_layout_for_epd2in13_family(self):
        for epd in ("epd2in13", "epd2in13_V2", "epd2in13_V3", "epd2in13_V4"):
            layout = DisplayLayout(_shared(epd))
            assert layout.meta()["name"] == "epd2in13_default"
            assert layout.ref_size() == (122, 250)

    def test_epd2in7_layout_loaded_for_2in7(self):
        layout = DisplayLayout(_shared("epd2in7"))
        assert layout.ref_size() == (176, 264)

    def test_unknown_epd_type_falls_back_to_default(self):
        layout = DisplayLayout(_shared("epd99"))
        assert layout.ref_size() == (122, 250)


class TestElementAccess:
    def test_get_returns_element_dict(self):
        layout = DisplayLayout(_shared())
        title = layout.get("title")
        assert title == {"x": 37, "y": 5}

    def test_get_single_property(self):
        layout = DisplayLayout(_shared())
        assert layout.get("title", "x") == 37
        assert layout.get("title", "y") == 5

    def test_missing_element_returns_empty(self):
        layout = DisplayLayout(_shared())
        assert layout.get("nonexistent") == {}
        assert layout.get("nonexistent", "x") is None

    def test_frise_default_for_2in13(self):
        layout = DisplayLayout(_shared("epd2in13_V4"))
        assert layout.frise() == {"x": 0, "y": 160}

    def test_frise_for_2in7(self):
        layout = DisplayLayout(_shared("epd2in7"))
        assert layout.frise() == {"x": 50, "y": 160}

    def test_stats_have_ten_entries_with_attrs(self):
        layout = DisplayLayout(_shared())
        stats = layout.stats()
        assert len(stats) == 10
        for s in stats:
            for key in ("name", "stat_attr", "count_attr", "img", "text"):
                assert key in s, f"stat {s.get('name')} missing {key}"
            assert {"x", "y"} <= set(s["img"])
            assert {"x", "y"} <= set(s["text"])


class TestCustomOverride:
    def test_custom_json_overrides_builtin(self, tmp_path):
        custom = {"meta": {"ref_width": 200, "ref_height": 300},
                  "elements": {"title": {"x": 99, "y": 88}},
                  "frise": {"default": {"x": 1, "y": 2}}, "stats": []}
        layouts_dir = tmp_path / "resources" / "layouts"
        layouts_dir.mkdir(parents=True)
        (layouts_dir / "epd2in13_V4.json").write_text(json.dumps(custom), encoding="utf-8")

        layout = DisplayLayout(_shared("epd2in13_V4", currentdir=str(tmp_path)))
        assert layout.get("title", "x") == 99
        assert layout.ref_size() == (200, 300)
        assert layout.frise() == {"x": 1, "y": 2}

    def test_unreadable_custom_falls_back_to_builtin(self, tmp_path):
        layouts_dir = tmp_path / "resources" / "layouts"
        layouts_dir.mkdir(parents=True)
        (layouts_dir / "epd2in13_V4.json").write_text("{not valid json", encoding="utf-8")

        layout = DisplayLayout(_shared("epd2in13_V4", currentdir=str(tmp_path)))
        # Falls back to built-in DEFAULT_LAYOUT title x.
        assert layout.get("title", "x") == 37


class TestParityContract:
    """Pin the pre-PORT-3 literal values. If these change, the rendering
    changes — update only after a side-by-side screenshot confirms intent."""

    def test_known_coordinates_match_old_literals(self):
        layout = DisplayLayout(_shared())
        assert layout.get("title", "x") == 37 and layout.get("title", "y") == 5
        assert layout.get("status_image", "y") == 60  # was int(60*scale_y)
        assert layout.get("status_line1", "y") == 65
        assert layout.get("comment_text", "y_start") == 90
        assert layout.get("line_top", "y") == 20
        assert layout.get("line_mid", "y") == 59
        assert layout.get("line_lower", "y") == 87
        # Spot-check a stat (target icon/text).
        target = next(s for s in layout.stats() if s["name"] == "target")
        assert target["img"] == {"x": 8, "y": 22}
        assert target["text"] == {"x": 28, "y": 22}
