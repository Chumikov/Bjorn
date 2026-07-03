"""PORT-1: single-instance lock (fcntl.flock).

Behavioral where possible (real fcntl on Linux), with a source-level guard
for the Bjorn.py __main__ wiring (acquire + atexit + release), since
__main__ can't be driven in CI.
"""
import os
import sys

import pytest

import instance_lock


class TestInstanceLock:
    """Behavioral: the lock actually excludes a second acquirer."""

    def test_acquire_then_second_acquire_fails(self, tmp_path, monkeypatch):
        lock_path = str(tmp_path / "bjorn.lock")
        monkeypatch.setattr(instance_lock._LockState, "fd", None)

        assert instance_lock.acquire_instance_lock(lock_path) is True, (
            "First acquire must succeed.")
        assert instance_lock._LockState.fd is not None

        # A second acquire while the lock is held must fail.
        assert instance_lock.acquire_instance_lock(lock_path) is False, (
            "Second acquire while the lock is held must fail (return False), "
            "so a second Bjorn instance exits cleanly.")

        # Release restores the no-lock state.
        instance_lock.release_instance_lock()
        assert instance_lock._LockState.fd is None

        # After release, a fresh acquire must succeed again.
        assert instance_lock.acquire_instance_lock(lock_path) is True
        instance_lock.release_instance_lock()

    def test_release_without_acquire_is_noop(self, monkeypatch):
        monkeypatch.setattr(instance_lock._LockState, "fd", None)
        # Must not raise.
        instance_lock.release_instance_lock()

    @pytest.mark.skipif(sys.platform == "win32",
                        reason="fcntl unavailable on Windows")
    def test_lock_file_records_pid(self, tmp_path, monkeypatch):
        lock_path = str(tmp_path / "bjorn.lock")
        monkeypatch.setattr(instance_lock._LockState, "fd", None)

        instance_lock.acquire_instance_lock(lock_path)
        try:
            with open(lock_path) as f:
                content = f.read().strip()
            assert content == str(os.getpid()), (
                f"Lock file must contain the owning PID; got {content!r}.")
        finally:
            instance_lock.release_instance_lock()


class TestInstanceLockWiring:
    """Source-level guard: Bjorn.py __main__ must acquire + register + release."""

    def test_main_wires_lock(self):
        with open("Bjorn.py", encoding="utf-8") as f:
            src = f.read()
        main = src[src.index('if __name__ == "__main__":'):]
        assert "acquire_instance_lock()" in main, (
            "__main__ must call acquire_instance_lock() before starting.")
        assert "atexit.register(release_instance_lock)" in main, (
            "__main__ must release the lock on exit via atexit.")
        assert "sys.exit(1)" in main, (
            "__main__ must exit non-zero when the lock can't be acquired.")
