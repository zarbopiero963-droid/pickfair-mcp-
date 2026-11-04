"""MCP-01h: SL/TP per tavolo (get_exposure), settlement (get_reconciliation_status), barriere di
cashout (get_status) attraverso il server MCP reale: adapter simulato e Control API reale."""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import jsonschema
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.adapters.http import HttpControlApiAdapter
from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter
from pickfair_mcp.auth.token_file import LocalTokenFile
from pickfair_mcp.cli import LOCAL_STDIO_PRINCIPAL as LOCAL
from pickfair_mcp.server import build_server
from tests.control_api import bodies
from tests.control_api.servers import control_api

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def counter_ids() -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"req_{next(counter):032x}"


@asynccontextmanager
async def session_for(adapter: ControlApiAdapter) -> AsyncIterator[ClientSession]:
    server = build_server(adapter, timeout_s=0.5, principal=LOCAL, request_id_factory=counter_ids())
    with anyio.fail_after(20):
        async with create_connected_server_and_client_session(server) as session:
            yield session


async def call(session: ClientSession, name: str) -> Any:
    result = await session.call_tool(name, {})
    assert result.structuredContent is not None
    return bool(result.isError), result.structuredContent


async def test_simulated_sl_tp_settlement_and_barriers() -> None:
    async with session_for(SimulatedControlApiAdapter()) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        exp = await call(s, "get_exposure")
        rec = await call(s, "get_reconciliation_status")
        st = await call(s, "get_status")
    for name, (is_error, payload) in (
        ("get_exposure", exp),
        ("get_reconciliation_status", rec),
        ("get_status", st),
    ):
        assert is_error is False, payload
        jsonschema.validate(payload, tools[name].outputSchema)
    t1 = exp[1]["data"]["exposure"]["tables"][0]["sl_tp"]
    assert t1["state"] == "ARMED" and t1["stop_loss"] == "10" and t1["trailing_stop_pct"] is None
    assert rec[1]["data"]["reconciliation"]["settlement"]["sim_settlements"] == 2
    assert st[1]["data"]["status"]["engine"]["queues"]["cashout_barriers"] == 0


@pytest.mark.loopback
@pytest.mark.parametrize(
    ("provider", "body"),
    [
        # tavolo «non armato» con importi: lo ferma il MCP (regola fra campi)
        (
            "exposure",
            bodies.exposure(
                tables=[bodies.table(1, sl_tp={**bodies.not_armed(), "stop_loss": "2"})]
            ),
        ),
        # importo SL in float: lo ferma lo schema del server
        (
            "exposure",
            bodies.exposure(
                tables=[
                    bodies.table(
                        1, sl_tp={**bodies.not_armed(), "state": "ARMED", "stop_loss": 2.0}
                    )
                ]
            ),
        ),
        # payload di settlement esposto: schema chiuso
        (
            "reconciliation",
            bodies.reconciliation(settlement={**bodies.settlement(), "payload": {}}),
        ),
        # held che non coincide con il dettaglio per esito
        (
            "reconciliation",
            bodies.reconciliation(
                settlement={
                    **bodies.settlement(),
                    "effects": {"held": 3, "not_realized": 0, "by_outcome": []},
                }
            ),
        ),
    ],
)
async def test_misrepresented_data_never_reaches_the_agent(
    tmp_path: Path, provider: str, body: dict[str, Any]
) -> None:
    tool = "get_exposure" if provider == "exposure" else "get_reconciliation_status"
    with control_api(tmp_path) as (server, _s, token_path, providers):
        setattr(providers, provider, lambda: body)
        adapter = HttpControlApiAdapter(
            port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
        )
        async with session_for(adapter) as s:
            is_error, payload = await call(s, tool)
    assert is_error is True and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
