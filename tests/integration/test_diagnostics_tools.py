"""MCP-01f: diagnostica e protezioni in get_status, posizioni in list_positions.

Livelli tenuti distinti: adapter SIMULATO (dati fittizi) e Control API REALE su 127.0.0.1 con
provider di prova. L'integrazione col core reale è in tests/crossrepo.
"""

from __future__ import annotations

import itertools
import json
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import anyio
import jsonschema
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.adapters.http import HttpControlApiAdapter
from pickfair_mcp.adapters.simulated import Scenario, SimulatedControlApiAdapter, StatusScenario
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


async def call(session: ClientSession, name: str, args: dict[str, Any] | None = None) -> Any:
    result = await session.call_tool(name, args or {})
    assert result.structuredContent is not None
    return bool(result.isError), result.structuredContent


# ------------------------------------------------------------------ adapter simulato


async def test_status_carries_engine_and_every_protection() -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        is_error, payload = await call(session, "get_status")
    assert is_error is False, payload
    jsonschema.validate(payload, tools["get_status"].outputSchema)
    status = payload["data"]["status"]
    assert len(status["protections"]["items"]) == 23
    assert status["engine"]["modes"]["read_only_mode"] == "NOT_IN_CORE"
    assert status["protections"]["unverifiable"] == ["funds_freshness", "market_tradability"]
    assert "never treat them as safe" in (tools["get_status"].description or "")


async def test_unverifiable_protection_is_reported_as_unverifiable() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.NOT_STARTED)
    async with session_for(adapter) as session:
        _e, payload = await call(session, "get_status")
    prot = payload["data"]["status"]["protections"]
    assert prot["items"]["risk_stop"] == {
        "state": "UNKNOWN",
        "reason": "LOCK_BUSY",
        "source": "RUNTIME",
        "limit": None,
        "as_of": None,
    }
    assert "risk_stop" in prot["unverifiable"]


async def test_triggered_protections_are_reported_with_reason_and_time() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.STOP_ACTIVE)
    async with session_for(adapter) as session:
        _e, payload = await call(session, "get_status")
    items = payload["data"]["status"]["protections"]["items"]
    assert items["emergency_stop"]["state"] == "TRIGGERED"
    assert items["daily_loss"]["reason"] == "DAILY_LOSS_BREACHED"
    assert items["daily_loss"]["limit"] == "50" and items["daily_loss"]["as_of"] is not None


async def test_positions_keep_decimal_strings_end_to_end() -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        result = await session.call_tool("list_positions", {})
    payload = result.structuredContent
    assert payload is not None and result.isError is False
    jsonschema.validate(payload, tools["list_positions"].outputSchema)
    lay = payload["data"]["positions"]["positions"][1]
    assert lay["side"] == "LAY" and lay["avg_entry_price"] == "3.1"
    assert isinstance(lay["exposure"], str) and Decimal(lay["exposure"]) == Decimal("8.4")
    # anche il testo restituito al client non contiene float per gli importi
    text = result.content[0].text  # type: ignore[union-attr]
    assert '"exposure": "8.4"' in text or '"exposure":"8.4"' in text


@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        (StatusScenario.EXTRA_FIELD, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.INJECTION_TEXT, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.INCONSISTENT, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.STALE, "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"),
        (StatusScenario.FUTURE, "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"),
        (StatusScenario.WRONG_SOURCE, "UPSTREAM_INVALID_RESPONSE:SOURCE_MISMATCH"),
    ],
)
async def test_invalid_positions_fail_closed(scenario: StatusScenario, reason: str) -> None:
    async with session_for(SimulatedControlApiAdapter(status_scenario=scenario)) as session:
        is_error, payload = await call(session, "list_positions")
    assert is_error is True and payload["data"] is None
    assert payload["error"]["details"]["reasons"] == [reason]
    assert "IGNORE" not in json.dumps(payload)


async def test_positions_unauthorized_or_with_arguments_never_reach_upstream() -> None:
    for principal in (None, Principal(principal_id="w", scopes=frozenset({Scope.WRITE}))):
        adapter = SimulatedControlApiAdapter()
        async with session_for(adapter, principal=principal) as session:
            is_error, payload = await call(session, "list_positions")
        assert is_error and payload["error"]["code"] == "FORBIDDEN"
        assert adapter.positions_calls == 0 and adapter.meta_calls == 0
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        is_error, payload = await call(session, "list_positions", {"market_id": "1.2"})
    assert is_error and payload["error"]["code"] == "INVALID_REQUEST"
    assert adapter.positions_calls == 0


async def test_core_without_positions_capability_is_never_read() -> None:
    adapter = SimulatedControlApiAdapter(Scenario.META_ONLY)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, "list_positions")
    assert is_error and payload["error"]["code"] == "CONTRACT_INCOMPATIBLE"
    assert adapter.positions_calls == 0


# ------------------------------------------------------------------ Control API reale (HTTP)


def http_adapter(port: int, token_path: Path) -> HttpControlApiAdapter:
    return HttpControlApiAdapter(port=port, token_file=LocalTokenFile(token_path), timeout_s=2.0)


@pytest.mark.loopback
async def test_status_and_positions_through_the_real_control_api(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, _p):
        async with session_for(http_adapter(server.port, token_path)) as session:
            status = await call(session, "get_status")
            positions = await call(session, "list_positions")
    assert status[0] is False and positions[0] is False
    assert status[1]["data"]["status"]["protections"]["items"]["kill_switch"]["state"] == "ACTIVE"
    assert positions[1]["data"]["positions"]["positions"][0]["open_size"] == "10.00"
    assert server.request_counts() == {"OK": 3}


@pytest.mark.loopback
@pytest.mark.parametrize(
    "mutate",
    [
        # il core dichiara «tutto a posto» ma tace una protezione non verificabile
        lambda b: b["protections"].update(unverifiable=[]),
        # protezione non verificabile spacciata per attiva senza dati: schema la blocca
        lambda b: b["protections"]["items"].update(
            risk_stop={
                "state": "ACTIVE",
                "reason": "LOCK_BUSY",
                "source": "RUNTIME",
                "limit": None,
                "as_of": None,
            }
        ),
        # stato inventato
        lambda b: b["protections"]["items"]["kill_switch"].update(state="SAFE"),
    ],
)
async def test_unverifiable_never_reaches_the_agent_as_safe(tmp_path: Path, mutate: Any) -> None:
    body = bodies.status()
    mutate(body)
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.status = lambda: body
        async with session_for(http_adapter(server.port, token_path)) as session:
            is_error, payload = await call(session, "get_status")
    assert is_error is True and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"


@pytest.mark.loopback
async def test_stale_positions_from_core_are_rejected(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.positions = lambda: bodies.positions(observed_at=time.time() - 3600)
        async with session_for(http_adapter(server.port, token_path)) as session:
            is_error, payload = await call(session, "list_positions")
    assert is_error and payload["error"]["details"]["reasons"] == [
        "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"
    ]


@pytest.mark.loopback
async def test_float_amount_from_core_is_stopped_by_the_server(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.positions = lambda: bodies.positions(positions=[bodies.position(exposure=10.0)])
        async with session_for(http_adapter(server.port, token_path)) as session:
            is_error, payload = await call(session, "list_positions")
    assert is_error and payload["error"]["details"]["reasons"] == [
        "UPSTREAM_INVALID_RESPONSE:HTTP_500"
    ]
    assert server.request_counts().get("CONTRACT_SELF_CHECK") == 1
