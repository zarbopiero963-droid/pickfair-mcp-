"""MCP-01g: list_orders attraverso il server MCP reale (simulato e Control API reale via HTTP).

Prova anche che la lettura non produce effetti: nessun tool di comando è esposto e la Control API
risponde 405 a ogni metodo diverso da GET su /v1/orders.
"""

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
from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter, StatusScenario
from pickfair_mcp.auth import Principal, Scope
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
async def session_for(
    adapter: ControlApiAdapter, *, principal: Principal | None = LOCAL
) -> AsyncIterator[ClientSession]:
    server = build_server(
        adapter, timeout_s=0.5, principal=principal, request_id_factory=counter_ids()
    )
    with anyio.fail_after(20):
        async with create_connected_server_and_client_session(server) as session:
            yield session


async def call(session: ClientSession, args: dict[str, Any] | None = None) -> Any:
    result = await session.call_tool("list_orders", args or {})
    assert result.structuredContent is not None
    return bool(result.isError), result.structuredContent


async def test_orders_are_listed_with_ambiguous_kept_ambiguous() -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        is_error, payload = await call(session)
    assert is_error is False, payload
    jsonschema.validate(payload, tools["list_orders"].outputSchema)
    assert tools["list_orders"].annotations.readOnlyHint is True  # type: ignore[union-attr]
    orders = payload["data"]["orders"]["snapshot"]["orders"]
    amb = orders[1]
    assert amb["status"] == "AMBIGUOUS" and amb["bet_id"] is None
    assert amb["reconciliation"]["ambiguity_reason"] == "TIMEOUT_AFTER_SUBMIT"
    assert orders[2]["role"] == "HEDGE" and orders[2]["table_id"] is None
    assert isinstance(orders[0]["stake"], str)


async def test_stale_and_unavailable_snapshots_are_explicit() -> None:
    for scenario, state in (
        (StatusScenario.RECONCILIATION_REQUIRED, "STALE"),
        (StatusScenario.NOT_STARTED, "UNAVAILABLE"),
    ):
        async with session_for(SimulatedControlApiAdapter(status_scenario=scenario)) as session:
            _e, payload = await call(session)
        assert payload["data"]["orders"]["snapshot"]["state"] == state


@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        (StatusScenario.INCONSISTENT, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.EXTRA_FIELD, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.INJECTION_TEXT, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.STALE, "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"),
        (StatusScenario.WRONG_SOURCE, "UPSTREAM_INVALID_RESPONSE:SOURCE_MISMATCH"),
        (StatusScenario.MALFORMED, "UPSTREAM_INVALID_RESPONSE:"),
    ],
)
async def test_invalid_orders_fail_closed(scenario: StatusScenario, reason: str) -> None:
    async with session_for(SimulatedControlApiAdapter(status_scenario=scenario)) as session:
        is_error, payload = await call(session)
    assert is_error is True and payload["data"] is None
    assert payload["error"]["details"]["reasons"][0].startswith(reason)
    assert "IGNORE" not in json.dumps(payload)


async def test_unauthorized_or_with_arguments_never_reaches_upstream() -> None:
    for principal in (None, Principal(principal_id="w", scopes=frozenset({Scope.WRITE}))):
        adapter = SimulatedControlApiAdapter()
        async with session_for(adapter, principal=principal) as session:
            is_error, payload = await call(session)
        assert is_error and payload["error"]["code"] == "FORBIDDEN"
        assert adapter.orders_calls == 0
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        for args in ({"status": "AMBIGUOUS"}, {"cancel": True}, {"bet_id": "1"}):
            is_error, payload = await call(session, args)
            assert is_error and payload["error"]["code"] == "INVALID_REQUEST"
    assert adapter.orders_calls == 0


async def test_no_order_command_tool_is_exposed() -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        names = {t.name for t in (await session.list_tools()).tools}
        for name in ("place_order", "cancel_order", "replace_order", "cashout", "place_dutching"):
            result = await session.call_tool(name, {})
            assert result.isError and result.structuredContent["error"]["code"] == "UNKNOWN_TOOL"  # type: ignore[index]
    assert not names & {"place_order", "cancel_order", "replace_order", "cashout"}


def http_adapter(port: int, token_path: Path) -> HttpControlApiAdapter:
    return HttpControlApiAdapter(port=port, token_file=LocalTokenFile(token_path), timeout_s=2.0)


@pytest.mark.loopback
async def test_orders_through_the_real_control_api(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, _p):
        async with session_for(http_adapter(server.port, token_path)) as session:
            is_error, payload = await call(session)
    assert is_error is False, payload
    assert payload["data"]["orders"]["snapshot"]["orders"][0]["size_remaining"] == "6"
    assert server.request_counts() == {"OK": 2}


@pytest.mark.loopback
@pytest.mark.parametrize(
    "order",
    [
        bodies.order(core_status="AMBIGUOUS", status="FAILED"),  # AMBIGUOUS spacciato per fallito
        bodies.order(size_matched=None, unavailable=["size_matched"]),  # split senza quantità
        bodies.order(stake=10.0),  # float finanziario: lo ferma lo schema del server
    ],
)
async def test_misrepresented_orders_never_reach_the_agent(tmp_path: Path, order: Any) -> None:
    body = bodies.orders(snapshot={**bodies.orders()["snapshot"], "orders": [order]})
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.orders = lambda: body
        async with session_for(http_adapter(server.port, token_path)) as session:
            is_error, payload = await call(session)
    assert is_error is True and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"


@pytest.mark.loopback
async def test_post_to_orders_is_refused_by_the_control_api(tmp_path: Path) -> None:
    from tests.control_api.test_server import request

    with control_api(tmp_path) as (server, _s, token_path, providers):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _h, body = request(
                server.port, method, "/v1/orders", token=token_path.read_text(), body=b"{}"
            )
            assert (status, body) == (405, {"error": {"code": "METHOD_NOT_ALLOWED"}})
        assert providers.calls == 0
