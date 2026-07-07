"""Behavioral tests for display.py render_frame() (COV-3).

render_frame was extracted from run() in REF-1 — it can be called directly
with a PIL image + draw, without running the threading loop. These tests
verify that the frame is rendered with all UI elements (title, icons, stats,
status, frise, border, lines, comments, main character).
"""
import os
import sys
from unittest.mock import MagicMock

import pytest
from PIL import Image, ImageDraw, ImageFont


def _make_display():
    """Build a Display instance without __init__ (no threads, no EPD)."""
    sys.modules.pop('display', None)
    import display
    from display_layout import DisplayLayout

    disp = display.Display.__new__(display.Display)
    # Real layout (already 100% tested).
    sd = MagicMock()
    sd.width = 122
    sd.height = 250
    sd.config = {"epd_type": "epd2in13_V4"}
    sd.epd_type = "epd2in13_V4"
    sd.currentdir = os.getcwd()
    sd.epd_helper = None  # headless
    sd.screen_reversed = False
    sd.web_screen_reversed = False
    sd.scale_factor_x = 1.0
    sd.scale_factor_y = 1.0

    # Real fonts (use default to avoid loading custom TTFs).
    font = ImageFont.load_default()
    sd.font_viking = font
    sd.font_arial14 = font
    sd.font_arial9 = font
    sd.font_arialbold = font

    # Real 1-bit images for paste operations (10x10 black squares).
    icon = Image.new('1', (10, 10), 0)
    for attr in ("wifi", "usb", "connected", "target", "port", "vuln",
                 "cred", "money", "level", "zombie", "networkkb",
                 "data", "attacks", "bjornstatusimage", "frise"):
        setattr(sd, attr, icon)

    # Stats counters.
    for attr in ("targetnbr", "portnbr", "vulnnbr", "crednbr", "coinnbr",
                 "levelnbr", "zombiesnbr", "networkkbnbr", "datanbr",
                 "attacksnbr"):
        setattr(sd, attr, 5)

    # Connection flags.
    sd.wifi_connected = True
    sd.pan_connected = False
    sd.usb_active = True

    # Status text.
    sd.bjornorch_status = "SSHBruteforce"
    sd.bjornstatustext = "Scanning"
    sd.bjornstatustext2 = "192.168.1.10"
    sd.bjornsay = "Hacking away at the network"

    # Main image position + content.
    main_img = Image.new('1', (20, 20), 0)
    sd.x_center1 = 51
    sd.y_bottom1 = 220

    # wrap_text returns a list of lines.
    sd.wrap_text.return_value = ["Line one", "Line two"]

    # update_bjornstatus — no-op (already set bjornstatusimage).
    sd.update_bjornstatus = MagicMock()

    disp.shared_data = sd
    disp.config = sd.config
    disp.layout = DisplayLayout(sd)
    disp.scale_factor_x = 1.0
    disp.scale_factor_y = 1.0
    disp.screen_reversed = False
    disp.web_screen_reversed = False
    disp.manual_mode_txt = ""
    disp.main_image = main_img
    return disp


class TestRenderFrame:
    def test_renders_non_blank_frame(self):
        """render_frame must produce an image with both black and white pixels."""
        disp = _make_display()
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        pixels = list(image.getdata())
        black = sum(1 for p in pixels if p == 0)
        white = sum(1 for p in pixels if p == 255)
        assert black > 50, f"Expected rendered content (black pixels); got {black}"
        assert white > 50, f"Expected background (white pixels); got {white}"

    def test_title_text_drawn(self):
        """The 'BJORN' title must appear at the layout title position."""
        disp = _make_display()
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        # Title is at layout.get("title") = {x:37, y:5}.
        # Check that there are black pixels near (37, 5).
        region = image.crop((35, 3, 60, 12))
        black_in_region = sum(1 for p in region.getdata() if p == 0)
        assert black_in_region > 0, "Title 'BJORN' should be drawn near (37,5)"

    def test_border_rectangle_drawn(self):
        """The border rectangle must be drawn (black pixels at edges)."""
        disp = _make_display()
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        # Border at (1,1)-(121,249) — check corners.
        assert image.getpixel((1, 1)) == 0, "Border top-left corner"
        assert image.getpixel((121, 249)) == 0, "Border bottom-right corner"

    def test_wifi_icon_drawn_when_connected(self):
        """wifi icon must be pasted at its layout position when wifi_connected."""
        disp = _make_display()
        disp.shared_data.wifi_connected = True
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        # wifi_icon at (3, 3) — 10x10 black square pasted there.
        assert image.getpixel((5, 5)) == 0, "wifi icon should be at (3,3)"

    def test_no_wifi_icon_when_disconnected(self):
        """wifi icon must NOT appear when wifi_connected is False."""
        disp = _make_display()
        disp.shared_data.wifi_connected = False
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        # Position (5,5) should be white (no icon pasted).
        assert image.getpixel((5, 5)) == 255, "No wifi icon expected when disconnected"

    def test_horizontal_lines_drawn(self):
        """Layout lines (top/mid/lower) must be drawn as horizontal black lines."""
        disp = _make_display()
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        # line_top y=20, line_mid y=59, line_lower y=87.
        for y in (20, 59, 87):
            assert image.getpixel((60, y)) == 0, f"Horizontal line at y={y} expected"

    def test_stats_icons_drawn(self):
        """Stats row icons must be pasted at their layout positions."""
        disp = _make_display()
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        # target icon at (8,22) — 10x10 black square.
        assert image.getpixel((10, 25)) == 0, "target stat icon should be at (8,22)"

    def test_calls_update_bjornstatus(self):
        """render_frame must call shared_data.update_bjornstatus()."""
        disp = _make_display()
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        disp.shared_data.update_bjornstatus.assert_called_once()

    def test_main_image_pasted(self):
        """The main character image must be pasted at x_center1/y_bottom1."""
        disp = _make_display()
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)
        # main_image (20x20 black) at (51, 220) → pixel at (55, 225) should be black.
        assert image.getpixel((55, 225)) == 0, "main_image should be pasted"

    def test_no_crash_without_main_image(self):
        """render_frame must not crash when main_image is None (logs error)."""
        disp = _make_display()
        disp.main_image = None
        image = Image.new('1', (122, 250), 255)
        draw = ImageDraw.Draw(image)
        disp.render_frame(image, draw)  # must not raise
