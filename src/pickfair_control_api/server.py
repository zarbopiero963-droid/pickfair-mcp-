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
- corpi d'errore fissi, anche per gli errori di protocollo della libreria standard (mai l'eco dell'input);
  nessun log né traceback per richiesta; token mai nei log;
- risorse limitate per chiunque, anche senza token: al più ``MAX_CONNECTIONS`` connessioni servite insieme,
  ognuna chiusa entro ``REQUEST_DEADLINE_S`` (MCP-SEC-01);
- MCP-01o (PF-BLACKBOX-01): l'unica query string ammessa è quella di ``/v1/blackbox/events``, in
whitelist
  chiusa (``blackbox_query``); ogni richiesta è registrata nella scatola nera tramite
  ``request_hook``
  (una volta per richiesta, mai per evento letto). Una richiesta accettata che non si può
  registrare
  riceve ``503 BLACKBOX_UNAVAILABLE``, tranne ``/v1/blackbox/status``; oltre ``RECORD_RATE_PER_S``
  le
  registrazioni si aggregano in un conteggio (``coalesced_before``) portato dal record successivo.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import socketserver
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Final

from pickfair_control_api.blackbox_query import QueryRejected, parse_events_query
from pickfair_control_api.blackbox_redact import redact_response
from pickfair_control_api.contract import (
    BLACKBOX_STATUS_ROUTE,
    CAPABILITIES,
    CONTRACT_VERSION,
    GIT_SHA_RE,
    PARAM_ROUTE_PATTERNS,
    PARAM_ROUTE_SCHEMAS,
    PROVIDER_NAMES,
    QUERY_ROUTE_SCHEMAS,
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
# MCP-SEC-01: risorse limitate anche per client senza token (slowloris). Al più MAX_CONNECTIONS connessioni
# servite insieme (le altre chiuse subito, nessun thread); ogni connessione chiusa entro REQUEST_DEADLINE_S
# dall'accettazione, qualunque sia il ritmo con cui il client invia i byte.
MAX_CONNECTIONS = 16  # ogni connessione servita usa due thread (gestore + timer della scadenza)
REQUEST_DEADLINE_S = 10.0
# Errori di protocollo della libreria standard (riga di richiesta, versione, URI o header troppo lunghi):
# corpo JSON fisso, mai l'eco dell'input. Un metodo sconosciuto è METHOD_NOT_ALLOWED come gli altri.
_PROTOCOL_ERRORS: Final = {501: (405, "METHOD_NOT_ALLOWED")}
MAX_RESPONSE_BYTES: Final = 64 * 1024
SHUTDOWN_POLL_S: Final = 0.1  # arresto rapido: stop() attende al più un ciclo
Provider = Callable[[], dict[str, Any]]
ParamProvider = Callable[[str], dict[str, Any]]
QueryProvider = Callable[[dict[str, object]], dict[str, Any]]
# MCP-01o: hook del ponte che scrive un record nella scatola nera; True solo se il record è stato
# accettato.
RequestHook = Callable[[dict[str, Any]], bool]
REQUEST_ID_RE: Final = re.compile(r"[A-Za-z0-9-]{8,64}")
RECORD_RATE_PER_S: Final = 20.0
RECORD_BURST: Final = 40.0


def _public_params(filters: dict[str, object]) -> dict[str, object]:
    """Filtri già validati in forma serializzabile per il record (nessun valore grezzo)."""
    out: dict[str, object] = {}
    for name, value in sorted(filters.items()):
        if isinstance(value, datetime):
            out[name] = value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"
        else:
            out[name] = value
    return out


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
        # Scadenza complessiva della connessione: il timeout del socket vale per ogni singola ricezione,
        # un client lento lo rinnoverebbe all'infinito.
        self._deadline = threading.Timer(REQUEST_DEADLINE_S, self._expire)
        self._deadline.daemon = True
        self._deadline.start()

    def _expire(self) -> None:
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def finish(self) -> None:
        self._deadline.cancel()
        try:
            super().finish()
        except OSError:
            pass  # client già disconnesso: nessun traceback

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """Errori di protocollo della libreria standard: JSON fisso, mai il testo ricevuto."""
        status, error = _PROTOCOL_ERRORS.get(code, (400, "BAD_REQUEST"))
        try:
            self._error(status, error)
        except OSError:
            self.close_connection = True

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
        self._record_result(status, code)

    def _record(self, phase: str, status: int | None, code: str | None) -> None:
        """Un record per fase; un fallimento conta la richiesta UNA volta come non registrata."""
        started = getattr(self, "_started", None)
        record = {
            "phase": phase,
            "route": getattr(self, "_route", None),
            "params": getattr(self, "_params", None),
            "request_id": getattr(self, "_request_id", None),
            "status": status,
            "code": code,
            "duration_ms": None if started is None else int((time.monotonic() - started) * 1000),
        }
        if not self.server.app.record(record):
            self._mark_unrecorded()

    def _record_result(self, status: int, code: str) -> None:
        self._record("RESULT", status, code)

    def _mark_unrecorded(self) -> None:
        if not getattr(self, "_unrecorded", False):
            self._unrecorded = True
            self.server.app.add_unrecorded(1)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        presented = header[len("Bearer ") :].encode("utf-8", "surrogateescape")
        return self.server.app.tokens.accepts(presented)

    def do_GET(self) -> None:
        app = self.server.app
        self._started = time.monotonic()
        if self.headers.get("Host") != app.expected_host:
            return self._error(400, "BAD_HOST")
        if not self._authorized():
            return self._error(401, "UNAUTHORIZED")
        length = self.headers.get("Content-Length")
        if self.headers.get("Transfer-Encoding") or (length not in (None, "0")):
            return self._error(400, "BODY_NOT_ALLOWED")
        request_id = self.headers.get("X-Request-Id")
        if request_id is not None:
            if not REQUEST_ID_RE.fullmatch(request_id):
                return self._error(400, "BAD_REQUEST")
            self._request_id = request_id
        # Percorso grezzo: http.server normalizza «//x» in «/x»; il contratto vuole quello esatto.
        parts = self.requestline.split(" ")
        raw_path = parts[1] if len(parts) == 3 else ""
        exact = raw_path == self.path
        route = raw_path if exact and raw_path in app.routes else None
        read: Callable[[], dict[str, Any]] | None = app.routes.get(route) if route else None
        schema_name = ROUTE_SCHEMAS.get(route) if route else None
        path_part, _sep, query = raw_path.partition("?")
        if route is None and path_part in QUERY_ROUTE_SCHEMAS:
            self._route = path_part
            try:
                filters = parse_events_query(query)
            except QueryRejected as exc:
                return self._error(400, str(exc))
            query_provider = app.query_routes[path_part]
            route, schema_name = path_part, QUERY_ROUTE_SCHEMAS[path_part]
            self._params = _public_params(filters)
            read = lambda: query_provider(filters)  # noqa: E731
        if route is None and exact:
            for template, pattern in PARAM_ROUTE_PATTERNS.items():
                match = pattern.fullmatch(raw_path)
                if match:
                    value = match.group("id")
                    provider = app.param_routes[template]
                    route, schema_name = template, PARAM_ROUTE_SCHEMAS[template]
                    self._params = {"id": value}
                    read = lambda: provider(value)  # noqa: E731
                    break
        if route is None or read is None or schema_name is None:
            if exact and any(p.fullmatch(raw_path) for p in unserved_read_routes()):
                return self._error(501, "NOT_IMPLEMENTED")
            return self._error(404, "NOT_FOUND")
        self._route = route
        # Registra o rifiuta: senza un record della richiesta nessun dato esce, tranne lo stato del
        # registro, che serve proprio a vedere il guasto.
        attempt = {
            "phase": "ATTEMPT", "route": route, "params": getattr(self, "_params", None),
            "request_id": getattr(self, "_request_id", None), "status": None, "code": None,
            "duration_ms": None,
        }
        if not app.record(attempt):
            self._mark_unrecorded()
            if route != BLACKBOX_STATUS_ROUTE:
                return self._error(503, "BLACKBOX_UNAVAILABLE")
        try:
            body = read()
        except Exception:  # noqa: BLE001 - mai testo di eccezione verso il client
            logger.error("control_api: lettura fallita (%s)", route)
            return self._error(500, "INTERNAL")
        if schema_name in ("blackbox_events", "blackbox_event"):
            # Seconda redazione: mai un valore sensibile verso il client.
            body = redact_response(body)
        if route == BLACKBOX_STATUS_ROUTE and isinstance(body, dict):
            # Conteggio noto solo al server: richieste servite o rifiutate senza un record.
            body = {**body, "requests_unrecorded": app.unrecorded_count()}
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
        self._record_result(200, "OK")

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
        query_routes: dict[str, QueryProvider] | None = None,
        request_hook: RequestHook | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.routes = routes
        self.param_routes = param_routes or {}
        self.query_routes = query_routes or {}
        self.tokens = tokens
        self.expected_host = f"{LOOPBACK_HOST}:{port}"
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()
        self._hook = request_hook
        self._clock = clock
        self._budget = RECORD_BURST
        self._budget_at = clock()
        self._coalesced = 0
        self._unrecorded = 0

    def record(self, record: dict[str, Any]) -> bool:
        """Scrive un record tramite l'hook; oltre il ritmo massimo lo conta senza scriverlo
        (aggregazione).

        True se il record è stato accettato dall'hook oppure contato per l'aggregazione; False se
        l'hook lo
        rifiuta o fallisce (i conteggi aggregati che portava diventano non registrati)."""
        with self._lock:
            now = self._clock()
            refill = (now - self._budget_at) * RECORD_RATE_PER_S
            self._budget = min(RECORD_BURST, self._budget + refill)
            self._budget_at = now
            if self._budget < 1.0:
                self._coalesced += 1
                return True
            self._budget -= 1.0
            carried, self._coalesced = self._coalesced, 0
        hook = self._hook
        try:
            ok = hook is not None and hook({**record, "coalesced_before": carried}) is True
        except Exception:  # noqa: BLE001 - un guasto del registro non fa cadere il server
            ok = False
        if not ok and carried:
            self.add_unrecorded(carried)
        return ok

    def add_unrecorded(self, n: int) -> None:
        with self._lock:
            self._unrecorded += n

    def unrecorded_count(self) -> int:
        with self._lock:
            return min(self._unrecorded, 1_000_000)

    def count(self, code: str) -> None:
        with self._lock:
            self._counts[code] = self._counts.get(code, 0) + 1

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    _slots: threading.BoundedSemaphore

    def process_request(self, request: Any, client_address: Any) -> None:
        """Connessione oltre MAX_CONNECTIONS: chiusa subito, nessun thread (MCP-SEC-01)."""
        if not self._slots.acquire(blocking=False):
            self.app.count("BUSY")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Nessun traceback su stderr per richiesta (un client disconnesso non riempie i log)."""
        logger.debug("control_api: connessione chiusa con errore")
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
        request_hook: RequestHook | None = None,
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
        if not callable(request_hook):
            # PF-BLACKBOX-01: ogni richiesta va registrata; senza hook il server non parte.
            raise ControlApiConfigError("REQUEST_HOOK_REQUIRED")
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
        self._httpd._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.port = int(self._httpd.server_address[1])
        param_routes: dict[str, ParamProvider] = {
            template: providers[name] for template, name in PARAM_ROUTE_SCHEMAS.items()
        }
        query_routes: dict[str, QueryProvider] = {
            template: providers[name] for template, name in QUERY_ROUTE_SCHEMAS.items()
        }
        self._httpd.app = _App(routes, tokens, self.port, param_routes, query_routes, request_hook)
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
