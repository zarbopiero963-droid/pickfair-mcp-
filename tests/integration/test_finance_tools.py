"""MCP-01e: get_account e get_exposure attraverso il server MCP reale.

Due livelli, tenuti distinti:
- adapter SIMULATO (dati fittizi, `source=simulated`): logica del tool, errori, sicurezza;
- adapter HTTP di prodotto contro la Control API REALE su 127.0.0.1 con provider di prova
  (`source=core` ma provider sostituiti): trasporto, auto-verifica del server, autenticazione.
Nessuno dei due è integrazione con Pickfair: quella è in tests/crossrepo (core reale).
"""

from __future__ import annotations

import itertools
import json
import time
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
from pickfair_mcp.adapters.simulated import Scenario, SimulatedControlApiAdapter, StatusScenario
from pickfair_mcp.auth import Principal, Scope
from pickfair_mcp.auth.token_file import LocalTokenFile
from pickfair_mcp.cli import LOCAL_STDIO_PRINCIPAL as LOCAL
from pickfair_mcp.server import build_server
from tests.control_api import bodies
from tests.control_api.servers import control_api

pytestmark = pytest.mark.anyio

TOOLS = ("get_account", "get_exposure")
SECTION = {"get_account": "account", "get_exposure": "exposure"}


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
    payload = result.structuredContent
    assert payload is not None
    return bool(result.isError), payload


def reads(adapter: SimulatedControlApiAdapter) -> int:
    return adapter.account_calls + adapter.exposure_calls


# ------------------------------------------------------------------ adapter simulato


async def test_tools_are_listed_read_only_with_strict_schemas() -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
    assert set(TOOLS) <= set(tools)
    for name in TOOLS:
        tool = tools[name]
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.inputSchema.get("additionalProperties") is False
        assert tool.inputSchema.get("properties", {}) == {}
        assert "never real money" in (tool.description or "")


@pytest.mark.parametrize("tool", TOOLS)
async def test_simulated_answers_are_marked_simulated(tool: str) -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        is_error, payload = await call(session, tool)
    assert is_error is False, payload
    jsonschema.validate(payload, tools[tool].outputSchema)
    data = payload["data"]
    assert data["upstream"] == {"kind": "simulated", "certified": False}
    assert data[SECTION[tool]]["source"] == "simulated"
    assert data[SECTION[tool]]["consistency"] == "PER_SECTION_LOCKED"


async def test_account_values_are_reported_not_recomputed() -> None:
    async with session_for(
        SimulatedControlApiAdapter(status_scenario=StatusScenario.STOP_ACTIVE)
    ) as session:
        _e, payload = await call(session, "get_account")
    account = payload["data"]["account"]
    # Il MCP riporta il desk mode del core anche se dai numeri si potrebbe «ricalcolarlo».
    assert account["desk_mode"] == "LOCKDOWN"
    assert account["bankroll"]["drawdown_pct"] == 23.52941176470588


async def test_live_basis_without_verified_cash_is_explicit() -> None:
    async with session_for(
        SimulatedControlApiAdapter(status_scenario=StatusScenario.LIVE_BLOCKED)
    ) as session:
        _e, payload = await call(session, "get_account")
    account = payload["data"]["account"]
    assert account["execution_mode"] == "LIVE"
    assert account["cash"] == {
        "verified": False,
        "cash_equity": None,
        "committed_exposure": 0.0,
        "unverified_reason": "CASH_NOT_READ",
    }
    assert account["exchange_funds"] is None and account["unavailable"] == ["exchange_funds"]


async def test_not_started_reports_unavailable_never_zero() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.NOT_STARTED)
    async with session_for(adapter) as session:
        _e1, account = await call(session, "get_account")
        _e2, exposure = await call(session, "get_exposure")
    a = account["data"]["account"]
    assert a["bankroll"] is None and a["desk_mode"] is None
    assert set(a["unavailable"]) == {"bankroll", "exchange_funds", "desk_mode"}
    e = exposure["data"]["exposure"]
    assert e["total_exposure"] is None and e["unavailable"] == ["total_exposure"]


async def test_recovery_tables_are_reported() -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.RECONCILIATION_REQUIRED)
    async with session_for(adapter) as session:
        _e, payload = await call(session, "get_exposure")
    exposure = payload["data"]["exposure"]
    assert exposure["tables"][1]["status"] == "RECOVERY"
    assert exposure["tables"][1]["loss_amount"] == 12.0
    assert exposure["recovery"] == {
        "active_count": 1,
        "max_recovery_tables": 2,
        "allow_recovery": True,
    }


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        (StatusScenario.MALFORMED, "UPSTREAM_INVALID_RESPONSE:"),
        (StatusScenario.EXTRA_FIELD, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.NON_FINITE, "UPSTREAM_INVALID_RESPONSE:"),
        (StatusScenario.OVERSIZED, "UPSTREAM_INVALID_RESPONSE:"),
        (StatusScenario.INCONSISTENT, "UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION"),
        (StatusScenario.WRONG_SOURCE, "UPSTREAM_INVALID_RESPONSE:SOURCE_MISMATCH"),
        (StatusScenario.STALE, "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"),
        (StatusScenario.FUTURE, "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"),
    ],
)
async def test_invalid_upstream_answers_fail_closed(
    tool: str, scenario: StatusScenario, reason: str
) -> None:
    async with session_for(SimulatedControlApiAdapter(status_scenario=scenario)) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    assert payload["error"]["details"]["reasons"][0].startswith(reason)


@pytest.mark.parametrize("tool", TOOLS)
async def test_injection_text_is_never_echoed(tool: str) -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.INJECTION_TEXT)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True
    assert "IGNORE" not in json.dumps(payload)


@pytest.mark.parametrize("tool", TOOLS)
async def test_timeout_is_bounded_and_retryable(tool: str) -> None:
    adapter = SimulatedControlApiAdapter(status_scenario=StatusScenario.TIMEOUT)
    started = time.monotonic()
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert time.monotonic() - started < 5
    assert is_error is True and payload["error"]["code"] == "UPSTREAM_TIMEOUT"
    assert payload["error"]["retryable"] is True
    assert reads(adapter) == 2  # tentativi limitati


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize(
    "scenario",
    [Scenario.INCOMPATIBLE_MAJOR, Scenario.UNSUPPORTED_MINOR, Scenario.SCHEMA_HASH_MISMATCH],
)
async def test_incompatible_contract_blocks_before_any_read(tool: str, scenario: Scenario) -> None:
    adapter = SimulatedControlApiAdapter(scenario)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True and payload["error"]["code"] == "CONTRACT_INCOMPATIBLE"
    assert reads(adapter) == 0


@pytest.mark.parametrize("tool", TOOLS)
async def test_core_without_the_capability_is_never_read(tool: str) -> None:
    # Un core 1.2.0 che non dichiara la route: nessuna lettura, errore di contratto.
    adapter = SimulatedControlApiAdapter(Scenario.META_ONLY)
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True and payload["error"]["code"] == "CONTRACT_INCOMPATIBLE"
    assert reads(adapter) == 0


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize(
    "principal",
    [
        None,
        Principal(principal_id="writer", scopes=frozenset({Scope.WRITE})),
        Principal(principal_id="owner", scopes=frozenset({Scope.OWNER})),
    ],
)
async def test_unauthorized_principal_never_reaches_upstream(
    tool: str, principal: Principal | None
) -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter, principal=principal) as session:
        is_error, payload = await call(session, tool)
    assert is_error is True and payload["error"]["code"] == "FORBIDDEN"
    assert reads(adapter) == 0 and adapter.meta_calls == 0


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize(
    "args", [{"table_id": 1}, {"market_id": "1.2"}, {"all": True}, {"execute": True}]
)
async def test_arguments_are_rejected(tool: str, args: dict[str, Any]) -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        is_error, payload = await call(session, tool, args)
    assert is_error is True and payload["error"]["code"] == "INVALID_REQUEST"
    assert reads(adapter) == 0


async def test_concurrent_reads_share_one_handshake() -> None:
    adapter = SimulatedControlApiAdapter()
    results: list[Any] = []
    async with session_for(adapter) as session:

        async def one(name: str) -> None:
            results.append(await call(session, name))

        async with anyio.create_task_group() as tg:
            for name in TOOLS * 10:
                tg.start_soon(one, name)
    assert all(not is_error for is_error, _ in results)
    assert adapter.meta_calls == 1
    assert reads(adapter) == 20


# ------------------------------------------------------------------ Control API reale (HTTP)


def http_adapter(port: int, token_path: Path) -> HttpControlApiAdapter:
    return HttpControlApiAdapter(port=port, token_file=LocalTokenFile(token_path), timeout_s=2.0)


@pytest.mark.loopback
async def test_reads_through_the_real_control_api(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, _p):
        async with session_for(http_adapter(server.port, token_path)) as session:
            tools = {t.name: t for t in (await session.list_tools()).tools}
            results = {name: await call(session, name) for name in TOOLS}
    for name, (is_error, payload) in results.items():
        assert is_error is False, (name, payload)
        jsonschema.validate(payload, tools[name].outputSchema)
        assert payload["data"]["upstream"] == {"kind": "http", "certified": False}
        assert payload["data"][SECTION[name]]["source"] == "core"
    assert server.request_counts() == {"OK": 3}  # meta + due letture


@pytest.mark.loopback
@pytest.mark.parametrize(
    ("tool", "provider", "body"),
    [
        ("get_account", "account", bodies.account(desk_mode="YOLO")),
        ("get_account", "account", bodies.account(cash=None)),  # null non dichiarato
        ("get_exposure", "exposure", bodies.exposure(total_exposure=-1.0)),
        (
            "get_exposure",
            "exposure",
            bodies.exposure(tables=[{**bodies.table(1), "customer_ref": "x"}]),
        ),
    ],
)
async def test_off_contract_core_answer_is_stopped_by_the_server_self_check(
    tmp_path: Path, tool: str, provider: str, body: dict[str, Any]
) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        setattr(providers, provider, lambda: body)
        async with session_for(http_adapter(server.port, token_path)) as session:
            is_error, payload = await call(session, tool)
    assert is_error is True and payload["data"] is None
    assert payload["error"]["details"]["reasons"] == ["UPSTREAM_INVALID_RESPONSE:HTTP_500"]
    assert server.request_counts().get("CONTRACT_SELF_CHECK") == 1


@pytest.mark.loopback
async def test_failing_core_read_is_internal_and_leaks_nothing(tmp_path: Path) -> None:
    def boom() -> dict[str, Any]:
        raise RuntimeError("password=hunter2 /home/secret")

    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.account = boom
        async with session_for(http_adapter(server.port, token_path)) as session:
            is_error, payload = await call(session, "get_account")
    assert is_error is True
    assert "hunter2" not in json.dumps(payload) and "secret" not in json.dumps(payload)
    assert server.request_counts().get("INTERNAL") == 1


@pytest.mark.loopback
async def test_not_implemented_from_the_core_is_typed_and_not_retried(tmp_path: Path) -> None:
    # Un core che dichiara la capability ma risponde 501 (es. route ritirata): errore tipizzato.
    from tests.control_api.servers import hostile_http

    def respond(handler: Any) -> None:
        payload = b'{"error": {"code": "NOT_IMPLEMENTED"}}'
        handler.send_response(501)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    token = tmp_path / "pickfair-control-api"
    token.mkdir(mode=0o700)
    from pickfair_control_api.tokens import issue_token_file

    issue_token_file(token / "t.token")
    with hostile_http(respond) as (port, seen):
        adapter = http_adapter(port, token / "t.token")
        with pytest.raises(Exception) as excinfo:
            await adapter.get_account_raw()
    assert type(excinfo.value).__name__ == "UpstreamNotImplemented"
    assert seen == ["/v1/account"]

    from pickfair_mcp.errors import ErrorCode
    from pickfair_mcp.journal.retry import read_with_retry

    calls = 0

    async def read() -> bytes:
        nonlocal calls
        calls += 1
        raise type(excinfo.value)()

    with pytest.raises(Exception) as err:
        await read_with_retry(read, attempts=2, timeout_s=1.0)
    assert err.value.code is ErrorCode.UPSTREAM_NOT_IMPLEMENTED  # type: ignore[attr-defined]
    assert calls == 1
