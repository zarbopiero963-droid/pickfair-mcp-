"""Server HTTP della Control API v1 — sola lettura, solo loopback, autenticato, auto-verificato.

Il server non conosce il motore: riceve dal core un *provider* di sola lettura per ogni route
servita (``contract.PROVIDER_NAMES``: status, reconciliation_status, account, exposure) che
restituisce un dict. Il ponte che li implementa
sul ``RuntimeController`` appartiene al repository Pickfair-nogui (handoff a Claude B).

Regole:
- bind solo su ``127.0.0.1`` con porta esplicita (0 solo con ``allow_ephemeral_port``);
- ``Authorization: Bearer <token>`` (TokenStore, tempo costante) e ``Host: 127.0.0.1:<porta>``;
- solo GET esatti sulle route di ``contract.ROUTE_SCHEMAS``, senza query né corpo; le route con un
  parametro (``contract.PARAM_ROUTE_SCHEMAS``, MCP-01l) solo se il parametro rispetta il suo pattern
  stretto (altrimenti 404) e il provider riceve il valore già validato;
- una route di lettura approvata ma non servita risponde ``501 NOT_IMPLEMENTED`` (mai un dato);
  un percorso fuori contratto ``404 NOT_FOUND``; ogni metodo diverso da GET ``405``;
- ogni risposta è validata contro lo schema del contratto PRIMA dell'invio: una risposta fuori
  contratto diventa ``500 CONTRACT_SELF_CHECK``, mai un dato apparentemente valido;
- corpi d'errore fissi; nessun log per richiesta; token mai nei log.
"""

from __future__ import annotations

import json
import logging
import os
import socketserver
import threading
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Final

from pickfair_control_api.contract import (
    CAPABILITIES,
    CONTRACT_VERSION,
    GIT_SHA_RE,
    PARAM_ROUTE_PATTERNS,
    PARAM_ROUTE_SCHEMAS,
    PROVIDER_NAMES,
    ROUTE_SCHEMAS,
    response_schema,
    schema_hash,
    unserved_read_routes,
)
from pickfair_control_api.schema_check import SchemaUnsupported, SchemaViolation, validate
from pickfair_control_api.tokens import TokenStore

logger = logging.getLogger(__name__)

LOOPBACK_HOST: Final = "127.0.0.1"
MIN_TOKEN_CHARS: Final = 43
REQUEST_TIMEOUT_S: Final = 5.0
MAX_RESPONSE_BYTES: Final = 64 * 1024
SHUTDOWN_POLL_S: Final = 0.1  # arresto rapido: stop() attende al più un ciclo
Provider = Callable[[], dict[str, Any]]
ParamProvider = Callable[[str], dict[str, Any]]


class ControlApiConfigError(Exception):
    """Configurazione non sicura o incompleta: il server non parte."""


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    protocol_version = "HTTP/1.1"
    server_version = "pickfair-control-api"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_S)

    def log_message(self, format: str, *args: Any) -> None:
        """Nessun log per richiesta: percorso e header non escono."""

    def _send(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body, sort_keys=True, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def _error(self, status: int, code: str) -> None:
        self.server.app.count(code)
        self._send(status, {"error": {"code": code}})

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        presented = header[len("Bearer ") :].encode("utf-8", "surrogateescape")
        return self.server.app.tokens.accepts(presented)

    def do_GET(self) -> None:
        app = self.server.app
        if self.headers.get("Host") != app.expected_host:
            return self._error(400, "BAD_HOST")
        if not self._authorized():
            return self._error(401, "UNAUTHORIZED")
        length = self.headers.get("Content-Length")
        if self.headers.get("Transfer-Encoding") or (length not in (None, "0")):
            return self._error(400, "BODY_NOT_ALLOWED")
        # Percorso grezzo: http.server normalizza «//x» in «/x»; il contratto vuole quello esatto.
        parts = self.requestline.split(" ")
        raw_path = parts[1] if len(parts) == 3 else ""
        exact = raw_path == self.path
        route = raw_path if exact and raw_path in app.routes else None
        read: Callable[[], dict[str, Any]] | None = app.routes.get(route) if route else None
        schema_name = ROUTE_SCHEMAS.get(route) if route else None
        if route is None and exact:
            for template, pattern in PARAM_ROUTE_PATTERNS.items():
                match = pattern.fullmatch(raw_path)
                if match:
                    value = match.group("id")
                    provider = app.param_routes[template]
                    route, schema_name = template, PARAM_ROUTE_SCHEMAS[template]
                    read = lambda: provider(value)  # noqa: E731
                    break
        if route is None or read is None or schema_name is None:
            if exact and any(p.fullmatch(raw_path) for p in unserved_read_routes()):
                return self._error(501, "NOT_IMPLEMENTED")
            return self._error(404, "NOT_FOUND")
        try:
            body = read()
        except Exception:  # noqa: BLE001 - mai testo di eccezione verso il client
            logger.error("control_api: lettura fallita (%s)", route)
            return self._error(500, "INTERNAL")
        try:
            validate(body, response_schema(schema_name))
            size = len(json.dumps(body, sort_keys=True, allow_nan=False).encode("utf-8"))
        except (SchemaViolation, SchemaUnsupported, ValueError, TypeError):
            logger.error("control_api: risposta fuori contratto (%s)", route)
            return self._error(500, "CONTRACT_SELF_CHECK")
        if size > MAX_RESPONSE_BYTES:
            return self._error(500, "CONTRACT_SELF_CHECK")
        app.count("OK")
        self._send(200, body)

    def _method_not_allowed(self) -> None:
        self._error(405, "METHOD_NOT_ALLOWED")

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = _method_not_allowed


class _App:
    def __init__(
        self,
        routes: dict[str, Provider],
        tokens: TokenStore,
        port: int,
        param_routes: dict[str, ParamProvider] | None = None,
    ) -> None:
        self.routes = routes
        self.param_routes = param_routes or {}
        self.tokens = tokens
        self.expected_host = f"{LOOPBACK_HOST}:{port}"
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def count(self, code: str) -> None:
        with self._lock:
            self._counts[code] = self._counts.get(code, 0) + 1

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Il server chiude le connessioni: senza SO_REUSEADDR un riavvio sulla stessa porta
    # fallirebbe per TIME_WAIT (~60 s). Su Linux SO_REUSEADDR NON permette due server in
    # ascolto sulla stessa porta. Su Windows resterebbe possibile il dirottamento: disattivato.
    allow_reuse_address = os.name == "posix"
    app: _App

    def server_bind(self) -> None:
        # HTTPServer.server_bind chiama socket.getfqdn(): una risoluzione DNS inversa a ogni
        # avvio. La Control API non risolve nomi: bind TCP puro e nome = IP letterale.
        socketserver.TCPServer.server_bind(self)
        self.server_name = LOOPBACK_HOST
        self.server_port = int(self.server_address[1])


class ControlApiServer:
    """Control API v1 di sola lettura sopra provider forniti dal core."""

    def __init__(
        self,
        providers: Mapping[str, Callable[..., dict[str, Any]]],
        *,
        port: int,
        tokens: TokenStore,
        git_sha: str,
        host: str = LOOPBACK_HOST,
        allow_ephemeral_port: bool = False,
    ) -> None:
        if host != LOOPBACK_HOST:
            raise ControlApiConfigError("HOST_NOT_LOOPBACK_LITERAL")
        if (
            type(port) is not int
            or not (0 <= port <= 65535)
            or (port == 0 and not allow_ephemeral_port)
        ):
            raise ControlApiConfigError("PORT_NOT_EXPLICIT")
        if not isinstance(tokens, TokenStore):
            raise ControlApiConfigError("TOKEN_STORE_REQUIRED")
        if not isinstance(git_sha, str) or not GIT_SHA_RE.fullmatch(git_sha):
            raise ControlApiConfigError("GIT_SHA_INVALID")
        if set(providers) != PROVIDER_NAMES or not all(callable(p) for p in providers.values()):
            raise ControlApiConfigError("PROVIDERS_INVALID")
        meta = {
            "contract_version": CONTRACT_VERSION,
            "capabilities": list(CAPABILITIES),
            "git_sha": git_sha,
            "schema_hash": schema_hash(),
        }
        routes: dict[str, Provider] = {
            path: (lambda: dict(meta)) if name == "meta" else providers[name]
            for path, name in ROUTE_SCHEMAS.items()
        }
        self._httpd = _Server((host, port), _Handler, bind_and_activate=True)
        self.port = int(self._httpd.server_address[1])
        param_routes: dict[str, ParamProvider] = {
            template: providers[name] for template, name in PARAM_ROUTE_SCHEMAS.items()
        }
        self._httpd.app = _App(routes, tokens, self.port, param_routes)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def base_url(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.port}"

    def request_counts(self) -> dict[str, int]:
        return self._httpd.app.counts()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._httpd.serve_forever,
                kwargs={"poll_interval": SHUTDOWN_POLL_S},
                name="control-api",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread, self._thread = self._thread, None
        if thread is not None:
            self._httpd.shutdown()
            thread.join(timeout=5)
        self._httpd.server_close()

    def __enter__(self) -> ControlApiServer:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()
