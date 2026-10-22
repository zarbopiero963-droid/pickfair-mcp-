"""Lock esclusivo tra processi sul journal (POSIX flock, Windows msvcrt)."""

from __future__ import annotations

import os
import sys
from typing import Final

# Nessun symlink seguito e nessuna eredità del descrittore nei sottoprocessi.
OPEN_FLAGS: Final = 0 if sys.platform == "win32" else os.O_NOFOLLOW | os.O_CLOEXEC


def try_lock(fd: int) -> bool:
    """True se il lock esclusivo non bloccante è stato acquisito."""
    try:
        if sys.platform == "win32":  # pragma: no mutate
            import msvcrt

            # Ramo Windows: verificato in MCP-07a (packaging Windows), non su CI Linux.
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # pragma: no mutate
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def open_lock_file(path: str) -> int:
    return os.open(path, os.O_RDWR | os.O_CREAT | OPEN_FLAGS, 0o600)
