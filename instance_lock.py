"""PORT-1: single-instance lock.

Prevents two Bjorn processes from running concurrently and racing on the
shared data/config/log files. Implemented as an exclusive ``flock`` on
``/tmp/bjorn.lock``; the second process exits cleanly with a non-zero
status. On non-POSIX hosts (no ``fcntl``) the lock degrades to a no-op so
dev/test there isn't blocked.
"""
import os
import logging

try:
    import fcntl
except ImportError:  # non-POSIX (e.g. Windows)
    fcntl = None

from logger import Logger

logger = Logger(name="instance_lock.py", level=logging.INFO)

LOCK_PATH = "/tmp/bjorn.lock"


class _LockState:
    """Mutable holder for the lock file descriptor (avoids module globals)."""
    fd = None


def acquire_instance_lock(path=LOCK_PATH):
    """Acquire an exclusive flock.

    Returns True if this process holds the lock, False if another Bjorn is
    already running. ``path`` is overridable (used by tests).
    """
    if fcntl is None:
        logger.warning("fcntl unavailable — instance lock disabled.")
        return True
    fd = None
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as e:
        logger.error(f"Another Bjorn instance is already running "
                     f"(lock {path} held). Exiting. ({e})")
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return False
    # Record owning PID for diagnostics (visible via lsof / cat).
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
    except OSError:
        pass
    _LockState.fd = fd
    return True


def release_instance_lock():
    """Release the lock acquired by ``acquire_instance_lock``."""
    if _LockState.fd is None:
        return
    try:
        if fcntl is not None:
            fcntl.flock(_LockState.fd, fcntl.LOCK_UN)
        os.close(_LockState.fd)
    except OSError as e:
        logger.error(f"Error releasing instance lock: {e}")
    finally:
        _LockState.fd = None

