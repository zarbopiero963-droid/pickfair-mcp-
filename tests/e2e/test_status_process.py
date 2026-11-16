"""MCP-02a, prova L3: get_status / get_reconciliation_status sul processo `pickfair-mcp serve`.

Adapter simulato: la prova riguarda protocollo, trasporto e marcatura «simulated»,
non l'integrazione con il core.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
import jsonschema
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = [pytest.mark.anyio, pytest.mark.e2e]

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def params(*extra: str) -> StdioServerParameters:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONUNBUFFERED": "1",
    }
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "pickfair_mcp", "serve", "--adapter", "simulated", *extra],
        env=env,
    )


async def test_process_serves_status_marked_simulated(tmp_path: Path) -> None:
    errlog = (tmp_path / "stderr.log").open("w+")
    with anyio.fail_after(60):
        async with (
            stdio_client(params(), errlog=errlog) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
            for name, key in (
                ("get_status", "status"),
                ("get_reconciliation_status", "reconciliation"),
            ):
                result = await session.call_tool(name, {})
                assert result.isError is False
                payload = result.structuredContent
                assert payload is not None
                jsonschema.validate(payload, tools[name].outputSchema)
                assert payload["data"]["upstream"] == {"kind": "simulated", "certified": False}
                assert payload["data"][key]["source"] == "simulated"
    errlog.seek(0)
    audit = [json.loads(line) for line in errlog.read().splitlines() if line.startswith("{")]
    calls = [a for a in audit if a.get("event") == "tool_call"]
    assert {c["tool"] for c in calls} == {"get_status", "get_reconciliation_status"}
    assert all(c["ok"] is True for c in calls)


async def test_process_status_scenario_injection_fails_closed(tmp_path: Path) -> None:
    errlog = (tmp_path / "stderr.log").open("w+")
    with anyio.fail_after(60):
        async with (
            stdio_client(params("--sim-status-scenario", "injection_text"), errlog=errlog) as (
                read,
                write,
            ),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool("get_status", {})
    assert result.isError is True
    text = result.content[0].text  # type: ignore[union-attr]
    assert "IGNORE" not in text
    assert json.loads(text)["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    errlog.seek(0)
    assert "IGNORE" not in errlog.read()
