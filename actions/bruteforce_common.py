"""bruteforce_common.py - Shared helpers for bruteforce actions (PORT-9).

Progress tracking (``ProgressTracker``) and an optional exhaustive password
generator. Pure Python — no SQLite/AI deps. The connectors keep their CSV
persistence; this module only standardises progress reporting (to
``shared_data.bjorn_progress``) and the password plan.

The exhaustive generator ships DORMANT (``bruteforce_exhaustive_enabled``
defaults to False) — no behaviour change unless an operator opts in.

Adapted from ``upstream/ai:actions/bruteforce_common.py``.
"""
import itertools
import threading
import time
from typing import Iterable, List, Sequence


def _unique_keep_order(items):
    seen = set()
    out = []
    for raw in items:
        s = str(raw or "")
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def build_exhaustive_passwords(shared_data, existing_passwords):
    """Build optional exhaustive password candidates from runtime config.

    Returns a bounded list (``max_candidates``) to stay Pi Zero friendly.
    Empty unless ``bruteforce_exhaustive_enabled`` is True.
    """
    if not bool(getattr(shared_data, "bruteforce_exhaustive_enabled", False)):
        return []

    min_len = max(1, int(getattr(shared_data, "bruteforce_exhaustive_min_length", 1)))
    max_len = max(min_len, min(int(getattr(shared_data, "bruteforce_exhaustive_max_length", 4)), 8))
    max_candidates = max(0, min(int(getattr(shared_data, "bruteforce_exhaustive_max_candidates", 2000)), 200000))
    if max_candidates == 0:
        return []

    require_mix = bool(getattr(shared_data, "bruteforce_exhaustive_require_mix", False))
    use_lower = bool(getattr(shared_data, "bruteforce_exhaustive_lowercase", True))
    use_upper = bool(getattr(shared_data, "bruteforce_exhaustive_uppercase", True))
    use_digits = bool(getattr(shared_data, "bruteforce_exhaustive_digits", True))
    use_symbols = bool(getattr(shared_data, "bruteforce_exhaustive_symbols", False))
    symbols = str(getattr(shared_data, "bruteforce_exhaustive_symbols_chars", "!@#$%^&*"))

    groups = []
    if use_lower:
        groups.append("abcdefghijklmnopqrstuvwxyz")
    if use_upper:
        groups.append("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if use_digits:
        groups.append("0123456789")
    if use_symbols and symbols:
        groups.append(symbols)
    if not groups:
        return []

    charset = "".join(groups)
    existing = set(str(x) for x in (existing_passwords or []))
    generated = []

    for ln in range(min_len, max_len + 1):
        for tup in itertools.product(charset, repeat=ln):
            pwd = "".join(tup)
            if pwd in existing:
                continue
            if require_mix and len(groups) > 1:
                if not all(any(ch in grp for ch in pwd) for grp in groups):
                    continue
            generated.append(pwd)
            if len(generated) >= max_candidates:
                return generated
    return generated


class ProgressTracker:
    """Thread-safe progress helper for bruteforce actions.

    Writes a percentage string to ``shared_data.bjorn_progress`` (consumed
    by the web UI / EPD). Replaces the rich ``Progress`` TTY bar — which is
    invisible on a headless RPi service anyway.
    """

    def __init__(self, shared_data, total_attempts):
        self.shared_data = shared_data
        self.total = max(1, int(total_attempts))
        self.attempted = 0
        self._lock = threading.Lock()
        self._last_emit = 0.0
        self.shared_data.bjorn_progress = "0%"

    def advance(self, step=1):
        now = time.time()
        with self._lock:
            self.attempted += max(1, int(step))
            attempted = self.attempted
            total = self.total
            if now - self._last_emit < 0.2 and attempted < total:
                return
            self._last_emit = now
        pct = min(100, int((attempted * 100) / total))
        self.shared_data.bjorn_progress = f"{pct}%"

    def set_complete(self):
        self.shared_data.bjorn_progress = "100%"

    def clear(self):
        self.shared_data.bjorn_progress = ""


def merged_password_plan(shared_data, dictionary_passwords):
    """Return ``(dictionary_passwords, fallback_passwords)`` unique-ordered.

    The fallback (exhaustive) list is empty unless exhaustive mode is on.
    """
    dictionary = _unique_keep_order(dictionary_passwords or [])
    fallback = build_exhaustive_passwords(shared_data, dictionary)
    return dictionary, _unique_keep_order(fallback)
