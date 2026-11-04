"""MCP-01d: adapter HTTP di prodotto, attraverso il server MCP completo, contro la Control API.

Livello L4 con provider di prova (nessun core): prova trasporto, autenticazione, rotazione,
guasti, compatibilità e assenza di fallback. Il core reale è nelle prove cross-repository.
"""

from __future__ import annotations

import itertools
import json
import logging
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

import pickfair_control_api.server as api_server
from pickfair_mcp.adapters.http import HttpControlApiAdapter, validate_port
from pickfair_mcp.auth import Principal, Scope
from pickfair_mcp.auth.token_file import LocalTokenFile
from pickfair_mcp.server import build_server
from tests.control_api import bodies
from tests.control_api.servers import control_api, free_port, hostile_http, silent_server

pytestmark = [pytest.mark.anyio, pytest.mark.loopback]
READER = Principal(principal_id="reader", scopes=frozenset({Scope.READ}))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _ids() -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"req_{next(counter):032x}"


def adapter_for(port: int, token_path: Path, timeout_s: float = 2.0) -> HttpControlApiAdapter:
    return HttpControlApiAdapter(
        port=port, token_file=LocalTokenFile(token_path), timeout_s=timeout_s
    )


@asynccontextmanager
async def session(
    adapter: HttpControlApiAdapter, principal: Principal | None = READER, timeout_s: float = 2.0
) -> AsyncIterator[ClientSession]:
    server = build_server(
        adapter, timeout_s=timeout_s, principal=principal, request_id_factory=_ids()
    )
    with anyio.fail_after(30):
        async with create_connected_server_and_client_session(server) as s:
            yield s


async def call(s: ClientSession, name: str) -> tuple[bool, dict[str, Any]]:
    result = await s.call_tool(name, {})
    assert result.structuredContent is not None
    return bool(result.isError), result.structuredContent


async def test_reads_through_the_real_control_api(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _store, token_path, _p):
        adapter = adapter_for(server.port, token_path)
        async with session(adapter) as s:
            tools = {t.name: t for t in (await s.list_tools()).tools}
            results = {
                n: await call(s, n) for n in ("get_meta", "get_status", "get_reconciliation_status")
            }
    for name, (is_error, payload) in results.items():
        assert is_error is False, (name, payload)
        jsonschema.validate(payload, tools[name].outputSchema)
    assert results["get_status"][1]["data"]["upstream"] == {"kind": "http", "certified": False}
    assert results["get_status"][1]["data"]["status"]["source"] == "core"
    assert results["get_meta"][1]["data"]["handshake"]["status"] == "COMPATIBLE"
    assert server.request_counts() == {"OK": 3}


async def test_simulated_source_from_http_is_rejected(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.status = lambda: bodies.status(source="simulated")
        async with session(adapter_for(server.port, token_path)) as s:
            is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["details"]["reasons"] == [
        "UPSTREAM_INVALID_RESPONSE:SOURCE_MISMATCH"
    ]


async def test_stale_snapshot_from_core_is_rejected(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.status = lambda: bodies.status(observed_at=time.time() - 3600)
        async with session(adapter_for(server.port, token_path)) as s:
            is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["details"]["reasons"] == [
        "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"
    ]


async def test_off_contract_core_answer_is_never_apparently_valid(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        providers.status = lambda: bodies.status(execution_mode="PAPER")
        async with session(adapter_for(server.port, token_path)) as s:
            is_error, payload = await call(s, "get_status")
    assert is_error and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    assert payload["error"]["details"]["reasons"] == ["UPSTREAM_INVALID_RESPONSE:HTTP_500"]


async def test_incompatible_contract_blocks_before_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_server, "schema_hash", lambda: "0" * 64)
    with control_api(tmp_path) as (server, _s, token_path, providers):
        async with session(adapter_for(server.port, token_path)) as s:
            is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["code"] == "CONTRACT_INCOMPATIBLE"
    assert providers.calls == 0


async def test_wrong_token_is_unauthorized_and_not_retryable(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, _token_path, providers):
        other = tmp_path / "pickfair-control-api" / "other.token"
        from pickfair_control_api.tokens import issue_token_file

        issue_token_file(other)
        async with session(adapter_for(server.port, other)) as s:
            is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["code"] == "UPSTREAM_UNAUTHORIZED"
    assert payload["error"]["retryable"] is False
    assert providers.calls == 0
    assert server.request_counts() == {"UNAUTHORIZED": 2}  # richiesta + un solo nuovo tentativo


async def test_rotation_is_recovered_with_one_reload(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, store, token_path, _p):
        adapter = adapter_for(server.port, token_path)
        async with session(adapter) as s:
            assert (await call(s, "get_status"))[0] is False
            epoch = adapter.connection_epoch
            store.rotate(token_path)
            is_error, payload = await call(s, "get_status")
    assert is_error is False, payload
    assert adapter.connection_epoch > epoch  # rilettura del token => nuovo handshake
    assert server.request_counts()["UNAUTHORIZED"] == 1


async def test_token_file_made_readable_by_others_fails_closed(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, store, token_path, _providers):
        adapter = adapter_for(server.port, token_path)
        async with session(adapter) as s:
            assert (await call(s, "get_status"))[0] is False
            store.rotate(token_path)
            token_path.chmod(0o644)
            is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["code"] == "UPSTREAM_UNAUTHORIZED"


async def test_control_api_down_then_restarted_recovers_with_new_handshake(tmp_path: Path) -> None:
    port = free_port()
    with control_api(tmp_path, port=port) as (server, _s, token_path, _p):
        adapter = adapter_for(port, token_path)
        async with session(adapter) as s:
            assert (await call(s, "get_status"))[0] is False
            server.stop()
            down_error, down = await call(s, "get_status")
            with control_api(tmp_path, port=port) as (server2, _s2, _t2, _p2):
                up_error, up = await call(s, "get_status")
    assert down_error and down["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert down["error"]["retryable"] is True and down["data"] is None
    assert up_error is False, up
    assert server2.request_counts().get("OK", 0) == 2  # nuovo handshake + lettura
    # nessun fallback: durante il fermo nessun dato, mai una sorgente simulata
    assert "simulated" not in json.dumps(down)


async def test_timeout_is_retryable_and_bounded(tmp_path: Path) -> None:
    from pickfair_control_api.tokens import issue_token_file

    token_path = tmp_path / "pickfair-control-api" / "t"
    token_path.parent.mkdir(mode=0o700)
    issue_token_file(token_path)
    with silent_server() as port:
        adapter = adapter_for(port, token_path, timeout_s=0.3)
        started = time.monotonic()
        async with session(adapter, timeout_s=0.3) as s:
            is_error, payload = await call(s, "get_status")
        elapsed = time.monotonic() - started
    assert is_error and payload["error"]["code"] == "UPSTREAM_TIMEOUT"
    assert payload["error"]["retryable"] is True
    assert elapsed < 10


def _redirect(h: Any) -> None:
    h.send_response(302)
    h.send_header("Location", "http://127.0.0.1:1/v1/meta")
    h.send_header("Content-Length", "0")
    h.end_headers()


def _wrong_type(h: Any) -> None:
    body = b'{"contract_version": "1.1.0"}'
    h.send_response(200)
    h.send_header("Content-Type", "text/html")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _huge(h: Any) -> None:
    body = b"{" + b" " * (2 * 1024 * 1024) + b"}"
    h.send_response(200)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    try:
        h.wfile.write(body)
    except OSError:
        pass


@pytest.mark.parametrize(
    ("respond", "reason"),
    [
        (_redirect, "UPSTREAM_INVALID_RESPONSE:HTTP_302"),
        (_wrong_type, "UPSTREAM_INVALID_RESPONSE:CONTENT_TYPE"),
        (_huge, "UPSTREAM_INVALID_RESPONSE:TOO_LARGE"),
    ],
)
async def test_protocol_violations_fail_closed(tmp_path: Path, respond: Any, reason: str) -> None:
    from pickfair_control_api.tokens import issue_token_file

    token_path = tmp_path / "pickfair-control-api" / "t"
    token_path.parent.mkdir(mode=0o700)
    issue_token_file(token_path)
    with hostile_http(respond) as (port, seen):
        async with session(adapter_for(port, token_path)) as s:
            is_error, payload = await call(s, "get_meta")
    assert is_error and payload["error"]["details"]["reasons"] == [reason]
    assert seen == ["/v1/meta"]  # nessun redirect seguito, nessuna richiesta aggiuntiva


async def test_environment_proxy_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with hostile_http(lambda h: h.send_error(502)) as (proxy_port, proxy_seen):
        for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(var, f"http://127.0.0.1:{proxy_port}")
        monkeypatch.setenv("NO_PROXY", "")
        with control_api(tmp_path) as (server, _s, token_path, _p):
            async with session(adapter_for(server.port, token_path)) as s:
                is_error, _payload = await call(s, "get_status")
    assert is_error is False
    assert proxy_seen == []


async def test_unauthorized_principal_never_reaches_the_control_api(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        adapter = adapter_for(server.port, token_path)
        writer = Principal(principal_id="w", scopes=frozenset({Scope.WRITE}))
        async with session(adapter, principal=writer) as s:
            is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["code"] == "FORBIDDEN"
    assert adapter.requests == 0 and server.request_counts() == {} and providers.calls == 0


async def test_concurrent_reads_share_one_handshake(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, _p):
        adapter = adapter_for(server.port, token_path)
        results: list[bool] = []
        async with session(adapter) as s:

            async def one(name: str) -> None:
                results.append((await call(s, name))[0])

            async with anyio.create_task_group() as tg:
                for i in range(20):
                    tg.start_soon(one, ("get_status", "get_reconciliation_status")[i % 2])
    assert results == [False] * 20
    assert server.request_counts() == {"OK": 21}


async def test_no_secret_in_payloads_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    with control_api(tmp_path) as (server, _s, token_path, _p):
        token = token_path.read_text()
        async with session(adapter_for(server.port, token_path)) as s:
            payloads = [await call(s, n) for n in ("get_meta", "get_status")]
    captured = capsys.readouterr()
    text = json.dumps(payloads) + caplog.text + captured.err + captured.out
    assert token not in text and str(token_path) not in json.dumps(payloads)


@pytest.mark.parametrize("port", [0, -1, 65536, "8765", True, None])
def test_port_validation(port: Any) -> None:
    with pytest.raises(ValueError):
        validate_port(port)
