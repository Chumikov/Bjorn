"""display_layout.py - Data-driven EPD layout definitions (PORT-3).

Replaces ~60 hardcoded coordinate literals in ``display.py:run()`` with a
JSON-style layout dict. The ``DEFAULT_LAYOUT`` below is populated with this
fork's *current* coordinates (122x250 reference grid, epd2in13 family) so
the rendering is byte-identical before/after the refactor — verify with a
side-by-side screenshot on the HW session. ``LAYOUT_EPD2IN7`` (adapted from
upstream/ai) opens the door to 2.7" support later.

Custom overrides: drop a ``resources/layouts/<epd_type>.json`` to replace a
built-in layout without touching code.
"""
import json
import os
import logging

from logger import Logger

logger = Logger(name="display_layout.py", level=logging.INFO)

# Our fork's current 2.13" coordinates (reference grid 122x250).
# Every value here was extracted verbatim from the pre-PORT-3 display.py
# literals — do NOT change them without a side-by-side screenshot check.
DEFAULT_LAYOUT = {
    "meta": {
        "name": "epd2in13_default",
        "ref_width": 122,
        "ref_height": 250,
        "description": "2.13\" layout (this fork's coordinates)",
    },
    "elements": {
        "title":        {"x": 37, "y": 5},
        "manual_mode":  {"x": 110, "y": 170},
        "wifi_icon":    {"x": 3, "y": 3},
        "pan_icon":     {"x": 104, "y": 3},
        "usb_icon":     {"x": 90, "y": 4},
        "status_image": {"x": 3, "y": 60},
        "status_line1": {"x": 35, "y": 65},
        "status_line2": {"x": 35, "y": 75},
        "comment_text": {"x": 4, "y_start": 90},
        "border":       {"x0": 1, "y0": 1},
        "line_top":     {"y": 20},
        "line_mid":     {"y": 59},
        "line_lower":   {"y": 87},
    },
    # frise position differs per EPD type.
    "frise": {
        "default":  {"x": 0, "y": 160},
        "epd2in7":  {"x": 50, "y": 160},
    },
    # Stats row: img + text positions per stat. ``stat_attr`` is the icon
    # attribute on shared_data; ``count_attr`` is the numeric counter.
    "stats": [
        {"name": "target",    "stat_attr": "target",    "count_attr": "targetnbr",     "img": {"x": 8, "y": 22},   "text": {"x": 28, "y": 22}},
        {"name": "port",      "stat_attr": "port",      "count_attr": "portnbr",       "img": {"x": 47, "y": 22},  "text": {"x": 67, "y": 22}},
        {"name": "vuln",      "stat_attr": "vuln",      "count_attr": "vulnnbr",       "img": {"x": 86, "y": 22},  "text": {"x": 106, "y": 22}},
        {"name": "cred",      "stat_attr": "cred",      "count_attr": "crednbr",       "img": {"x": 8, "y": 41},   "text": {"x": 28, "y": 41}},
        {"name": "money",     "stat_attr": "money",     "count_attr": "coinnbr",       "img": {"x": 3, "y": 172},  "text": {"x": 3, "y": 192}},
        {"name": "level",     "stat_attr": "level",     "count_attr": "levelnbr",      "img": {"x": 2, "y": 217},  "text": {"x": 4, "y": 237}},
        {"name": "zombie",    "stat_attr": "zombie",    "count_attr": "zombiesnbr",    "img": {"x": 47, "y": 41},  "text": {"x": 67, "y": 41}},
        {"name": "networkkb", "stat_attr": "networkkb", "count_attr": "networkkbnbr",  "img": {"x": 102, "y": 190}, "text": {"x": 102, "y": 208}},
        {"name": "data",      "stat_attr": "data",      "count_attr": "datanbr",       "img": {"x": 86, "y": 41},  "text": {"x": 106, "y": 41}},
        {"name": "attacks",   "stat_attr": "attacks",   "count_attr": "attacksnbr",    "img": {"x": 100, "y": 218}, "text": {"x": 102, "y": 237}},
    ],
}

# 2.7" layout placeholder (adapted from upstream/ai; verify on real 2.7"
# hardware before use — not wired to a stat binding yet).
LAYOUT_EPD2IN7 = {
    "meta": {"name": "epd2in7_default", "ref_width": 176, "ref_height": 264,
             "description": "2.7\" layout (placeholder, untested on HW)"},
    "elements": dict(DEFAULT_LAYOUT["elements"]),
    "frise": {"default": {"x": 50, "y": 160}, "epd2in7": {"x": 50, "y": 160}},
    "stats": list(DEFAULT_LAYOUT["stats"]),
}

BUILTIN_LAYOUTS = {
    "epd2in13": DEFAULT_LAYOUT,
    "epd2in13_V2": DEFAULT_LAYOUT,
    "epd2in13_V3": DEFAULT_LAYOUT,
    "epd2in13_V4": DEFAULT_LAYOUT,
    "epd2in7": LAYOUT_EPD2IN7,
}


class DisplayLayout:
    """Resolves element coordinates for the current EPD type.

    A custom JSON at ``resources/layouts/<epd_type>.json`` overrides the
    built-in. Coordinates are in the reference grid; the caller scales them
    by ``scale_factor_x/y`` (unchanged from pre-PORT-3 behaviour).
    """

    def __init__(self, shared_data):
        self.shared_data = shared_data
        self.epd_type = getattr(shared_data, "epd_type", "epd2in13_V4")
        self._custom_dir = os.path.join(
            getattr(shared_data, "currentdir", "."), "resources", "layouts")
        self._layout = None
        self.load()

    def load(self):
        """Load the layout for ``epd_type`` (custom file overrides built-in)."""
        builtin = BUILTIN_LAYOUTS.get(self.epd_type, DEFAULT_LAYOUT)
        custom_path = os.path.join(self._custom_dir, f"{self.epd_type}.json")
        if os.path.isfile(custom_path):
            try:
                with open(custom_path, "r", encoding="utf-8") as f:
                    self._layout = json.load(f)
                logger.info(f"Loaded custom layout {custom_path}")
                return
            except (OSError, ValueError) as e:
                logger.error(f"Custom layout {custom_path} unreadable ({e}); "
                             f"falling back to built-in.")
        self._layout = builtin

    def element(self, name):
        """Return the element dict ``{x, y, ...}`` or ``{}`` if absent."""
        return self._layout.get("elements", {}).get(name, {})

    def get(self, name, prop=None):
        """Return the whole element dict, or a single property if ``prop`` set."""
        el = self.element(name)
        if prop is None:
            return el
        return el.get(prop)

    def frise(self):
        """Frise position for this EPD type (falls back to 'default')."""
        frise = self._layout.get("frise", {})
        return frise.get(self.epd_type, frise.get("default", {"x": 0, "y": 160}))

    def stats(self):
        """List of stat descriptors ({name, stat_attr, count_attr, img, text})."""
        return self._layout.get("stats", [])

    def meta(self):
        return self._layout.get("meta", {})

    def ref_size(self):
        m = self.meta()
        return (m.get("ref_width", 122), m.get("ref_height", 250))
