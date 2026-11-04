"""MCP-02a: get_status e get_reconciliation_status attraverso il server MCP reale (in-process).

Prove L2: adapter simulato deterministico. Non equivalgono a integrazione con il core.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
import jsonschema
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from pickfair_mcp.adapters.simulated import Scenario, SimulatedControlApiAdapter, StatusScenario
from pickfair_mcp.auth import Principal, Scope
from pickfair_mcp.cli import LOCAL_STDIO_PRINCIPAL as LOCAL
from pickfair_mcp.server import build_server

pytestmark = pytest.mark.anyio

TOOLS = ("get_status", "get_reconciliation_status")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def counter_ids() -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"req_{next(counter):032x}"


@asynccontextmanager
async def session_for(
    adapter: SimulatedControlApiAdapter, *, principal: Principal | None = LOCAL
) -> AsyncIterator[ClientSession]:
    server = build_server(
        adapter, timeout_s=0.2, principal=principal, request_id_factory=counter_ids()
    )
    with anyio.fail_after(20):
        async with create_connected_server_and_client_session(server) as session:
            yield session


async def call(session: ClientSession, name: str, args: dict[str, Any] | None = None) -> Any:
    result = await session.call_tool(name, args or {})
    payload = result.structuredContent
    assert payload is not None
    assert json.loads(result.content[0].text) == payload  # type: ignore[union-attr]
    return result.isError, payload


def upstream_calls(adapter: SimulatedControlApiAdapter) -> int:
    return adapter.status_calls + adapter.reconciliation_calls


async def test_both_tools_listed_as_read_only_with_output_schema() -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
    assert set(tools) == {"get_meta", *TOOLS, "get_account", "get_exposure", "list_positions"}
    for name in TOOLS:
        tool = tools[name]
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.inputSchema.get("additionalProperties") is False
        assert tool.inputSchema.get("properties", {}) == {}
        assert tool.outputSchema is not None
        assert "simulat" in (tool.description or "").lower() or "upstream" in (
            tool.description or ""
        )


async def test_get_status_sim_ready_is_marked_simulated() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        is_error, payload = await call(session, "get_status")
    assert is_error is False
    data = payload["data"]
    assert data["upstream"] == {"kind": "simulated", "certified": False}
    assert data["status"]["source"] == "simulated"
    assert data["status"]["execution_mode"] == "SIM"
    assert data["status"]["runtime_state"] == "ACTIVE"
    assert data["status"]["readiness"]["mcp_aware"] is False
    jsonschema.validate(payload, tools["get_status"].outputSchema)


async def test_get_reconciliation_status_ok_is_marked_simulated() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        is_error, payload = await call(session, "get_reconciliation_status")
    assert is_error is False
    assert payload["data"]["upstream"] == {"kind": "simulated", "certified": False}
    assert payload["data"]["reconciliation"]["source"] == "simulated"
    assert payload["data"]["reconciliation"]["startup"]["state"] == "OK"


async def test_live_blocked_reports_blockers_as_data() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.LIVE_BLOCKED)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, "get_status")
    assert is_error is False
    readiness = payload["data"]["status"]["readiness"]
    assert payload["data"]["status"]["execution_mode"] == "LIVE"
    assert readiness["ready"] is False
    assert readiness["level"] == "NOT_READY"
    assert "LIVE_NOT_ENABLED" in readiness["blockers"]


async def test_stop_active_reported() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.STOP_ACTIVE)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, "get_status")
    assert is_error is False
    stop = payload["data"]["status"]["stop"]
    assert stop["emergency_stopped"] is True
    assert stop["emergency_reason"] == "DAILY_LOSS_BREACH"


async def test_reconciliation_required_reported() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.RECONCILIATION_REQUIRED)
    async with session_for(adapter) as session:
        _, status = await call(session, "get_status")
        is_error, payload = await call(session, "get_reconciliation_status")
    assert is_error is False
    recon = payload["data"]["reconciliation"]
    assert recon["startup"]["state"] == "REQUIRED"
    assert recon["ambiguities_pending"] == 2
    assert status["data"]["status"]["runtime_state"] == "PAUSED"


async def test_not_started_reports_unavailable_never_defaults() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.NOT_STARTED)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, "get_reconciliation_status")
    assert is_error is False
    recon = payload["data"]["reconciliation"]
    assert recon["startup"]["state"] == "NOT_RUN"
    assert recon["recovery_state"] is None
    assert "recovery_state" in recon["unavailable"]


@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        (StatusScenario.MALFORMED, "UPSTREAM_INVALID_RESPONSE:NOT_JSON"),
        (StatusScenario.EXTRA_FIELD, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.NON_FINITE, "UPSTREAM_INVALID_RESPONSE:NON_FINITE_NUMBER"),
        (StatusScenario.OVERSIZED, "UPSTREAM_INVALID_RESPONSE:TOO_LARGE"),
        (StatusScenario.INJECTION_TEXT, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.INCONSISTENT, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.WRONG_SOURCE, "UPSTREAM_INVALID_RESPONSE:SOURCE_MISMATCH"),
        (StatusScenario.STALE, "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"),
        (StatusScenario.FUTURE, "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"),
    ],
)
@pytest.mark.parametrize("tool", TOOLS)
async def test_invalid_upstream_answers_fail_closed(
    tool: str, scenario: StatusScenario, reason: str
) -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=scenario)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True
    assert payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    assert payload["error"]["details"]["reasons"] == [reason]
    assert payload["error"]["retryable"] is False


@pytest.mark.parametrize("tool", TOOLS)
async def test_injection_text_never_echoed(tool: str) -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.INJECTION_TEXT)
    async with session_for(adapter) as session:
        result = await session.call_tool(tool, {})
    text = result.content[0].text  # type: ignore[union-attr]
    assert "IGNORE" not in text and "cashout" not in text.lower()


@pytest.mark.parametrize("tool", TOOLS)
async def test_timeout_is_retryable_read_error_after_bounded_attempts(tool: str) -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.TIMEOUT)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True
    assert payload["error"]["code"] == "UPSTREAM_TIMEOUT"
    assert payload["error"]["retryable"] is True
    assert upstream_calls(adapter) == 2


@pytest.mark.parametrize("tool", TOOLS)
async def test_unavailable_is_retryable_read_error(tool: str) -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.UNAVAILABLE)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True
    assert payload["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert upstream_calls(adapter) == 2


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize(
    "meta_scenario",
    [Scenario.INCOMPATIBLE_MAJOR, Scenario.SCHEMA_HASH_MISMATCH, Scenario.UNAPPROVED_CAPABILITY],
)
async def test_incompatible_contract_blocks_before_any_read(
    tool: str, meta_scenario: Scenario
) -> None:
    adapter = SimulatedControlApiAdapter(meta_scenario)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True
    assert payload["error"]["code"] == "CONTRACT_INCOMPATIBLE"
    assert upstream_calls(adapter) == 0


@pytest.mark.parametrize(
    ("tool", "missing"),
    [
        ("get_status", "GET /v1/status"),
        ("get_reconciliation_status", "GET /v1/reconciliation/status"),
    ],
)
async def test_missing_capability_blocks_before_read(tool: str, missing: str) -> None:
    adapter = SimulatedControlApiAdapter(Scenario.META_ONLY)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True
    assert payload["error"]["code"] == "CONTRACT_INCOMPATIBLE"
    assert f"CAPABILITY_MISSING:{missing}" in payload["error"]["details"]["reasons"]
    assert upstream_calls(adapter) == 0


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize(
    "principal",
    [
        None,
        Principal(principal_id="writer", scopes=frozenset({Scope.WRITE})),
        Principal(principal_id="owner", scopes=frozenset({Scope.OWNER})),
    ],
)
async def test_forbidden_before_handshake_and_upstream(
    tool: str, principal: Principal | None
) -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter, principal=principal) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True
    assert payload["error"]["code"] == "FORBIDDEN"
    assert adapter.meta_calls == 0
    assert upstream_calls(adapter) == 0


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("args", [{"x": 1}, {"mode": "LIVE"}, {"execution_mode": "SIM"}])
async def test_arguments_rejected(tool: str, args: dict[str, Any]) -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool, args)
    assert is_error is True
    assert payload["error"]["code"] == "INVALID_REQUEST"
    assert upstream_calls(adapter) == 0


async def test_concurrent_reads_are_consistent_and_share_one_handshake() -> None:
    adapter = SimulatedControlApiAdapter()
    results: list[Any] = []
    async with session_for(adapter) as session:

        async def one(name: str) -> None:
            results.append((name, await call(session, name)))

        async with anyio.create_task_group() as tg:
            for i in range(20):
                tg.start_soon(one, TOOLS[i % 2])
    assert len(results) == 20
    assert all(is_error is False for _, (is_error, _) in results)
    assert adapter.meta_calls == 1
    assert upstream_calls(adapter) == 20


async def test_reconnect_repeats_handshake_before_reads() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        await call(session, "get_status")
        adapter.reconnect(Scenario.INCOMPATIBLE_MAJOR)
        is_error, payload = await call(session, "get_status")
    assert is_error is True
    assert payload["error"]["code"] == "CONTRACT_INCOMPATIBLE"
    assert adapter.meta_calls == 2
    assert adapter.status_calls == 1
