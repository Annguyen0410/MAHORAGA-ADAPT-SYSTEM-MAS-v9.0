"""Profile locking, two layers:

1. In-process RLock per profile dir — UI threads + bridge threads inside one
   Mei instance (re-entrant, cheap).
2. Cross-process advisory lock — a lock file beside the profile (msvcrt/
   fcntl). A second Mei instance opening the SAME profile gets a clear
   warning at startup instead of two Chromeniums silently corrupting one
   prefs.json (pre-0.6.8 bug class).

The cross-process lock is held for the whole process lifetime by main.py;
service code keeps using profile_locked() exactly as before.
"""
from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps


def profile_transaction(function):
    """Serialize an entire profile read/modify/write, not only its final write.

    Service functions take ``base_dir`` first; the RLock permits nested service
    calls while preserving that transaction boundary across UI/bridge threads.
    """
    @wraps(function)
    def locked(base_dir, *args, **kwargs):
        with profile_locked(base_dir):
            return function(base_dir, *args, **kwargs)

    return locked


_registry_lock = threading.Lock()
_locks: dict[str, threading.RLock] = {}
_process_locks: dict[str, object] = {}


def _profile_key(base_dir: str) -> str:
    return os.path.normcase(os.path.realpath(base_dir))


@contextmanager
def profile_locked(base_dir: str) -> Iterator[None]:
    key = _profile_key(base_dir)
    with _registry_lock:
        rlock = _locks.get(key)
        if rlock is None:
            rlock = threading.RLock()
            _locks[key] = rlock
    rlock.acquire()
    try:
        yield
    finally:
        rlock.release()


# ------------------------- cross-process layer -------------------------

_LOCK_NAME = ".mei-profile-lock"


def try_acquire_process_lock(base_dir: str) -> tuple[bool, str]:
    """Try to exclusively claim a profile for this process (lifetime lock).

    Returns (acquired, message). The handle is kept open in _process_locks
    until process exit, which releases it automatically."""
    key = _profile_key(base_dir)
    if key in _process_locks:
        return True, ""
    path = os.path.join(base_dir, _LOCK_NAME)
    try:
        os.makedirs(base_dir, exist_ok=True)
        handle = open(path, "a+b")
    except OSError as exc:
        return False, f"cannot open lock file: {exc}"
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False, (
            "Another Mei instance is already running this profile.\n"
            "Close the other window first, or pick a different profile."
        )
    # Hold the handle for the process lifetime.
    _process_locks[key] = handle
    return True, ""


def release_process_lock(base_dir: str) -> None:
    key = _profile_key(base_dir)
    handle = _process_locks.pop(key, None)
    if handle is None:
        return
    with contextlib.suppress(Exception):
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    with contextlib.suppress(Exception):
        handle.close()
