"""epd_preview.py — Mock Waveshare EPD driver for preview/headless testing.

Provides the same interface as the real ``epd2in13_V4`` driver (width, height,
init, getbuffer, displayPartial, Clear, sleep, FULL_UPDATE/PART_UPDATE,
epdconfig.module_exit) but ALL hardware calls are no-ops. The rendered PIL
image is still written to ``web/screen.png`` by ``display.py``, so the full
render pipeline (DisplayLayout coordinates, art assets, stats, comments)
exercises and the result is visible via the web UI — without SPI/GPIO.

Usage: set ``"epd_type": "preview"`` in ``shared_config.json``. Dimensions
match the 2.13" V4 (122x250) so the layout is pixel-accurate.
"""


class _MockEpdConfig:
    """Stand-in for epdconfig (SPI/GPIO bus manager)."""
    @staticmethod
    def module_exit(cleanup=False):
        pass


class EPD:
    """Mock EPD with the Waveshare interface — all calls are no-ops."""

    width = 122
    height = 250

    FULL_UPDATE = 0
    PART_UPDATE = 1
    lut_full_update = 0
    lut_partial_update = 1

    epdconfig = _MockEpdConfig

    def init(self, mode=None):
        pass

    def getbuffer(self, image):
        # Real drivers convert PIL → monochrome byte buffer; the preview
        # driver doesn't push to hardware, so the buffer content is unused.
        return image

    def displayPartial(self, buf):
        pass

    def display(self, buf):
        pass

    def Clear(self):
        pass

    def sleep(self):
        pass
