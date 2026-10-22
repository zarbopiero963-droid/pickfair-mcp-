"""MCP-01b: casi limite del journal (formato stabile, motivi fail-closed, integrità)."""

from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path
from typing import Any

import anyio
import pytest

from pickfair_mcp.adapters.base import UpstreamUnavailable
from pickfair_mcp.errors import ErrorCode, ToolError
from pickfair_mcp.journal import (
    Entry,
    EntryStatus,
    Journal,
    JournalUnavailable,
    UpstreamAck,
    read_with_retry,
)
from pickfair_mcp.journal import store as store_mod

pytestmark = pytest.mark.anyio

RID1 = "req_" + "1" * 32
RID2 = "req_" + "2" * 32
KH1 = "a" * 64
KH2 = "b" * 64
JID = "f" * 32


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _write(path: Path, records: list[dict[str, Any]], *, header: bool = True) -> None:
    rows = ([{"kind": "header", "journal_id": JID}] if header else []) + records
    out = []
    for seq, rec in enumerate(rows):
        full = {**rec, "v": 1, "seq": seq}
        full["crc"] = store_mod._crc(full)
        out.append(json.dumps(full, sort_keys=True))
    path.write_text("".join(line + "\n" for line in out))


def _begin(rid: str = RID1, kh: str = KH1) -> dict[str, Any]:
    return {"kind": "begin", "request_id": rid, "key_hash": kh}


def _sent(rid: str = RID1) -> dict[str, Any]:
    return {"kind": "sent", "request_id": rid}


def _out(status: str, op: Any = None, corr: Any = None, rid: str = RID1) -> dict[str, Any]:
    return {
        "kind": "outcome",
        "request_id": rid,
        "status": status,
        "operation_id": op,
        "correlation_id": corr,
    }


VALID: dict[str, list[dict[str, Any]]] = {
    "accepted": [_begin(), _sent(), _out("ACCEPTED", "op", "c")],
    "ambiguous": [_begin(), _sent(), _out("AMBIGUOUS")],
    "not_sent": [_begin(), _out("NOT_SENT")],
    "open_unsent": [_begin()],
    "two": [_begin(), _out("NOT_SENT"), _begin(RID2, KH2), _sent(RID2)],
}

CORRUPT: dict[str, list[dict[str, Any]]] = {
    "rid_not_str": [{"kind": "begin", "request_id": 5, "key_hash": KH1}],
    "rid_bad": [_begin("req_bad")],
    "kh_not_str": [{"kind": "begin", "request_id": RID1, "key_hash": 7}],
    "kh_bad": [_begin(kh="XYZ")],
    "begin_twice": [_begin(), _begin()],
    "kh_duplicate": [_begin(), _begin(RID2, KH1)],
    "sent_without_begin": [_sent()],
    "sent_twice": [_begin(), _sent(), _sent()],
    "sent_after_outcome": [_begin(), _out("NOT_SENT"), _sent()],
    "outcome_without_begin": [_out("NOT_SENT")],
    "outcome_twice": [_begin(), _out("NOT_SENT"), _out("NOT_SENT")],
    "accepted_unsent": [_begin(), _out("ACCEPTED", "op", "c")],
    "accepted_bad_op": [_begin(), _sent(), _out("ACCEPTED", "bad op", "c")],
    "accepted_no_corr": [_begin(), _sent(), _out("ACCEPTED", "op", None)],
    "not_sent_with_op": [_begin(), _out("NOT_SENT", "op", None)],
    "ambiguous_with_corr": [_begin(), _sent(), _out("AMBIGUOUS", None, "c")],
    "ambiguous_with_op": [_begin(), _sent(), _out("AMBIGUOUS", "op", None)],
    "outcome_in_flight": [_begin(), _sent(), _out("IN_FLIGHT")],
    "outcome_unknown": [_begin(), _sent(), _out("DONE")],
    "not_sent_after_sent": [_begin(), _sent(), _out("NOT_SENT")],
    "ambiguous_unsent": [_begin(), _out("AMBIGUOUS")],
    "unknown_kind": [{"kind": "replay", "request_id": RID1}],
    "second_header": [{"kind": "header", "journal_id": JID}],
}


@pytest.mark.parametrize("name", sorted(VALID))
def test_valid_journals_load_writable(tmp_path: Path, name: str) -> None:
    p = tmp_path / "j.jsonl"
    _write(p, VALID[name])
    j = Journal.open(p)
    assert j.writable, j.failure_reason
    j.close()


def test_loaded_entries_are_exact(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    _write(p, VALID["accepted"])
    j = Journal.open(p)
    assert j.entries() == (Entry(RID1, KH1, EntryStatus.ACCEPTED, True, "op", "c"),)
    j.close()
    _write(p, VALID["open_unsent"])
    j = Journal.open(p)
    assert j.lookup(RID1) == Entry(RID1, KH1, EntryStatus.IN_FLIGHT, False)
    j.close()


@pytest.mark.parametrize("name", sorted(CORRUPT))
def test_structural_corruption_fails_closed(tmp_path: Path, name: str) -> None:
    p = tmp_path / "j.jsonl"
    _write(p, CORRUPT[name])
    j = Journal.open(p)
    assert not j.writable
    assert j.failure_reason == "JOURNAL_CORRUPT"
    assert j.entries() == ()
    j.close()


@pytest.mark.parametrize(
    "header",
    [
        {"kind": "header"},
        {"kind": "header", "journal_id": 5},
        {"kind": "header", "journal_id": "f" * 34},
        {"kind": "header", "journal_id": "f" * 64},
    ],
)
def test_header_validated(tmp_path: Path, header: dict[str, Any]) -> None:
    p = tmp_path / "j.jsonl"
    _write(p, [header], header=False)
    j = Journal.open(p)
    assert j.failure_reason == "JOURNAL_CORRUPT"
    j.close()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(v=2),
        lambda r: r.update(seq=5),
        lambda r: r.pop("crc"),
        lambda r: r.update(crc="0" * 64),
    ],
)
def test_record_envelope_checked_with_valid_crc(tmp_path: Path, mutate: Any) -> None:
    p = tmp_path / "j.jsonl"
    _write(p, VALID["accepted"])
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    rec = rows[1]
    mutate(rec)
    if "crc" in rec and rec["crc"] != "0" * 64:
        rec.pop("crc")
        rec["crc"] = store_mod._crc(rec)
    rows[1] = rec
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    j = Journal.open(p)
    assert j.failure_reason == "JOURNAL_CORRUPT"
    j.close()


def test_non_object_line(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    p.write_text("[1, 2]\n")
    assert Journal.open(p).failure_reason == "JOURNAL_CORRUPT"


def test_on_disk_format_is_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Formato v1 fissato byte per byte: chiavi, ordinamento, checksum, hash della chiave."""
    monkeypatch.setattr(store_mod.secrets, "token_hex", lambda n: "ab" * n)
    p = tmp_path / "j.jsonl"
    j = Journal.open(p)
    e = j.begin("logical-key")
    e = j.mark_sent(e)
    j.complete(e, UpstreamAck(operation_id="op_1", correlation_id="corr_1"))
    j.close()
    assert store_mod.key_hash("logical-key") == (
        "863945040e3e5a664a2989b425994381c21fbbf1671fc941ac340cf772fe8799"
    )
    golden = Path(__file__).with_name("journal_v1_golden.jsonl").read_text()
    assert p.read_text() == golden


def test_crc_known_value() -> None:
    assert store_mod._crc({"b": 1, "a": "x"}) == (
        "cdab067e9f3beb32d1252cfd63e492592fecbf591b0d08cadb24bb17f3864246"
    )


def test_large_journal_reloads_across_read_chunks(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    j = Journal.open(p)
    for i in range(400):
        e = j.mark_sent(j.begin(f"k{i}"))
        j.complete(e, UpstreamAck(operation_id=f"op{i}", correlation_id=f"c{i}"))
    j.close()
    assert p.stat().st_size > 1 << 16
    j2 = Journal.open(p)
    assert j2.writable and len(j2.entries()) == 400
    j2.close()


def _reason(j: Journal) -> str:
    with pytest.raises(JournalUnavailable) as exc:
        j.begin("x")
    assert str(exc.value) == exc.value.reason
    err = exc.value.to_tool_error()
    assert isinstance(err, ToolError)
    assert err.code is ErrorCode.JOURNAL_UNAVAILABLE and err.reasons == (exc.value.reason,)
    return exc.value.reason


def test_reason_closed(tmp_path: Path) -> None:
    j = Journal.open(tmp_path / "j.jsonl")
    j.close()
    j.close()  # idempotente
    assert j.failure_reason == "JOURNAL_CLOSED" and _reason(j) == "JOURNAL_CLOSED"


def test_reason_invalid_path_close_safe(tmp_path: Path) -> None:
    j = Journal.open(Path("rel.jsonl"))
    j.close()
    assert _reason(j) == "JOURNAL_PATH_INVALID"


def test_reason_corrupt(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    p.write_text("x\n")
    assert _reason(Journal.open(p)) == "JOURNAL_CORRUPT"


def test_reason_locked_and_lock_file(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    j1 = Journal.open(p)
    assert (tmp_path / "j.jsonl.lock").exists()
    assert (tmp_path / "j.jsonl.lock").stat().st_mode & 0o777 == 0o600
    assert p.stat().st_mode & 0o777 == 0o600
    j2 = Journal.open(p)
    assert _reason(j2) == "JOURNAL_LOCKED"
    j1.close()


def test_reason_lock_file_unopenable(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    (tmp_path / "j.jsonl.lock").mkdir()
    assert _reason(Journal.open(p)) == "JOURNAL_IO"


def test_reason_symlink(tmp_path: Path) -> None:
    (tmp_path / "real").write_text("")
    (tmp_path / "j.jsonl").symlink_to(tmp_path / "real")
    assert _reason(Journal.open(tmp_path / "j.jsonl")) == "JOURNAL_IO"


def test_reason_not_regular(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "j.jsonl")
    assert _reason(Journal.open(tmp_path / "j.jsonl")) == "JOURNAL_IO"


def test_reason_fstat_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(fd: int) -> os.stat_result:
        raise OSError(errno.EIO, "x")

    monkeypatch.setattr(store_mod.os, "fstat", boom)
    j = Journal.open(tmp_path / "j.jsonl")
    monkeypatch.undo()
    assert _reason(j) == "JOURNAL_IO"


def test_reason_header_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def full(fd: int, data: bytes) -> int:
        raise OSError(errno.ENOSPC, "x")

    monkeypatch.setattr(store_mod.os, "write", full)
    j = Journal.open(tmp_path / "j.jsonl")
    monkeypatch.undo()
    assert _reason(j) == "JOURNAL_IO"


def test_reason_replaced(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    j = Journal.open(p)
    os.replace(p, tmp_path / "moved")
    p.write_text("")
    assert _reason(j) == "JOURNAL_REPLACED"
    assert j.failure_reason == "JOURNAL_REPLACED"


def test_replaced_by_symlink_to_same_file(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    j = Journal.open(p)
    os.replace(p, tmp_path / "moved")
    p.symlink_to(tmp_path / "moved")
    assert _reason(j) == "JOURNAL_REPLACED"


def test_journal_fd_is_append_only(tmp_path: Path) -> None:
    j = Journal.open(tmp_path / "j.jsonl")
    assert j._fd is not None
    assert fcntl.fcntl(j._fd, fcntl.F_GETFL) & os.O_APPEND
    j.close()


def test_short_writes_completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.write
    monkeypatch.setattr(store_mod.os, "write", lambda fd, b: real(fd, bytes(b[:1])))
    p = tmp_path / "j.jsonl"
    j = Journal.open(p)
    e = j.mark_sent(j.begin("k"))
    j.complete(e, UpstreamAck(operation_id="o", correlation_id="c"))
    j.close()
    monkeypatch.undo()
    j2 = Journal.open(p)
    assert j2.writable and j2.entries()[0].status is EntryStatus.ACCEPTED
    j2.close()


def test_zero_byte_write_is_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    j = Journal.open(tmp_path / "j.jsonl")
    monkeypatch.setattr(store_mod.os, "write", lambda fd, b: 0)
    assert _reason(j) == "JOURNAL_IO"


def test_state_machine_misuse_raises(tmp_path: Path) -> None:
    j = Journal.open(tmp_path / "j.jsonl")
    e = j.begin("k")
    assert e == Entry(e.request_id, store_mod.key_hash("k"), EntryStatus.IN_FLIGHT, False)
    with pytest.raises(ValueError):
        j.begin("k")
    with pytest.raises(ValueError):
        j.complete(e, None)
    e = j.mark_sent(e)
    with pytest.raises(ValueError):
        j.mark_sent(e)
    done = j.complete(e, None)
    with pytest.raises(ValueError):
        j.complete(done, None)
    with pytest.raises(ValueError):
        j.mark_sent(done)
    j.close()


def test_recover_handles_every_open_entry(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    _write(p, VALID["two"] + [_begin("req_" + "3" * 32, "c" * 64)])
    j = Journal.open(p)
    pending = j.recover()
    assert [e.request_id for e in pending] == [RID2]
    statuses = {e.request_id: e.status for e in j.entries()}
    assert statuses["req_" + "3" * 32] is EntryStatus.NOT_SENT
    j.close()
    j2 = Journal.open(p)
    assert j2.writable and all(e.status is not EntryStatus.IN_FLIGHT for e in j2.entries())
    j2.close()


async def test_recover_on_unwritable_journal_in_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    j = Journal.open(tmp_path / "j.jsonl")
    j.mark_sent(j.begin("k"))
    monkeypatch.setattr(
        store_mod.os, "write", lambda fd, b: (_ for _ in ()).throw(OSError(errno.ENOSPC, "x"))
    )
    with pytest.raises(JournalUnavailable):
        j.begin("other")
    (amb,) = j.recover()
    assert amb.status is EntryStatus.AMBIGUOUS and j.entries() == (amb,)
    j.close()


async def test_waiter_on_failed_in_flight_gets_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    j = Journal.open(tmp_path / "j.jsonl")
    gate = anyio.Event()
    results: list[object] = []

    async def up(request_id: str) -> UpstreamAck:
        await gate.wait()
        monkeypatch.setattr(
            store_mod.os, "write", lambda fd, b: (_ for _ in ()).throw(OSError(errno.EIO, "x"))
        )
        return UpstreamAck(operation_id="o", correlation_id="c")

    async def first() -> None:
        try:
            await j.execute("k", up, timeout_s=5)
        except JournalUnavailable as exc:
            results.append(("first", exc.reason))

    async def second() -> None:
        try:
            await j.execute("k", up, timeout_s=5)
        except JournalUnavailable as exc:
            results.append(("second", exc.reason))

    async with anyio.create_task_group() as tg:
        tg.start_soon(first)
        await anyio.sleep(0.01)
        tg.start_soon(second)
        await anyio.sleep(0.01)
        gate.set()
    assert sorted(results) == [("first", "JOURNAL_IO"), ("second", "JOURNAL_IO")]
    j.close()


async def test_read_retry_codes_and_bounds() -> None:
    async def down() -> str:
        raise UpstreamUnavailable

    with pytest.raises(ToolError) as exc:
        await read_with_retry(down, attempts=5, timeout_s=1)
    assert exc.value.code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert exc.value.reasons == ("READ_RETRY_EXHAUSTED",)
    with pytest.raises(ValueError):
        await read_with_retry(down, attempts=6, timeout_s=1)
