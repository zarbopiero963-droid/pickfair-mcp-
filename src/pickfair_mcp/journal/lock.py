"""Lock esclusivo tra processi sul journal (POSIX flock) e apertura protetta dei file.

C-AUD-04 (decisione owner D05, PF-CROSS-PLATFORM-EXECUTION-20261110): il journal si apre solo
dove le protezioni richieste esistono davvero, cioè ``O_NOFOLLOW`` (nessun symlink seguito),
``O_CLOEXEC`` (nessuna eredità del descrittore) e ``flock`` verificato. Altrove, e in particolare
su Windows, il journal è **fail-closed**: nessun file viene aperto e il motivo è dichiarato
(``JOURNAL_PLATFORM_UNSUPPORTED``). Non esiste un ramo più debole (niente apertura che segua i
reparse point, niente lock non verificato). La parità Windows equivalente arriva con MCP-WIN.
"""

from __future__ import annotations

import os
import sys
from typing import Final

_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", None)
_CLOEXEC: Final = getattr(os, "O_CLOEXEC", None)

PLATFORM_SUPPORTED: bool = sys.platform != "win32" and _NOFOLLOW is not None and _CLOEXEC is not None


class JournalPlatformUnsupported(OSError):
    """La piattaforma non offre le protezioni richieste dal journal: nessuna apertura."""


def _require_supported() -> None:
    if not PLATFORM_SUPPORTED:
        raise JournalPlatformUnsupported("JOURNAL_PLATFORM_UNSUPPORTED")


def open_flags() -> int:
    """Flag di protezione per ogni apertura del journal; solo su piattaforma supportata."""
    _require_supported()
    assert _NOFOLLOW is not None and _CLOEXEC is not None  # garantito da PLATFORM_SUPPORTED
    return _NOFOLLOW | _CLOEXEC


def try_lock(fd: int) -> bool:
    """True se il lock esclusivo non bloccante è stato acquisito."""
    _require_supported()
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def open_lock_file(path: str) -> int:
    return os.open(path, os.O_RDWR | os.O_CREAT | open_flags(), 0o600)
