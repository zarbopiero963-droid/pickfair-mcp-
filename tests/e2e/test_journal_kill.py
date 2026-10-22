"""MCP-01b runtime L3: processi reali uccisi con SIGKILL e due processi concorrenti.

Upstream simulato deterministico (file contatore): non è un'integrazione Pickfair.
"""

from __future__ import annotations

import json
import os
import random
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from pickfair_mcp.journal import EntryStatus, Journal
from tests.conftest import REPO_ROOT

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.name != "posix", reason="SIGKILL POSIX")]

WORKER = r"""
import os, sys, anyio
from pathlib import Path
from pickfair_mcp.journal import Journal, UpstreamAck
jp, sends, start = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
j = Journal.open(jp)
if not j.writable:
    print("LOCKED", flush=True); sys.exit(3)
j.recover()
print("READY", flush=True)
async def up(request_id):
    with open(sends, "a") as f:
        f.write(request_id + "\n"); f.flush(); os.fsync(f.fileno())
    return UpstreamAck(operation_id="op_" + request_id[4:12], correlation_id="c_" + request_id[4:12])
async def main():
    i = start
    while True:
        await j.execute(f"key{i % 40}", up, timeout_s=5)
        i += 1
anyio.run(main)
"""


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}


def _spawn(jp: Path, sends: Path, start: int) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        [sys.executable, "-c", WORKER, str(jp), str(sends), str(start)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=_env(),
    )
    assert proc.stdout is not None
    return proc


def test_random_sigkill_200_no_loss_no_duplicate(tmp_path: Path) -> None:
    jp, sends = tmp_path / "j.jsonl", tmp_path / "sends.txt"
    sends.touch()
    rng = random.Random(1337)
    kills = int(os.environ.get("PF_MCP_KILLS", "200"))
    for n in range(kills):
        proc = _spawn(jp, sends, rng.randrange(1000))
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        assert line == "READY", line
        time.sleep(rng.uniform(0, 0.004))
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=10)
        proc.stdout.close()
    j = Journal.open(jp)
    assert j.writable, j.failure_reason
    j.recover()
    sent_ids = sends.read_text().split()
    entries = j.entries()
    by_key: dict[str, int] = {}
    for e in entries:
        by_key[e.key_hash] = by_key.get(e.key_hash, 0) + 1
    assert all(v == 1 for v in by_key.values()), "chiave logica duplicata"
    # ogni invio upstream ha una voce; nessun invio duplicato (nessun replay)
    assert len(sent_ids) == len(set(sent_ids))
    known = {e.request_id: e for e in entries}
    for rid in sent_ids:
        assert rid in known, "invio senza voce persistita"
        assert known[rid].status in {EntryStatus.ACCEPTED, EntryStatus.AMBIGUOUS}
    for e in entries:
        if e.status is EntryStatus.ACCEPTED:
            assert e.request_id in sent_ids
        assert e.status is not EntryStatus.IN_FLIGHT
    j.close()


def test_two_processes_only_one_writes(tmp_path: Path) -> None:
    jp, sends = tmp_path / "j.jsonl", tmp_path / "sends.txt"
    sends.touch()
    a = _spawn(jp, sends, 0)
    assert a.stdout is not None and a.stdout.readline().strip() == "READY"
    b = _spawn(jp, sends, 0)
    assert b.stdout is not None
    assert b.stdout.readline().strip() == "LOCKED"
    assert b.wait(timeout=10) == 3
    a.send_signal(signal.SIGKILL)
    a.wait(timeout=10)
    for p in (a, b):
        assert p.stdout is not None
        p.stdout.close()
    lines = [json.loads(x) for x in jp.read_text().splitlines() if x]
    assert sum(r["kind"] == "header" for r in lines) == 1
