"""MCP-SEC-01: debolezze riprodotte dalla revisione di sicurezza indipendente del 05/11/2026 (test RED → GREEN).

1. token vuoto o corto accettato da `TokenStore`;
2. rotazioni concorrenti con scrittura fallita: token revocato di nuovo valido, token del file rifiutato;
3. connessioni senza token tenute aperte senza limite (slowloris): thread illimitati nel processo Pickfair;
4. risposte d'errore della libreria standard non JSON, con eco dell'input; traceback su stderr alla
   disconnessione del client.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import pickfair_control_api.tokens as tokens_mod
from pickfair_control_api import server as server_mod
from pickfair_control_api.tokens import TokenStore, issue_token_file
from tests.control_api.servers import control_api
from tests.control_api.test_server import request

pytestmark = pytest.mark.loopback


def connect(port: int) -> socket.socket:
    """Connessione TCP diretta a 127.0.0.1 (create_connection risolverebbe un nome: vietato nei test)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(("127.0.0.1", port))
    return s


# ------------------------------------------------------------------ 1. token deboli


@pytest.mark.parametrize("weak", ["", "a", "a" * 42, "a" * 42 + " ", "é" * 43, "a" * 42 + "/",
                                  "a" * 42 + "\n"])
def test_weak_or_malformed_tokens_are_refused(weak: str) -> None:
    with pytest.raises(ValueError) as err:
        TokenStore(weak)
    assert weak not in str(err.value) or weak == ""  # il token non finisce mai nel messaggio


def test_strong_token_is_accepted() -> None:
    assert TokenStore("A" * 21 + "b-_" + "9" * 19).accepts(("A" * 21 + "b-_" + "9" * 19).encode())


# ------------------------------------------------------------------ 2. rotazioni concorrenti


def test_concurrent_rotation_with_a_failed_write_never_revives_the_old_token(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "api.token"
    t0 = issue_token_file(path)
    store = TokenStore(t0)
    original = tokens_mod._write_exclusive
    gate, first = threading.Event(), threading.Event()
    calls = {"n": 0}

    def slow_write(p: Path, tok: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # rotazione A: si ferma, poi la scrittura fallisce (disco pieno)
            first.set()
            gate.wait(5)
            raise OSError(28, "No space left on device")
        original(p, tok)

    monkeypatch.setattr(tokens_mod, "_write_exclusive", slow_write)
    errors: list[BaseException] = []

    def rotate_a() -> None:
        try:
            store.rotate(path)
        except OSError as exc:
            errors.append(exc)

    a = threading.Thread(target=rotate_a)
    a.start()
    assert first.wait(5)
    b_result: dict[str, str] = {}
    b = threading.Thread(target=lambda: b_result.setdefault("tb", store.rotate(path)))
    b.start()
    time.sleep(0.2)
    gate.set()
    a.join(5)
    b.join(5)
    assert len(errors) == 1
    current = path.read_text()
    assert current == b_result["tb"]
    assert store.accepts(current.encode())      # il token del file è valido
    assert not store.accepts(t0.encode())       # il token revocato non torna mai valido


# ------------------------------------------------------------------ 3. connessioni senza token


def _closed(s: socket.socket, wait: float) -> bool:
    """True se il server ha chiuso la connessione entro `wait` secondi."""
    s.settimeout(wait)
    try:
        return s.recv(1) == b""
    except socket.timeout:
        return False
    except OSError:
        return True


def test_idle_connections_are_bounded_and_expire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_mod, "MAX_CONNECTIONS", 8)
    monkeypatch.setattr(server_mod, "REQUEST_DEADLINE_S", 1.5)
    monkeypatch.setattr(server_mod, "REQUEST_TIMEOUT_S", 30.0)  # solo la scadenza può chiudere le servite
    with control_api(tmp_path) as (server, _s, token_path, providers):
        socks = []
        for _ in range(30):  # slowloris: connessione aperta, mai una richiesta completa
            s = connect(server.port)
            s.sendall(b"GET /v1/status HTTP/1.1\r\n")
            socks.append(s)
        started = time.monotonic()
        time.sleep(0.4)
        early = [s for s in socks if _closed(s, 0.05)]
        held = [s for s in socks if s not in early]
        # oltre il tetto: chiuse subito, senza thread; al più MAX_CONNECTIONS restano servite
        assert len(held) == 8 and len(early) == 22
        assert providers.calls == 0
        # le servite chiudono per la scadenza complessiva (1,5 s), non per il timeout per ricezione (30 s)
        assert all(_closed(s, max(0.1, 1.5 + 1.0 - (time.monotonic() - started))) for s in held)
        assert time.monotonic() - started < 3.5
        for s in socks:
            s.close()
        # dopo la scadenza il servizio risponde di nuovo normalmente
        assert request(server.port, "GET", "/v1/status", token=token_path.read_text())[0] == 200


# ------------------------------------------------------------------ 4. errori della libreria standard


def raw_exchange(port: int, data: bytes) -> bytes:
    s = connect(port)
    try:
        s.sendall(data)
        chunks = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        s.close()


@pytest.mark.parametrize(
    "data",
    [
        b"FOO<script>x</script> /v1/status HTTP/1.1\r\nHost: x\r\n\r\n",
        b"GET /v1/status HTTP/<b>evil</b>\r\nHost: x\r\n\r\n",
        b"GET /" + b"a" * 70000 + b" HTTP/1.1\r\n\r\n",
        b"GET /v1/status HTTP/1.1\r\n" + b"X-Big: " + b"b" * 70000 + b"\r\n\r\n",
        b"GET /v1/status HTTP/2.0\r\n\r\n",
    ],
)
def test_protocol_errors_are_fixed_json_without_echo(tmp_path: Path, data: bytes) -> None:
    with control_api(tmp_path) as (server, _s, _t, providers):
        response = raw_exchange(server.port, data)
    head, _, body = response.partition(b"\r\n\r\n")
    assert b"application/json" in head
    assert body in (b'{"error": {"code": "BAD_REQUEST"}}', b'{"error": {"code": "METHOD_NOT_ALLOWED"}}')
    for echoed in (b"<script>", b"evil", b"aaaa", b"bbbb", b"FOO"):
        assert echoed not in response
    assert providers.calls == 0


def test_client_disconnect_prints_no_traceback(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    with control_api(tmp_path) as (server, _s, token_path, _p):
        for _ in range(5):
            s = connect(server.port)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
            s.sendall(f"GET /v1/status HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
                      f"Authorization: Bearer {token_path.read_text()}\r\n\r\n".encode())
            s.close()  # RST prima di leggere la risposta
        time.sleep(0.5)
    err = capfd.readouterr().err
    assert "Traceback" not in err and "Exception occurred" not in err
