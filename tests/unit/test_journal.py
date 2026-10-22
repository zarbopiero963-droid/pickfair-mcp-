"""MCP-01b: identità delle richieste e journal append-only (unit, adversarial, idempotenza)."""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import anyio
import pytest

from pickfair_mcp.adapters.base import UpstreamTimeout, UpstreamUnavailable
from pickfair_mcp.errors import ErrorCode, ToolError
from pickfair_mcp.journal import (
    EntryStatus,
    Journal,
    JournalUnavailable,
    UpstreamAck,
    read_with_retry,
)
from pickfair_mcp.journal import store as store_mod

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeUpstream:
    """Upstream simulato deterministico: conta le chiamate, nessuna rete."""

    def __init__(self, mode: str = "ok") -> None:
        self.calls = 0
        self.mode = mode
        self.seen: list[str] = []

    async def __call__(self, request_id: str) -> UpstreamAck:
        self.calls += 1
        self.seen.append(request_id)
        if self.mode == "timeout":
            await anyio.sleep_forever()
        if self.mode == "unavailable":
            raise UpstreamUnavailable
        if self.mode == "boom":
            raise RuntimeError("upstream text must never leak")
        if self.mode == "bad_ack":
            return UpstreamAck(operation_id="bad id!", correlation_id="c")
        await anyio.sleep(0)
        return UpstreamAck(operation_id=f"op_{self.calls}", correlation_id=f"corr_{self.calls}")


def jpath(tmp_path: Path) -> Path:
    return tmp_path / "journal.jsonl"


def lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(x) for x in path.read_text().splitlines()]


async def test_new_entry_has_request_operation_correlation(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    up = FakeUpstream()
    entry = await j.execute("k1", up, timeout_s=1)
    assert entry.status is EntryStatus.ACCEPTED
    assert entry.request_id.startswith("req_") and len(entry.request_id) == 36
    assert (entry.operation_id, entry.correlation_id) == ("op_1", "corr_1")
    assert up.seen == [entry.request_id]
    assert j.lookup(entry.request_id) == entry
    kinds = [r["kind"] for r in lines(jpath(tmp_path))]
    assert kinds == ["header", "begin", "sent", "outcome"]
    j.close()


async def test_duplicate_returns_same_operation_without_upstream_call(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    up = FakeUpstream()
    first = await j.execute("same", up, timeout_s=1)
    for _ in range(25):
        again = await j.execute("same", up, timeout_s=1)
        assert again.operation_id == first.operation_id
        assert again.request_id == first.request_id
        assert again.deduplicated
    assert up.calls == 1
    j.close()


async def test_duplicate_survives_restart(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    up = FakeUpstream()
    first = await j.execute("same", up, timeout_s=1)
    j.close()
    j2 = Journal.open(jpath(tmp_path))
    j2.recover()
    again = await j2.execute("same", up, timeout_s=1)
    assert up.calls == 1 and again.operation_id == first.operation_id
    j2.close()


async def test_parallel_same_key_one_upstream_call(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    up = FakeUpstream()
    results = []

    async def call() -> None:
        results.append(await j.execute("par", up, timeout_s=1))

    async with anyio.create_task_group() as tg:
        for _ in range(50):
            tg.start_soon(call)
    assert up.calls == 1
    assert len({r.request_id for r in results}) == 1
    j.close()


async def test_different_keys_distinct_request_ids(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    up = FakeUpstream()
    a = await j.execute("a", up, timeout_s=1)
    b = await j.execute("b", up, timeout_s=1)
    assert a.request_id != b.request_id and up.calls == 2
    j.close()


@pytest.mark.parametrize("mode", ["timeout", "unavailable", "boom", "bad_ack"])
async def test_failure_after_send_is_ambiguous_and_never_retried(tmp_path: Path, mode: str) -> None:
    j = Journal.open(jpath(tmp_path))
    up = FakeUpstream(mode)
    entry = await j.execute("m", up, timeout_s=0.05)
    assert entry.status is EntryStatus.AMBIGUOUS
    assert entry.operation_id is None
    again = await j.execute("m", up, timeout_s=0.05)
    assert again.status is EntryStatus.AMBIGUOUS and up.calls == 1
    assert "upstream text" not in jpath(tmp_path).read_text()
    j.close()


async def test_crash_before_send_closed_as_not_sent(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    j.begin("k")  # crash simulato: nessun "sent"
    j.abandon_for_test()
    j2 = Journal.open(jpath(tmp_path))
    pending = j2.recover()
    assert pending == ()
    (entry,) = j2.entries()
    assert entry.status is EntryStatus.NOT_SENT
    up = FakeUpstream()
    again = await j2.execute("k", up, timeout_s=1)
    assert up.calls == 0 and again.status is EntryStatus.NOT_SENT  # nessun replay
    j2.close()


async def test_crash_after_send_is_ambiguous_no_replay(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    entry = j.begin("k")
    j.mark_sent(entry)
    j.abandon_for_test()
    j2 = Journal.open(jpath(tmp_path))
    pending = j2.recover()
    assert [p.status for p in pending] == [EntryStatus.AMBIGUOUS]
    up = FakeUpstream()
    again = await j2.execute("k", up, timeout_s=1)
    assert up.calls == 0 and again.status is EntryStatus.AMBIGUOUS
    j2.close()
    # la chiusura AMBIGUOUS è persistita: un secondo recover non trova nulla di nuovo
    j3 = Journal.open(jpath(tmp_path))
    assert [p.status for p in j3.recover()] == [EntryStatus.AMBIGUOUS]
    assert sum(r["kind"] == "outcome" for r in lines(jpath(tmp_path))) == 1
    j3.close()


def _prepare(tmp_path: Path) -> Path:
    p = jpath(tmp_path)
    j = Journal.open(p)
    e = j.begin("k")
    j.mark_sent(e)
    j.complete(e, UpstreamAck(operation_id="op", correlation_id="c"))
    j.close()
    return p


@pytest.mark.parametrize(
    "damage",
    ["truncate", "checksum", "garbage", "missing_header", "seq_gap", "bad_version", "empty_line"],
)
async def test_corrupt_journal_fails_closed_reads_allowed(tmp_path: Path, damage: str) -> None:
    p = _prepare(tmp_path)
    raw = p.read_text()
    rows = raw.splitlines()
    if damage == "truncate":
        p.write_text(raw[:-7])
    elif damage == "checksum":
        rec = json.loads(rows[2])
        rec["request_id"] = "req_" + "0" * 32
        rows[2] = json.dumps(rec, sort_keys=True)
        p.write_text("\n".join(rows) + "\n")
    elif damage == "garbage":
        p.write_text(raw + "not json\n")
    elif damage == "missing_header":
        p.write_text("\n".join(rows[1:]) + "\n")
    elif damage == "seq_gap":
        p.write_text("\n".join([rows[0], rows[2], rows[3]]) + "\n")
    elif damage == "bad_version":
        rec = json.loads(rows[0])
        rec["v"] = 99
        p.write_text("\n".join([json.dumps(rec), *rows[1:]]) + "\n")
    elif damage == "empty_line":
        p.write_text(raw + "\n")
    j = Journal.open(p)
    assert not j.writable
    assert j.failure_reason is not None
    up = FakeUpstream()
    with pytest.raises(JournalUnavailable) as exc:
        await j.execute("new", up, timeout_s=1)
    assert up.calls == 0
    assert exc.value.to_tool_error().code is ErrorCode.JOURNAL_UNAVAILABLE
    # letture consentite
    assert await read_with_retry(lambda: _ok_read(), attempts=1, timeout_s=1) == "ok"
    j.close()


async def _ok_read() -> str:
    return "ok"


async def test_disk_full_no_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    j = Journal.open(jpath(tmp_path))

    def full(fd: int, data: bytes) -> int:
        raise OSError(errno.ENOSPC, "no space")

    monkeypatch.setattr(store_mod.os, "write", full)
    up = FakeUpstream()
    with pytest.raises(JournalUnavailable):
        await j.execute("k", up, timeout_s=1)
    assert up.calls == 0 and not j.writable
    monkeypatch.undo()
    with pytest.raises(JournalUnavailable):
        await j.execute("k2", up, timeout_s=1)
    assert up.calls == 0
    j.close()


async def test_fsync_failure_no_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    j = Journal.open(jpath(tmp_path))

    def bad_fsync(fd: int) -> None:
        raise OSError(errno.EIO, "io")

    monkeypatch.setattr(store_mod.os, "fsync", bad_fsync)
    up = FakeUpstream()
    with pytest.raises(JournalUnavailable):
        await j.execute("k", up, timeout_s=1)
    assert up.calls == 0
    j.close()


async def test_fsync_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    j = Journal.open(jpath(tmp_path))
    synced: list[int] = []
    real = os.fsync
    monkeypatch.setattr(store_mod.os, "fsync", lambda fd: (synced.append(fd), real(fd))[1])
    before: list[int] = []

    async def up(request_id: str) -> UpstreamAck:
        before.append(len(synced))
        on_disk = lines(jpath(tmp_path))
        assert [r["kind"] for r in on_disk][-2:] == ["begin", "sent"]
        return UpstreamAck(operation_id="op", correlation_id="c")

    await j.execute("k", up, timeout_s=1)
    assert before == [2]  # begin e sent sincronizzati prima dell'invio
    assert len(synced) == 3  # e l'esito dopo
    j.close()


async def test_outcome_write_failure_leaves_ambiguous_on_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    j = Journal.open(jpath(tmp_path))
    real_write = os.write

    async def up(request_id: str) -> UpstreamAck:
        monkeypatch.setattr(
            store_mod.os, "write", lambda fd, b: (_ for _ in ()).throw(OSError(errno.ENOSPC, "x"))
        )
        return UpstreamAck(operation_id="op", correlation_id="c")

    with pytest.raises(JournalUnavailable):
        await j.execute("k", up, timeout_s=1)
    monkeypatch.setattr(store_mod.os, "write", real_write)
    j.close()
    j2 = Journal.open(jpath(tmp_path))
    assert [p.status for p in j2.recover()] == [EntryStatus.AMBIGUOUS]
    j2.close()


def test_exclusive_lock_second_opener_cannot_write(tmp_path: Path) -> None:
    j1 = Journal.open(jpath(tmp_path))
    j2 = Journal.open(jpath(tmp_path))
    assert j1.writable and not j2.writable
    assert j2.failure_reason == "JOURNAL_LOCKED"
    j1.close()
    j2.close()
    j3 = Journal.open(jpath(tmp_path))
    assert j3.writable
    j3.close()


async def test_replaced_file_detected(tmp_path: Path) -> None:
    p = jpath(tmp_path)
    j = Journal.open(p)
    up = FakeUpstream()
    await j.execute("a", up, timeout_s=1)
    os.replace(p, tmp_path / "moved.jsonl")
    p.write_text("")
    with pytest.raises(JournalUnavailable):
        await j.execute("b", up, timeout_s=1)
    assert up.calls == 1
    j.close()


@pytest.mark.parametrize("bad", ["relative.jsonl", "../x/../j.jsonl"])
def test_path_rules(tmp_path: Path, bad: str) -> None:
    target = Path(bad) if bad.startswith("relative") else Path(str(tmp_path) + "/" + bad)
    j = Journal.open(target)
    assert not j.writable and j.failure_reason == "JOURNAL_PATH_INVALID"


def test_symlink_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.jsonl"
    real.write_text("")
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)
    j = Journal.open(link)
    assert not j.writable


def test_permission_denied_fails_closed(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignora i permessi")
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        j = Journal.open(d / "j.jsonl")
        assert not j.writable
    finally:
        d.chmod(0o700)


async def test_no_secret_or_raw_key_in_journal(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    secret_key = "ghp_" + "A" * 36 + " password=hunter2"
    await j.execute(secret_key, FakeUpstream(), timeout_s=1)
    text = jpath(tmp_path).read_text()
    assert "hunter2" not in text and "ghp_" not in text
    j.close()


def test_file_mode_private(tmp_path: Path) -> None:
    j = Journal.open(jpath(tmp_path))
    assert (jpath(tmp_path).stat().st_mode & 0o077) == 0
    j.close()


async def test_read_retry_only_for_transient_errors() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise UpstreamUnavailable
        return "v"

    assert await read_with_retry(flaky, attempts=3, timeout_s=1) == "v" and calls == 3

    async def hang() -> str:
        await anyio.sleep_forever()
        return "never"

    with pytest.raises(ToolError) as exc:
        await read_with_retry(hang, attempts=2, timeout_s=0.02)
    assert exc.value.code is ErrorCode.UPSTREAM_TIMEOUT

    async def bad() -> str:
        raise ValueError

    with pytest.raises(ValueError):
        await read_with_retry(bad, attempts=5, timeout_s=1)

    async def down() -> str:
        raise UpstreamTimeout

    with pytest.raises(ToolError) as exc2:
        await read_with_retry(down, attempts=2, timeout_s=1)
    assert exc2.value.code is ErrorCode.UPSTREAM_TIMEOUT


def test_read_retry_attempts_bounded() -> None:
    with pytest.raises(ValueError):
        anyio.run(lambda: read_with_retry(_ok_read, attempts=0, timeout_s=1))


def test_checksum_detects_structurally_valid_tampering(tmp_path: Path) -> None:
    """Un esito alterato ma coerente (operation_id diverso) è rilevato solo dal checksum."""
    p = _prepare(tmp_path)
    rows = p.read_text().splitlines()
    rec = json.loads(rows[3])
    assert rec["kind"] == "outcome"
    rec["operation_id"] = "op_forged"
    rows[3] = json.dumps(rec, sort_keys=True)
    p.write_text("\n".join(rows) + "\n")
    j = Journal.open(p)
    assert not j.writable and j.failure_reason == "JOURNAL_CORRUPT"
    assert j.entries() == ()
    j.close()
