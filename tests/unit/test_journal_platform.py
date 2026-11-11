"""C-AUD-04 (decisione owner D05, PF-CROSS-PLATFORM-EXECUTION-20261110): journal fail-closed su Windows.

Su una piattaforma senza le protezioni richieste (O_NOFOLLOW + O_CLOEXEC e lock verificato) il
journal non apre nessun file: nessun ramo «più debole» che segua i reparse point o ignori i
permessi. Il motivo è dichiarato (`JOURNAL_PLATFORM_UNSUPPORTED`) e il journal non è scrivibile,
quindi ogni mutazione futura resta rifiutata (fail-closed). La parità vera arriva con MCP-WIN.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

from pickfair_mcp.journal import lock
from pickfair_mcp.journal.store import Journal


@pytest.fixture
def unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lock, "PLATFORM_SUPPORTED", False)


def test_journal_refuses_to_open_on_unsupported_platform(unsupported: None, tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    j = Journal.open(path)
    assert not j.writable
    assert j.failure_reason == "JOURNAL_PLATFORM_UNSUPPORTED"
    # nessun file creato: né il journal né il lock
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_lock_primitives_refuse_on_unsupported_platform(unsupported: None, tmp_path: Path) -> None:
    with pytest.raises(lock.JournalPlatformUnsupported):
        lock.open_lock_file(str(tmp_path / "x.lock"))
    with pytest.raises(lock.JournalPlatformUnsupported):
        lock.open_flags()
    r, w = os.pipe()
    try:
        with pytest.raises(lock.JournalPlatformUnsupported):
            lock.try_lock(r)
    finally:
        os.close(r)
        os.close(w)
    assert list(tmp_path.iterdir()) == []


def test_win32_is_unsupported_at_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con sys.platform == 'win32' il modulo si dichiara non supportato: nessun fallback a 0."""
    monkeypatch.setattr(sys, "platform", "win32")
    reloaded = importlib.reload(lock)
    try:
        assert reloaded.PLATFORM_SUPPORTED is False
        assert not hasattr(reloaded, "OPEN_FLAGS")  # il vecchio fallback a 0 non esiste più
        with pytest.raises(reloaded.JournalPlatformUnsupported):
            reloaded.open_flags()
    finally:
        monkeypatch.undo()
        importlib.reload(lock)


def test_missing_nofollow_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un POSIX senza O_NOFOLLOW non è «quasi supportato»: è non supportato."""
    monkeypatch.delattr(os, "O_NOFOLLOW")
    reloaded = importlib.reload(lock)
    try:
        assert reloaded.PLATFORM_SUPPORTED is False
    finally:
        monkeypatch.undo()
        importlib.reload(lock)


def test_supported_platform_still_protects(tmp_path: Path) -> None:
    assert lock.PLATFORM_SUPPORTED is True
    flags = lock.open_flags()
    assert flags & os.O_NOFOLLOW and flags & os.O_CLOEXEC
    j = Journal.open(tmp_path / "journal.jsonl")
    assert j.writable and j.failure_reason is None
