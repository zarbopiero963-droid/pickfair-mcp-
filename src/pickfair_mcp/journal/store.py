"""Journal append-only su file (JSON Lines con checksum per riga).

Ogni richiesta che produrrà una mutazione upstream riceve un `request_id`
stabile e una voce persistita (write + fsync) PRIMA dell'invio; l'esito
(`operation_id`, `correlation_id`) è persistito dopo. Regole:

- stessa chiave logica ⇒ stessa voce, nessuna nuova chiamata upstream;
- nessun replay al riavvio: voce iniziata ma non inviata ⇒ NOT_SENT,
  voce inviata senza esito ⇒ AMBIGUOUS (si verifica solo con letture);
- esito incerto (timeout, errore, risposta non valida) ⇒ AMBIGUOUS, mai retry;
- journal corrotto, illeggibile, sostituito o bloccato ⇒ fail-closed per le
  mutazioni (`JOURNAL_UNAVAILABLE`); le letture restano consentite;
- un solo processo scrittore (lock esclusivo).

Il journal registra, non decide: nessuna autorità finanziaria. Non contiene
payload né segreti: solo identificativi validati e l'hash della chiave logica.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Final

import anyio

from pickfair_mcp.audit import audit_event
from pickfair_mcp.envelope import REQUEST_ID_PATTERN
from pickfair_mcp.errors import ErrorCode, ToolError
from pickfair_mcp.journal.lock import OPEN_FLAGS, open_lock_file, try_lock

JOURNAL_VERSION: Final = 1
_REQ_RE: Final = re.compile(REQUEST_ID_PATTERN)
_UPSTREAM_ID_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_HEX64_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_READ_CHUNK: Final = 1 << 16


class EntryStatus(Enum):
    IN_FLIGHT = "IN_FLIGHT"
    ACCEPTED = "ACCEPTED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_SENT = "NOT_SENT"


_FINAL: Final = frozenset({EntryStatus.ACCEPTED, EntryStatus.AMBIGUOUS, EntryStatus.NOT_SENT})


@dataclass(frozen=True)
class UpstreamAck:
    operation_id: str
    correlation_id: str


@dataclass(frozen=True)
class Entry:
    request_id: str
    key_hash: str
    status: EntryStatus
    sent: bool
    operation_id: str | None = None
    correlation_id: str | None = None
    deduplicated: bool = field(default=False, compare=False)


class JournalUnavailable(Exception):
    """Mutazione rifiutata: il journal non è scrivibile (fail-closed)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def to_tool_error(self) -> ToolError:
        return ToolError(ErrorCode.JOURNAL_UNAVAILABLE, reasons=(self.reason,))


class _Corrupt(Exception):
    pass


def new_request_id() -> str:
    return "req_" + secrets.token_hex(16)


def key_hash(key: str) -> str:
    return hashlib.sha256(b"pickfair-mcp:journal-key:v1\x00" + key.encode("utf-8")).hexdigest()


def _crc(record: dict[str, Any]) -> str:
    body = json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def _valid_ack(ack: object) -> bool:
    return (
        isinstance(ack, UpstreamAck)
        and isinstance(ack.operation_id, str)
        and isinstance(ack.correlation_id, str)
        and _UPSTREAM_ID_RE.fullmatch(ack.operation_id) is not None
        and _UPSTREAM_ID_RE.fullmatch(ack.correlation_id) is not None
    )


class Journal:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None
        self._lock_fd: int | None = None
        self._ino: tuple[int, int] | None = None
        self._seq = 0
        self._entries: dict[str, Entry] = {}
        self._by_key: dict[str, str] = {}
        self._inflight: dict[str, anyio.Event] = {}
        self.failure_reason: str | None = None

    # ---------------------------------------------------------------- apertura
    @classmethod
    def open(cls, path: Path) -> Journal:
        journal = cls(path)
        journal._open()
        return journal

    @property
    def writable(self) -> bool:
        return self.failure_reason is None and self._fd is not None

    def _fail(self, reason: str) -> None:
        if self.failure_reason is None:
            self.failure_reason = reason

    def _open(self) -> None:
        path = self._path
        if not path.is_absolute() or ".." in path.parts:
            self._fail("JOURNAL_PATH_INVALID")
            return
        try:
            self._lock_fd = open_lock_file(str(path) + ".lock")
        except OSError:
            self._fail("JOURNAL_IO")
            return
        if not try_lock(self._lock_fd):
            self._fail("JOURNAL_LOCKED")
            return
        try:
            fd = os.open(str(path), os.O_RDWR | os.O_CREAT | os.O_APPEND | OPEN_FLAGS, 0o600)
        except OSError:
            self._fail("JOURNAL_IO")
            return
        self._fd = fd
        try:
            st = os.fstat(fd)
            if not _is_regular(st.st_mode):
                self._fail("JOURNAL_IO")
                return
            self._ino = (st.st_dev, st.st_ino)
            raw = _read_all(fd)
        except OSError:
            self._fail("JOURNAL_IO")
            return
        try:
            self._load(raw)
        except _Corrupt:
            self._entries.clear()
            self._by_key.clear()
            self._fail("JOURNAL_CORRUPT")
            return
        if self._seq == 0:
            try:
                self._append({"kind": "header", "journal_id": secrets.token_hex(16)})
            except JournalUnavailable:
                return

    def _load(self, raw: bytes) -> None:
        if not raw:
            return
        if not raw.endswith(b"\n"):
            raise _Corrupt
        for index, line in enumerate(raw[:-1].split(b"\n")):
            try:
                rec = json.loads(line.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                raise _Corrupt from None
            if not isinstance(rec, dict):
                raise _Corrupt
            crc = rec.pop("crc", None)
            if crc != _crc(rec) or rec.get("v") != JOURNAL_VERSION or rec.get("seq") != index:
                raise _Corrupt
            self._apply(rec, first=index == 0)
            self._seq = index + 1

    def _apply(self, rec: dict[str, Any], *, first: bool) -> None:
        kind = rec.get("kind")
        if first != (kind == "header"):
            raise _Corrupt
        if kind == "header":
            return
        rid = rec.get("request_id")
        if not isinstance(rid, str) or not _REQ_RE.fullmatch(rid):
            raise _Corrupt
        current = self._entries.get(rid)
        if kind == "begin":
            kh = rec.get("key_hash")
            if current is not None or not isinstance(kh, str) or not _HEX64_RE.fullmatch(kh):
                raise _Corrupt
            if kh in self._by_key:
                raise _Corrupt
            self._entries[rid] = Entry(rid, kh, EntryStatus.IN_FLIGHT, sent=False)
            self._by_key[kh] = rid
        elif kind == "sent":
            if current is None or current.sent or current.status is not EntryStatus.IN_FLIGHT:
                raise _Corrupt
            self._entries[rid] = replace(current, sent=True)
        elif kind == "outcome":
            if current is None or current.status is not EntryStatus.IN_FLIGHT:
                raise _Corrupt
            try:
                status = EntryStatus(rec.get("status"))
            except ValueError:
                raise _Corrupt from None
            op, corr = rec.get("operation_id"), rec.get("correlation_id")
            if status is EntryStatus.ACCEPTED:
                if not current.sent or not _valid_ack(UpstreamAck(op, corr)):  # type: ignore[arg-type]
                    raise _Corrupt
            elif op is not None or corr is not None or status not in _FINAL:
                raise _Corrupt
            elif status is EntryStatus.NOT_SENT and current.sent:
                raise _Corrupt
            elif status is EntryStatus.AMBIGUOUS and not current.sent:
                raise _Corrupt
            self._entries[rid] = replace(
                current, status=status, operation_id=op, correlation_id=corr
            )
        else:
            raise _Corrupt

    # --------------------------------------------------------------- scrittura
    def _append(self, record: dict[str, Any]) -> None:
        if not self.writable or self._fd is None:
            raise JournalUnavailable(self.failure_reason or "JOURNAL_CLOSED")
        try:
            st = os.stat(self._path, follow_symlinks=False)
            if (st.st_dev, st.st_ino) != self._ino:
                self._fail("JOURNAL_REPLACED")
                raise JournalUnavailable("JOURNAL_REPLACED")
            rec = {**record, "v": JOURNAL_VERSION, "seq": self._seq}
            rec["crc"] = _crc(rec)
            data = (json.dumps(rec, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")
            view = memoryview(data)
            while view:
                written = os.write(self._fd, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(self._fd)
        except OSError:
            self._fail("JOURNAL_IO")
            raise JournalUnavailable("JOURNAL_IO") from None
        self._seq += 1

    def begin(self, key: str) -> Entry:
        kh = key_hash(key)
        if kh in self._by_key:
            raise ValueError("chiave già presente")
        rid = new_request_id()
        self._append({"kind": "begin", "request_id": rid, "key_hash": kh})
        entry = Entry(rid, kh, EntryStatus.IN_FLIGHT, sent=False)
        self._entries[rid] = entry
        self._by_key[kh] = rid
        return entry

    def mark_sent(self, entry: Entry) -> Entry:
        current = self._entries[entry.request_id]
        if current.sent or current.status is not EntryStatus.IN_FLIGHT:
            raise ValueError("voce non inviabile")
        self._append({"kind": "sent", "request_id": entry.request_id})
        updated = replace(current, sent=True)
        self._entries[entry.request_id] = updated
        return updated

    def complete(self, entry: Entry, ack: UpstreamAck | None) -> Entry:
        current = self._entries[entry.request_id]
        if current.status is not EntryStatus.IN_FLIGHT or not current.sent:
            raise ValueError("voce non completabile")
        if ack is not None and _valid_ack(ack):
            updated = replace(
                current,
                status=EntryStatus.ACCEPTED,
                operation_id=ack.operation_id,
                correlation_id=ack.correlation_id,
            )
        else:
            updated = replace(current, status=EntryStatus.AMBIGUOUS)
        self._close_entry(updated)
        return updated

    def _close_entry(self, updated: Entry) -> None:
        self._append(
            {
                "kind": "outcome",
                "request_id": updated.request_id,
                "status": updated.status.value,
                "operation_id": updated.operation_id,
                "correlation_id": updated.correlation_id,
            }
        )
        self._entries[updated.request_id] = updated
        audit_event(
            "journal_entry",
            request_id=updated.request_id,
            operation_id=updated.operation_id,
            correlation_id=updated.correlation_id,
            outcome=updated.status.value,
        )

    # ------------------------------------------------------------- esecuzione
    async def execute(
        self,
        key: str,
        send: Callable[[str], Awaitable[UpstreamAck]],
        *,
        timeout_s: float,
    ) -> Entry:
        """Unico percorso per una mutazione: journal prima, un solo invio, mai retry."""
        kh = key_hash(key)
        existing = self._by_key.get(kh)
        if existing is not None:
            event = self._inflight.get(kh)
            if event is not None:
                await event.wait()
            current = self._entries[existing]
            if current.status is EntryStatus.IN_FLIGHT:
                raise JournalUnavailable(self.failure_reason or "JOURNAL_IO")
            return replace(current, deduplicated=True)
        if not self.writable:
            raise JournalUnavailable(self.failure_reason or "JOURNAL_CLOSED")
        entry = self.begin(key)
        event = anyio.Event()
        self._inflight[kh] = event
        try:
            entry = self.mark_sent(entry)
            ack: UpstreamAck | None
            try:
                with anyio.fail_after(timeout_s):
                    ack = await send(entry.request_id)
            except Exception:  # noqa: BLE001 - esito incerto: AMBIGUOUS, mai testo upstream
                ack = None
            return self.complete(entry, ack)
        finally:
            event.set()
            del self._inflight[kh]

    def recover(self) -> tuple[Entry, ...]:
        """Chiude le voci aperte senza replay; restituisce le voci AMBIGUOUS."""
        for rid, entry in list(self._entries.items()):
            if entry.status is not EntryStatus.IN_FLIGHT or entry.key_hash in self._inflight:
                continue
            status = EntryStatus.AMBIGUOUS if entry.sent else EntryStatus.NOT_SENT
            closed = replace(entry, status=status)
            if self.writable:
                self._close_entry(closed)
            else:
                self._entries[rid] = closed
        return tuple(e for e in self._entries.values() if e.status is EntryStatus.AMBIGUOUS)

    # ---------------------------------------------------------------- letture
    def lookup(self, request_id: str) -> Entry | None:
        return self._entries.get(request_id)

    def entries(self) -> tuple[Entry, ...]:
        return tuple(self._entries.values())

    # ---------------------------------------------------------------- chiusura
    def close(self) -> None:
        for fd in (self._fd, self._lock_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self._fd = self._lock_fd = None
        self._fail("JOURNAL_CLOSED")

    def abandon_for_test(self) -> None:
        """Simula un crash: rilascia i descrittori senza scrivere nulla."""
        self.close()


def _is_regular(mode: int) -> bool:
    return stat.S_ISREG(mode)


def _read_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while chunk := os.read(fd, _READ_CHUNK):
        chunks.append(chunk)
    return b"".join(chunks)
