"""MCP-01i: chiusure SL/TP in get_exposure attraverso il server MCP reale (simulato e Control API reale)."""

from __future__ import annotations

import itertools
import json
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


async def call(session: ClientSession) -> tuple[bool, Any]:
    result = await session.call_tool("get_exposure", {})
    assert result.structuredContent is not None
    return bool(result.isError), result.structuredContent


async def test_simulated_close_is_schema_valid() -> None:
    async with session_for(SimulatedControlApiAdapter()) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        is_error, payload = await call(s)
    assert is_error is False, payload
    jsonschema.validate(payload, tools["get_exposure"].outputSchema)
    close = payload["data"]["exposure"]["sl_tp_closes"]["closes"][0]
    assert (close["close_state"], close["hedges"]["placed"]) == ("ROUTED", 1)


@pytest.mark.loopback
async def test_real_control_api_round_trip(tmp_path: Path) -> None:
    section = bodies.sl_tp_closes(
        bodies.sl_tp_close(),
        bodies.sl_tp_close(
            table_id=2,
            close_state="UNCERTAIN",
            detail="ROUTE_ERROR",
            residual_exposure=None,
            residual_source="UNAVAILABLE",
        ),
    )
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.exposure = lambda: bodies.exposure(sl_tp_closes=section)
        adapter = HttpControlApiAdapter(
            port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
        )
        async with session_for(adapter) as s:
            is_error, payload = await call(s)
    assert is_error is False, payload
    closes = payload["data"]["exposure"]["sl_tp_closes"]["closes"]
    assert [c["close_state"] for c in closes] == ["ROUTED", "UNCERTAIN"]
    assert closes[1]["retryable"] is False


@pytest.mark.loopback
@pytest.mark.parametrize(
    "close",
    [
        bodies.sl_tp_close(customer_ref="cref-secret"),  # schema del server
        bodies.sl_tp_close(close_state="UNCERTAIN", retryable=True),  # regola del MCP
        bodies.sl_tp_close(residual_exposure="40", residual_source="TABLE_RELEASED"),
    ],
)
async def test_misrepresented_closes_never_reach_the_agent(
    tmp_path: Path, close: dict[str, Any]
) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.exposure = lambda: bodies.exposure(sl_tp_closes=bodies.sl_tp_closes(close))
        adapter = HttpControlApiAdapter(
            port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
        )
        async with session_for(adapter) as s:
            is_error, payload = await call(s)
    assert is_error is True and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    assert "cref-secret" not in json.dumps(payload)
