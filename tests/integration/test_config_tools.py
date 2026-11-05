"""MCP-01j: get_config attraverso il server MCP reale (adapter simulato e Control API reale)."""

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
    result = await session.call_tool("get_config", {})
    assert result.structuredContent is not None
    return bool(result.isError), result.structuredContent


async def test_simulated_config_is_read_only_and_schema_valid() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        is_error, payload = await call(s)
    assert is_error is False, payload
    tool = tools["get_config"]
    jsonschema.validate(payload, tool.outputSchema)
    assert tool.annotations is not None and tool.annotations.readOnlyHint is True
    assert tool.inputSchema.get("properties", {}) == {}  # nessun parametro: nulla da modificare
    settings = {s["key"]: s for s in payload["data"]["config"]["settings"]}
    assert settings["max_session_loss"] == {"key": "max_session_loss", "kind": "DECIMAL",
                                            "state": "NOT_SET", "value": None}
    assert settings["risk_profile"]["value"] == "BALANCED"
    assert adapter.config_calls == 1


@pytest.mark.parametrize(
    "scenario",
    [StatusScenario.EXTRA_FIELD, StatusScenario.INJECTION_TEXT, StatusScenario.INCONSISTENT,
     StatusScenario.WRONG_SOURCE],
)
async def test_simulated_bad_bodies_are_rejected(scenario: StatusScenario) -> None:
    async with session_for(SimulatedControlApiAdapter(status_scenario=scenario)) as s:
        is_error, payload = await call(s)
    assert is_error is True and payload["data"] is None
    assert "telegram_bot_token" not in json.dumps(payload)


async def test_simulated_not_started_declares_unavailable() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.NOT_STARTED)
    async with session_for(adapter) as s:
        is_error, payload = await call(s)
    assert is_error is False
    assert payload["data"]["config"]["settings"] is None
    assert payload["data"]["config"]["unavailable"] == ["settings"]


@pytest.mark.loopback
async def test_real_control_api_round_trip(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.config = lambda: bodies.config(unlisted=["stop_loss_pct"], redacted=3)
        adapter = HttpControlApiAdapter(
            port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
        )
        async with session_for(adapter) as s:
            is_error, payload = await call(s)
    assert is_error is False, payload
    cfg = payload["data"]["config"]
    assert cfg["unlisted"] == ["stop_loss_pct"] and cfg["redacted"] == 3
    assert payload["data"]["upstream"]["kind"] == "http"


@pytest.mark.loopback
@pytest.mark.parametrize(
    "body",
    [
        # segreto con nome sensibile in `unlisted`: lo ferma il MCP
        bodies.config(unlisted=["betfair_password"]),
        # chiave fuori allowlist con valore: lo ferma lo schema del server
        bodies.config(settings=[*bodies.config()["settings"][:-1],
                                {"key": "app_key", "kind": "DECIMAL", "state": "SET",
                                 "value": "1"}]),
        # campo extra con un segreto
        bodies.config(credentials={"password": "x"}),
        # INVALID convertito in zero
        bodies.config(settings=[{**bodies.setting("max_daily_loss"), "state": "INVALID",
                                 "value": "0"}, *bodies.config()["settings"][1:]]),
    ],
)
async def test_leaks_never_reach_the_agent(tmp_path: Path, body: dict[str, Any]) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.config = lambda: body
        adapter = HttpControlApiAdapter(
            port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
        )
        async with session_for(adapter) as s:
            is_error, payload = await call(s)
    assert is_error is True and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    text = json.dumps(payload)
    assert "password" not in text and "app_key" not in text
