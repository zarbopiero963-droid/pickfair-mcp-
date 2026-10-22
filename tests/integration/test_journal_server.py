"""MCP-01b: server + journal + adapter simulato (in-process)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter
from pickfair_mcp.audit import LOGGER_NAME
from pickfair_mcp.journal import Journal, UpstreamAck
from pickfair_mcp.server import build_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == LOGGER_NAME]


async def _ambiguous_journal(path: Path) -> None:
    j = Journal.open(path)
    e = j.begin("k")
    j.mark_sent(e)
    j.abandon_for_test()


async def test_server_recovers_journal_and_audits_pending(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    p = tmp_path / "j.jsonl"
    await _ambiguous_journal(p)
    j = Journal.open(p)
    server = build_server(SimulatedControlApiAdapter(), timeout_s=0.1, journal=j)
    with anyio.fail_after(15):
        async with create_connected_server_and_client_session(server) as session:
            res = await session.call_tool("get_meta", {})
    assert res.isError is False
    rec = [e for e in _events(caplog) if e["event"] == "journal"]
    assert rec and rec[0]["journal_writable"] is True and rec[0]["pending_ambiguous"] == 1
    # nessun replay: nessuna nuova voce "sent"
    kinds = [json.loads(x)["kind"] for x in p.read_text().splitlines()]
    assert kinds.count("sent") == 1
    j.close()


async def test_corrupt_journal_reads_still_served(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    p = tmp_path / "j.jsonl"
    p.write_text("{broken\n")
    j = Journal.open(p)
    server = build_server(SimulatedControlApiAdapter(), timeout_s=0.1, journal=j)
    with anyio.fail_after(15):
        async with create_connected_server_and_client_session(server) as session:
            res = await session.call_tool("get_meta", {})
    assert res.isError is False  # letture consentite
    rec = [e for e in _events(caplog) if e["event"] == "journal"]
    assert rec[0]["journal_writable"] is False
    assert rec[0]["error_code"] == "JOURNAL_UNAVAILABLE"
    j.close()


async def test_identity_chain_reconstructible_from_journal_and_audit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    j = Journal.open(tmp_path / "j.jsonl")

    async def up(request_id: str) -> UpstreamAck:
        return UpstreamAck(operation_id="op_77", correlation_id="corr_77")

    entry = await j.execute("logical", up, timeout_s=1)
    j.close()
    j2 = Journal.open(tmp_path / "j.jsonl")
    j2.recover()
    again = j2.lookup(entry.request_id)
    assert again is not None and (again.operation_id, again.correlation_id) == ("op_77", "corr_77")
    audited = [e for e in _events(caplog) if e["event"] == "journal_entry"]
    assert {
        (e["request_id"], e["operation_id"], e["correlation_id"], e["outcome"]) for e in audited
    } >= {(entry.request_id, "op_77", "corr_77", "ACCEPTED")}
    j2.close()
