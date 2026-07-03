"""PORT-9: shared bruteforce helpers (progress tracking + password plan)."""
from unittest.mock import MagicMock

import pytest

from actions.bruteforce_common import (
    ProgressTracker, build_exhaustive_passwords, merged_password_plan,
    _unique_keep_order,
)


def _sd(exhaustive=False, **kw):
    sd = MagicMock()
    sd.bjorn_progress = ""
    sd.bruteforce_exhaustive_enabled = exhaustive
    for k, v in kw.items():
        setattr(sd, f"bruteforce_exhaustive_{k}", v)
    return sd


class TestProgressTracker:
    def test_init_sets_zero_percent(self):
        sd = _sd()
        ProgressTracker(sd, 100)
        assert sd.bjorn_progress == "0%"

    def test_advance_updates_percentage(self):
        sd = _sd()
        t = ProgressTracker(sd, 10)
        t._last_emit = 0.0  # force emit on every advance
        t.advance(5)
        assert sd.bjorn_progress == "50%"

    def test_advance_caps_at_100(self):
        sd = _sd()
        t = ProgressTracker(sd, 10)
        t._last_emit = 0.0
        t.advance(1000)
        assert sd.bjorn_progress == "100%"

    def test_set_complete_and_clear(self):
        sd = _sd()
        t = ProgressTracker(sd, 10)
        t.set_complete()
        assert sd.bjorn_progress == "100%"
        t.clear()
        assert sd.bjorn_progress == ""

    def test_thread_safe(self):
        import threading
        sd = _sd()
        t = ProgressTracker(sd, 1000)
        def worker():
            for _ in range(100):
                t.advance(1)
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert t.attempted == 1000
        assert sd.bjorn_progress == "100%"

    def test_total_clamped_to_min_one(self):
        sd = _sd()
        t = ProgressTracker(sd, 0)
        assert t.total == 1


class TestExhaustiveGenerator:
    def test_disabled_by_default(self):
        assert build_exhaustive_passwords(_sd(exhaustive=False), []) == []

    def test_enabled_generates_bounded_candidates(self):
        sd = _sd(exhaustive=True, min_length=1, max_length=2,
                 lowercase=True, uppercase=False, digits=False, symbols=False,
                 max_candidates=5)
        pwds = build_exhaustive_passwords(sd, [])
        assert len(pwds) == 5, "Must respect max_candidates bound."
        assert all(len(p) <= 2 for p in pwds)
        assert all(c.islower() for p in pwds for c in p)

    def test_existing_passwords_excluded(self):
        sd = _sd(exhaustive=True, min_length=1, max_length=1,
                 lowercase=True, uppercase=False, digits=False, symbols=False,
                 max_candidates=100)
        pwds = build_exhaustive_passwords(sd, ["a", "b"])
        assert "a" not in pwds
        assert "b" not in pwds
        assert "c" in pwds

    def test_require_mix_filters(self):
        # With lowercase+digits and require_mix, single-char "a" (no digit)
        # must be filtered; "1" (no lower) too. Only 2-char mixed survive.
        sd = _sd(exhaustive=True, min_length=2, max_length=2,
                 lowercase=True, uppercase=False, digits=True, symbols=False,
                 require_mix=True, max_candidates=100)
        pwds = build_exhaustive_passwords(sd, [])
        for p in pwds:
            has_lower = any(c.islower() for c in p)
            has_digit = any(c.isdigit() for c in p)
            assert has_lower and has_digit


class TestPasswordPlan:
    def test_merged_plan_dedups_dictionary(self):
        sd = _sd(exhaustive=False)
        d, f = merged_password_plan(sd, ["pw1", "pw2", "pw1"])
        assert d == ["pw1", "pw2"]
        assert f == []

    def test_merged_plan_appends_fallback_when_enabled(self):
        sd = _sd(exhaustive=True, min_length=1, max_length=1,
                 lowercase=True, uppercase=False, digits=False, symbols=False,
                 max_candidates=3)
        d, f = merged_password_plan(sd, ["a"])
        assert d == ["a"]
        assert len(f) == 3
        assert "a" not in f  # existing excluded from fallback


class TestConfigKeys:
    def test_default_config_has_bruteforce_keys(self):
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        cfg = sd.get_default_config()
        for key in ("bruteforce_exhaustive_enabled",
                    "bruteforce_exhaustive_min_length",
                    "bruteforce_exhaustive_max_length",
                    "bruteforce_exhaustive_max_candidates",
                    "bruteforce_exhaustive_lowercase",
                    "bruteforce_exhaustive_uppercase",
                    "bruteforce_exhaustive_digits",
                    "bruteforce_exhaustive_symbols",
                    "bruteforce_exhaustive_symbols_chars"):
            assert key in cfg, f"missing config key {key}"
        assert cfg["bruteforce_exhaustive_enabled"] is False, (
            "Exhaustive generator must be dormant by default.")
