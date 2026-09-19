"""Cross-process file lock (stdlib only, POSIX + Windows).

Wraps fcntl.flock on POSIX and msvcrt.locking on Windows. Used by
GoalStore and HarnessState so two REPLs / CI jobs sharing one workspace
don't silently last-writer-win each other's JSON stores.
"""
import os
from contextlib import contextmanager
from typing import Iterator


import os
import threading
from contextlib import contextmanager
from typing import Iterator

_held = threading.local()


def _held_paths() -> set:
    if not hasattr(_held, "paths"):
        _held.paths = set()
    return _held.paths


@contextmanager
def locked(path: str, timeout: float = 10.0) -> Iterator[None]:
    """Holds an exclusive lock on `<path>.lock` for the block duration.

    Re-entrant within one thread: nested acquisition of the same path is
    a no-op (the outer holder owns the fd).
    """
    key = os.path.abspath(path)
    if key in _held_paths():
        yield
        return
    import time
    lock_path = path + ".lock"
    parent = os.path.dirname(os.path.abspath(lock_path))
    os.makedirs(parent, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        _acquire(fd, timeout)
        _held_paths().add(key)
        try:
            yield
        finally:
            _held_paths().discard(key)
            _release(fd)
    finally:
        os.close(fd)


def _acquire(fd: int, timeout: float) -> None:
    import time
    try:
        import fcntl
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except (BlockingIOError, OSError):
                if time.time() >= deadline:
                    raise TimeoutError("flock timeout acquiring store lock")
                time.sleep(0.02)
    except ImportError:
        import msvcrt
        deadline = time.time() + timeout
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError("lock timeout acquiring store lock")
                time.sleep(0.02)


def _release(fd: int) -> None:
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
    except ImportError:
        try:
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
