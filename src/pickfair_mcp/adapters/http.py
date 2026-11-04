"""Adapter HTTP di prodotto verso la Control API (MCP-01d).

UNICO modulo del pacchetto autorizzato a importare moduli di rete (`http.client`, `socket`):
l'eccezione è circoscritta da `tests/guards/test_no_bypass.py` a questo file e a questi due
moduli. Proprietà, ciascuna verificata dai test:

- destinazione fissa: IPv4 letterale 127.0.0.1, porta dalla sola configurazione locale (CLI);
- nessuna risoluzione di nomi: il socket AF_INET si connette direttamente all'indirizzo
  (niente `getaddrinfo`, niente DNS);
- nessun proxy (http.client non legge le variabili d'ambiente) e nessun redirect (un 3xx è
  un errore di protocollo, mai seguito);
- autenticazione Bearer obbligatoria letta dal file del token verificato (`auth.token_file`);
  su 401 il token viene riletto UNA volta (rotazione) e la richiesta ripetuta UNA volta;
- timeout espliciti su connessione e lettura; corpo letto al massimo fino al limite + 1 byte;
- status diverso da 200 o content-type diverso da JSON UTF-8 => errore tipizzato;
- ogni guasto di trasporto, 401 o rilettura del token incrementa `connection_epoch`: il
  prossimo uso ripete l'handshake di contratto;
- nessun fallback verso l'adapter simulato: l'errore arriva al client come tale.

Solo GET di lettura: questo adapter non ha metodi di comando.
"""

from __future__ import annotations

import http.client
import socket
import threading
from typing import Final

import anyio

from pickfair_mcp.adapters.base import (
    AdapterKind,
    UpstreamNotImplemented,
    UpstreamProtocolError,
    UpstreamTimeout,
    UpstreamUnauthorized,
    UpstreamUnavailable,
)
from pickfair_mcp.auth.token_file import LocalTokenFile, TokenFileError
from pickfair_mcp.contract.parsing import MAX_UPSTREAM_BYTES

LOOPBACK_HOST: Final = "127.0.0.1"
EXPECTED_CONTENT_TYPE: Final = "application/json; charset=utf-8"


def validate_port(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError("CONFIG_PORT")
    return value


class _LoopbackConnection(http.client.HTTPConnection):
    """Connessione verso 127.0.0.1 senza risoluzione di nomi e senza tunnel/proxy."""

    def __init__(self, port: int, timeout: float) -> None:
        super().__init__(LOOPBACK_HOST, port, timeout=timeout)

    def connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect((LOOPBACK_HOST, self.port))
        except BaseException:
            sock.close()
            raise
        self.sock = sock


class HttpControlApiAdapter:
    def __init__(
        self,
        *,
        port: int,
        token_file: LocalTokenFile,
        timeout_s: float,
        max_response_bytes: int = MAX_UPSTREAM_BYTES,
    ) -> None:
        self._port = validate_port(port)
        self._token_file = token_file
        self._timeout_s = float(timeout_s)
        self._max = int(max_response_bytes)
        self._lock = threading.Lock()
        self._epoch = 1
        self._token: str | None = None
        self.requests = 0

    @property
    def kind(self) -> AdapterKind:
        return "http"

    @property
    def certified(self) -> bool:
        # Diventa True solo con una decisione di certificazione (MCP-07b), mai da codice.
        return False

    @property
    def connection_epoch(self) -> int:
        with self._lock:
            return self._epoch

    def _bump(self) -> None:
        with self._lock:
            self._epoch += 1

    def _current_token(self, *, reload: bool) -> str:
        with self._lock:
            if reload or self._token is None:
                try:
                    self._token = self._token_file.read()
                except TokenFileError:
                    self._token = None
                    raise UpstreamUnauthorized from None
            return self._token

    def _request(self, path: str, token: str) -> tuple[int, str, bytes]:
        conn = _LoopbackConnection(self._port, self._timeout_s)
        try:
            conn.request(
                "GET",
                path,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            resp = conn.getresponse()
            body = resp.read(self._max + 1)
            return resp.status, resp.getheader("Content-Type", ""), body
        except TimeoutError:
            self._bump()
            raise UpstreamTimeout from None
        except (OSError, http.client.HTTPException):
            self._bump()
            raise UpstreamUnavailable from None
        finally:
            conn.close()

    def _get_blocking(self, path: str) -> bytes:
        self.requests += 1
        status, content_type, body = self._request(path, self._current_token(reload=False))
        if status == 401:
            # Rotazione: rilettura del token e un solo nuovo tentativo, poi fail-closed.
            self._bump()
            status, content_type, body = self._request(path, self._current_token(reload=True))
            if status == 401:
                raise UpstreamUnauthorized
        if status == 501:
            raise UpstreamNotImplemented
        if status != 200:
            raise UpstreamProtocolError(f"HTTP_{status}")
        if content_type != EXPECTED_CONTENT_TYPE:
            raise UpstreamProtocolError("CONTENT_TYPE")
        return body

    async def _get(self, path: str) -> bytes:
        return await anyio.to_thread.run_sync(self._get_blocking, path, abandon_on_cancel=True)

    async def get_meta_raw(self) -> bytes:
        return await self._get("/v1/meta")

    async def get_status_raw(self) -> bytes:
        return await self._get("/v1/status")

    async def get_reconciliation_status_raw(self) -> bytes:
        return await self._get("/v1/reconciliation/status")

    async def get_account_raw(self) -> bytes:
        return await self._get("/v1/account")

    async def get_exposure_raw(self) -> bytes:
        return await self._get("/v1/exposure")
