"""PORT-11: headless mode (epd_type == "none").

Bjorn must run without an e-Paper HAT attached: EPD init is skipped,
width/height fall back to reference dimensions so PIL rendering and the
web UI screen.png keep working, and every hardware call site is guarded on
epd_helper truthiness.

The shared.py test is behavioral (calls the real initialize_epd_display);
the display.py / Bjorn.py tests pin the guards as a regression net, since
those modules' __main__/threading paths can't be driven behaviorally in CI
(per AGENTS.md, source-level tests are the fallback for threading code).
"""
import inspect
import sys
import textwrap

import pytest


class TestHeadlessInit:
    """Behavioral: initialize_epd_display() headless branch."""

    def test_headless_skips_epd_and_sets_ref_dims(self):
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.config = {"epd_type": "none"}
        sd.ref_width = 122
        sd.ref_height = 250
        # epd_helper must not already exist as a real helper
        sd.epd_helper = "sentinel"

        sd.initialize_epd_display()

        assert sd.epd_helper is None, (
            "Headless mode must leave epd_helper as None (no hardware).")
        assert sd.screen_reversed is False
        assert sd.web_screen_reversed is False
        assert (sd.width, sd.height) == (122, 250), (
            "Headless mode must fall back to reference dimensions so PIL "
            f"rendering still works; got {sd.width}x{sd.height}.")

    def test_non_headless_does_not_short_circuit(self):
        """A real epd_type must NOT take the headless early-return: the
        method should attempt EPD init (and raise, since EPDHelper is mocked
        out / hardware absent in CI). We assert it does not set epd_helper
        to None via the headless branch."""
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        sd.config = {"epd_type": "epd2in13_V4"}
        sd.ref_width = 122
        sd.ref_height = 250

        # The real EPD init path raises in CI (no SPI / mocked module).
        with pytest.raises(Exception):
            sd.initialize_epd_display()


class TestHeadlessGuards:
    """Regression pin: hardware call sites must be guarded for headless."""

    def test_display_run_guards_init_partial_update(self):
        sys.modules.pop('display', None)
        import display
        src = inspect.getsource(display.Display.run)
        assert "if self.epd_helper:" in src, (
            "Display.run must guard epd_helper.init_partial_update() and "
            "display_partial() so headless mode (epd_helper=None) renders "
            "to screen.png without touching hardware.")

    def test_display_init_guards_epd_helper(self):
        sys.modules.pop('display', None)
        import display
        src = inspect.getsource(display.Display.__init__)
        assert "if self.epd_helper:" in src, (
            "Display.__init__ must guard init_partial_update() on epd_helper.")

    def test_bjorn_main_skips_display_thread_in_headless(self):
        """Bjorn.__main__ must NOT start the display thread in headless mode
        and must tolerate display_thread being None on cleanup."""
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        main_block = src[src.index('if __name__ == "__main__":'):]
        assert 'epd_type") == "none"' in main_block, (
            "__main__ must branch on epd_type=='none' before starting display.")
        assert "display_thread = None" in main_block, (
            "Headless branch must set display_thread = None.")
        # Cleanup must not AttributeError when display_thread is None.
        assert "if display_thread and display_thread.is_alive()" in main_block, (
            "Cleanup must guard display_thread None-ness before .is_alive().")
