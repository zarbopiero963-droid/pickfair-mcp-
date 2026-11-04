"""Server di prova su 127.0.0.1: Control API reale con provider sostituibili e server ostili."""

from __future__ import annotations

import socket
import socketserver
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from pickfair_control_api.server import ControlApiServer
from pickfair_control_api.tokens import TokenStore, issue_token_file
from tests.control_api import bodies

SHA = "c" * 40


class Providers:
    """Provider sostituibili dai test (il core reale li fornisce tramite il ponte)."""

    def __init__(self) -> None:
        self.status: Callable[[], dict[str, Any]] = bodies.status
        self.reconciliation: Callable[[], dict[str, Any]] = bodies.reconciliation
        self.account: Callable[[], dict[str, Any]] = bodies.account
        self.exposure: Callable[[], dict[str, Any]] = bodies.exposure
        self.calls = 0

    def mapping(self) -> dict[str, Callable[[], dict[str, Any]]]:
        def status() -> dict[str, Any]:
            self.calls += 1
            return self.status()

        def recon() -> dict[str, Any]:
            self.calls += 1
            return self.reconciliation()

        def account() -> dict[str, Any]:
            self.calls += 1
            return self.account()

        def exposure() -> dict[str, Any]:
            self.calls += 1
            return self.exposure()

        return {
            "status": status,
            "reconciliation_status": recon,
            "account": account,
            "exposure": exposure,
        }


def secure_dir(base: Path) -> Path:
    d = base / "pickfair-control-api"
    d.mkdir(mode=0o700, exist_ok=True)
    return d


@contextmanager
def control_api(
    tmp_path: Path, *, port: int = 0, providers: Providers | None = None
) -> Iterator[tuple[ControlApiServer, TokenStore, Path, Providers]]:
    token_path = secure_dir(tmp_path) / "control_api.token"
    if token_path.exists():
        token_path.unlink()
    store = TokenStore(issue_token_file(token_path))
    prov = providers or Providers()
    server = ControlApiServer(
        prov.mapping(), port=port, tokens=store, git_sha=SHA, allow_ephemeral_port=True
    )
    server.start()
    try:
        yield server, store, token_path, prov
    finally:
        server.stop()


@contextmanager
def hostile_http(
    respond: Callable[[BaseHTTPRequestHandler], None],
) -> Iterator[tuple[int, list[str]]]:
    """Server HTTP che risponde come vuole il test; registra i percorsi richiesti."""
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a: Any) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(self.path)
            respond(self)

    class Server(ThreadingHTTPServer):
        def server_bind(self) -> None:  # niente getfqdn (DNS inverso) nei test
            socketserver.TCPServer.server_bind(self)
            self.server_name, self.server_port = "127.0.0.1", int(self.server_address[1])

    httpd = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(httpd.server_address[1]), seen
    finally:
        httpd.shutdown()
        httpd.server_close()


@contextmanager
def silent_server() -> Iterator[int]:
    """Accetta connessioni e non risponde mai (timeout)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept() -> None:
        sock.settimeout(0.1)
        while not stop.is_set():
            try:
                conn, _ = sock.accept()
                held.append(conn)
            except OSError:
                continue

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    try:
        yield int(sock.getsockname()[1])
    finally:
        stop.set()
        thread.join(timeout=2)
        for c in held:
            c.close()
        sock.close()


def free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port
