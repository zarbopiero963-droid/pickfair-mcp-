"""MCP-01l: list_markets e get_market_book attraverso il server MCP reale (simulato e Control API reale)."""

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
from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter, StatusScenario
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


async def call(
    session: ClientSession, name: str, args: dict[str, Any] | None = None
) -> tuple[bool, Any]:
    result = await session.call_tool(name, args or {})
    assert result.structuredContent is not None
    return bool(result.isError), result.structuredContent


async def test_simulated_markets_and_book() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        ml = await call(s, "list_markets")
        ok = await call(s, "get_market_book", {"market_id": "1.200000001"})
        nt = await call(s, "get_market_book", {"market_id": "1.999"})
    for name, (is_error, payload) in (
        ("list_markets", ml),
        ("get_market_book", ok),
        ("get_market_book", nt),
    ):
        assert is_error is False, payload
        jsonschema.validate(payload, tools[name].outputSchema)
        assert tools[name].annotations.readOnlyHint is True  # type: ignore[union-attr]
    assert (
        ok[1]["data"]["book"]["state"] == "OK" and nt[1]["data"]["book"]["state"] == "NOT_TRACKED"
    )
    schema = tools["get_market_book"].inputSchema
    assert schema["required"] == ["market_id"] and schema.get("additionalProperties") is False


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"market_id": "../etc"},
        {"market_id": "1.2", "x": 1},
        {"market_id": 1.2},
        {"market_id": "1.2/../book"},
    ],
)
async def test_bad_input_never_reaches_the_adapter(args: dict[str, Any]) -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as s:
        is_error, payload = await call(s, "get_market_book", args)
    assert is_error is True and payload["error"]["code"] == "INVALID_REQUEST"
    assert adapter.market_book_calls == 0 and adapter.meta_calls == 0


@pytest.mark.parametrize(
    "scenario",
    [
        StatusScenario.EXTRA_FIELD,
        StatusScenario.INJECTION_TEXT,
        StatusScenario.INCONSISTENT,
        StatusScenario.WRONG_SOURCE,
    ],
)
async def test_simulated_bad_market_bodies_are_rejected(scenario: StatusScenario) -> None:
    async with session_for(SimulatedControlApiAdapter(status_scenario=scenario)) as s:
        is_error, payload = await call(s, "list_markets")
    assert is_error is True and payload["data"] is None


@pytest.mark.loopback
async def test_real_control_api_book_round_trip_and_id_echo(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        adapter = HttpControlApiAdapter(
            port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
        )
        async with session_for(adapter) as s:
            ok = await call(s, "get_market_book", {"market_id": "1.42"})
            providers.market_book = lambda _mid: bodies.market_book(
                "1.43"
            )  # risposta per un altro mercato
            wrong = await call(s, "get_market_book", {"market_id": "1.42"})
        assert providers.book_requests == ["1.42", "1.42"]
    assert ok[0] is False and ok[1]["data"]["book"]["market_id"] == "1.42"
    assert wrong[0] is True and wrong[1]["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"


@pytest.mark.parametrize("bad", ["../etc", "1.2/../x", "1.2a", "", "1.1234567890123456", "1.2\n"])
async def test_http_adapter_never_builds_a_path_from_an_unvalidated_id(
    tmp_path: Path, bad: str
) -> None:
    """Seconda barriera (MCP-01l): anche chiamato direttamente, l'adapter non costruisce il percorso."""
    token = tmp_path / "t"
    adapter = HttpControlApiAdapter(port=1, token_file=LocalTokenFile(token), timeout_s=0.1)
    with pytest.raises(ValueError):
        await adapter.get_market_book_raw(bad)
