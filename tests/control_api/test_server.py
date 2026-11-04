"""Server Control API su loopback reale: autenticazione, Host, metodi, percorsi, auto-verifica."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from pickfair_control_api.contract import CAPABILITIES, CONTRACT_VERSION, schema_hash
from pickfair_control_api.server import ControlApiConfigError, ControlApiServer
from pickfair_control_api.tokens import TokenStore
from pickfair_mcp.adapters.http import _LoopbackConnection
from tests.control_api import bodies
from tests.control_api.servers import SHA, Providers, control_api

pytestmark = pytest.mark.loopback


def request(
    port: int,
    method: str,
    path: str,
    *,
    token: str | None,
    host: str | None = None,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], Any]:
    conn = _LoopbackConnection(port, 5.0)  # stessa connessione dell'adapter: niente DNS
    hdrs = {"Host": host or f"127.0.0.1:{port}"}
    if token is not None:
        hdrs["Authorization"] = f"Bearer {token}"
    hdrs.update(headers or {})
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return (
        resp.status,
        {k.lower(): v for k, v in resp.getheaders()},
        json.loads(raw) if raw else None,
    )


@pytest.fixture
def api(tmp_path: Path) -> Any:
    with control_api(tmp_path) as ctx:
        yield ctx


def test_meta_is_the_shared_contract(api: Any) -> None:
    server, _store, token_path, _p = api
    status, headers, body = request(server.port, "GET", "/v1/meta", token=token_path.read_text())
    assert status == 200
    assert body == {
        "contract_version": CONTRACT_VERSION,
        "capabilities": list(CAPABILITIES),
        "git_sha": SHA,
        "schema_hash": schema_hash(),
    }
    assert headers["content-type"] == "application/json; charset=utf-8"
    assert headers["cache-control"] == "no-store"


@pytest.mark.parametrize("token", [None, "", "x" * 43])
def test_unauthorized(api: Any, token: str | None) -> None:
    server, *_ = api
    assert request(server.port, "GET", "/v1/status", token=token)[0::2] == (
        401,
        {"error": {"code": "UNAUTHORIZED"}},
    )


@pytest.mark.parametrize("host", ["localhost", "evil.example", "127.0.0.1", "[::1]:80"])
def test_wrong_host(api: Any, host: str) -> None:
    server, _s, token_path, _p = api
    assert (
        request(server.port, "GET", "/v1/status", token=token_path.read_text(), host=host)[0] == 400
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("path", ["/v1/status", "/v1/orders", "/v1/mode", "/v1/cashout"])
def test_no_mutating_method(api: Any, method: str, path: str) -> None:
    server, _s, token_path, _p = api
    assert request(server.port, method, path, token=token_path.read_text(), body=b"{}")[0::2] == (
        405,
        {"error": {"code": "METHOD_NOT_ALLOWED"}},
    )


@pytest.mark.parametrize(
    "path",
    [
        "/v1/status/",
        "/v1/status?x=1",
        "//v1/status",
        "/",
        "/v1/cashout",
        "/v1/mode",
        "/v1/orders/1/cancel",
        "/v1/markets/../book",
        "/v1/operations?status=done",
        "/v1/audit/",
        "/v1/operations/.",
        "/v2/orders",
    ],
)
def test_unknown_paths(api: Any, path: str) -> None:
    server, _s, token_path, providers = api
    status, _h, body = request(server.port, "GET", path, token=token_path.read_text())
    assert (status, body) == (404, {"error": {"code": "NOT_FOUND"}})
    assert providers.calls == 0


@pytest.mark.parametrize(
    "path",
    [
        "/v1/orders",
        "/v1/config",
        "/v1/events",
        "/v1/markets",
        "/v1/markets/1.234567/book",
        "/v1/operations/op-1",
        "/v1/operations?status=pending",
        "/v1/audit/corr-1",
    ],
)
def test_approved_but_unserved_reads_are_typed_not_implemented(api: Any, path: str) -> None:
    """Route di lettura approvate ma assenti nel core: 501 tipizzato, mai un dato, mai il core."""
    server, _s, token_path, providers = api
    status, _h, body = request(server.port, "GET", path, token=token_path.read_text())
    assert (status, body) == (501, {"error": {"code": "NOT_IMPLEMENTED"}})
    assert providers.calls == 0


def test_not_implemented_still_requires_auth_and_host(api: Any) -> None:
    server, _s, _token_path, _p = api
    assert request(server.port, "GET", "/v1/orders", token="x" * 43)[0] == 401


def test_get_with_body_rejected(api: Any) -> None:
    server, _s, token_path, _p = api
    assert (
        request(server.port, "GET", "/v1/status", token=token_path.read_text(), body=b"{}")[0]
        == 400
    )


@pytest.mark.parametrize(
    "bad",
    [
        lambda: bodies.status(balance=100.0),
        lambda: bodies.status(execution_mode="SIMULATION"),
        lambda: bodies.status(stop=None),
        lambda: bodies.status(
            readiness={
                "level": "NOT_READY",
                "ready": False,
                "blockers": ["LIVE\n"],
                "mcp_aware": False,
            }
        ),
        lambda: bodies.status(observed_at=float("nan")),
        lambda: {"ok": True},
        lambda: bodies.status(
            readiness={
                "level": "NOT_READY",
                "ready": False,
                "blockers": [f"B{i}" for i in range(33)],
                "mcp_aware": False,
            }
        ),
    ],
)
def test_off_contract_provider_output_never_leaves_the_server(api: Any, bad: Any) -> None:
    server, _s, token_path, providers = api
    providers.status = bad
    status, _h, body = request(server.port, "GET", "/v1/status", token=token_path.read_text())
    assert (status, body) == (500, {"error": {"code": "CONTRACT_SELF_CHECK"}})


def test_provider_exception_is_a_fixed_internal_error(
    api: Any, caplog: pytest.LogCaptureFixture
) -> None:
    server, _s, token_path, providers = api

    def boom() -> dict[str, Any]:
        raise RuntimeError("password=hunter2")

    providers.status = boom
    caplog.set_level(logging.DEBUG)
    status, _h, body = request(server.port, "GET", "/v1/status", token=token_path.read_text())
    assert (status, body) == (500, {"error": {"code": "INTERNAL"}})
    assert "hunter2" not in caplog.text


def test_token_never_logged(api: Any, caplog: pytest.LogCaptureFixture) -> None:
    server, _s, token_path, _p = api
    caplog.set_level(logging.DEBUG)
    token = token_path.read_text()
    request(server.port, "GET", "/v1/status", token=token)
    request(server.port, "GET", "/v1/status", token="wrong-token-value-" + "z" * 30)
    assert token not in caplog.text and "wrong-token-value" not in caplog.text


def test_rotation_mid_traffic_never_fails_a_reader_using_the_file(api: Any) -> None:
    server, store, token_path, _p = api
    results: list[int] = []
    lock = threading.Lock()

    def reader() -> None:
        for _ in range(20):
            token = token_path.read_text()
            status = request(server.port, "GET", "/v1/status", token=token)[0]
            if status == 401:  # lettura del file avvenuta prima della revoca: rilettura una volta
                status = request(server.port, "GET", "/v1/status", token=token_path.read_text())[0]
            with lock:
                results.append(status)

    readers = [threading.Thread(target=reader) for _ in range(5)]
    for t in readers:
        t.start()
    # Limite dichiarato: un solo nuovo tentativo copre una rotazione per andata e ritorno.
    # Rotazioni a raffica (più di una durante una richiesta) possono dare 401 legittimi.
    for _ in range(10):
        time.sleep(0.05)
        store.rotate(token_path)
    for t in readers:
        t.join()
    assert results == [200] * 100


@pytest.mark.parametrize("host", ["0.0.0.0", "localhost", "::1", "127.0.0.2", ""])
def test_non_loopback_literal_host_refused(host: str) -> None:
    with pytest.raises(ControlApiConfigError, match="HOST_NOT_LOOPBACK_LITERAL"):
        ControlApiServer(
            Providers().mapping(),
            host=host,
            port=0,
            tokens=TokenStore("a" * 43),
            git_sha=SHA,
            allow_ephemeral_port=True,
        )


@pytest.mark.parametrize("port", [0, -1, 70000, "8765", True])
def test_port_must_be_explicit(port: Any) -> None:
    with pytest.raises(ControlApiConfigError, match="PORT_NOT_EXPLICIT"):
        ControlApiServer(Providers().mapping(), port=port, tokens=TokenStore("a" * 43), git_sha=SHA)


def test_invalid_configuration_refused() -> None:
    good = {"port": 0, "tokens": TokenStore("a" * 43), "git_sha": SHA, "allow_ephemeral_port": True}
    with pytest.raises(ControlApiConfigError, match="GIT_SHA_INVALID"):
        ControlApiServer(Providers().mapping(), **{**good, "git_sha": "A" * 40})
    with pytest.raises(ControlApiConfigError, match="TOKEN_STORE_REQUIRED"):
        ControlApiServer(Providers().mapping(), **{**good, "tokens": "a" * 43})
    with pytest.raises(ControlApiConfigError, match="PROVIDERS_INVALID"):
        ControlApiServer({"status": bodies.status}, **good)
    with pytest.raises(ControlApiConfigError, match="PROVIDERS_INVALID"):
        ControlApiServer({**Providers().mapping(), "orders": bodies.status}, **good)


def test_restart_on_the_same_port_is_immediate_but_never_shared(tmp_path: Path) -> None:
    from tests.control_api.servers import free_port

    port = free_port()
    with control_api(tmp_path, port=port) as (_server, _s, token_path, _p):
        assert request(port, "GET", "/v1/meta", token=token_path.read_text())[0] == 200
        with pytest.raises(OSError):  # un secondo server in ascolto sulla stessa porta: mai
            ControlApiServer(
                Providers().mapping(), port=port, tokens=TokenStore("a" * 43), git_sha=SHA
            )
    with control_api(tmp_path, port=port) as (_server2, _s2, token_path2, _p2):  # riavvio subito
        assert request(port, "GET", "/v1/meta", token=token_path2.read_text())[0] == 200


def test_almost_equal_tokens_are_rejected(api: Any) -> None:
    server, _s, token_path, _p = api
    token = token_path.read_text()
    for wrong in (token[:-1] + ("A" if token[-1] != "A" else "B"), token[:-1], token + "A"):
        assert request(server.port, "GET", "/v1/status", token=wrong)[0] == 401


def test_rotation_401s_are_legitimate_and_old_tokens_are_never_accepted(api: Any) -> None:
    """Distinzione: un 401 con un token appena ruotato è LEGITTIMO (si risolve rileggendo il file);
    un token revocato accettato dopo la fine della rotazione sarebbe un DIFETTO di sicurezza."""
    server, store, token_path, _p = api
    issued: list[str] = [token_path.read_text()]
    legit_401 = recovered = 0
    for _ in range(15):
        stale = token_path.read_text()
        store.rotate(token_path)
        issued.append(token_path.read_text())
        status = request(server.port, "GET", "/v1/status", token=stale)[0]
        if status == 401:
            legit_401 += 1
            if request(server.port, "GET", "/v1/status", token=token_path.read_text())[0] == 200:
                recovered += 1
    assert legit_401 == 15 and recovered == 15  # ogni 401 si risolve con la rilettura
    for old in issued[:-1]:  # sicurezza: nessun token revocato è più accettato
        assert request(server.port, "GET", "/v1/status", token=old)[0] == 401
    assert request(server.port, "GET", "/v1/status", token=issued[-1])[0] == 200
