"""Interfaccia dell'adapter verso la Control API.

L'adapter trasporta byte: non interpreta, non calcola e non decide nulla di
finanziario. Il parsing e la validazione avvengono nel livello contract.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

AdapterKind = Literal["simulated", "http"]


class UpstreamTimeout(Exception):
    """La Control API non ha risposto entro il tempo previsto."""


class UpstreamUnavailable(Exception):
    """La Control API non è raggiungibile o ha chiuso la connessione."""


class UpstreamUnauthorized(Exception):
    """La Control API ha rifiutato le credenziali dell'adapter, anche dopo la rilettura."""


class UpstreamNotImplemented(Exception):
    """La Control API dichiara la route approvata ma non ancora servita (501 NOT_IMPLEMENTED)."""


class UpstreamProtocolError(Exception):
    """Risposta HTTP fuori protocollo (status, redirect, content-type); `reason` è fisso."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@runtime_checkable
class ControlApiAdapter(Protocol):
    @property
    def kind(self) -> AdapterKind:
        """Tipo di adapter, esposto ai client: «simulated» non è mai il core reale."""
        ...

    @property
    def certified(self) -> bool:
        """True solo per un collegamento certificato al core. Sempre False in MCP-01a."""
        ...

    @property
    def connection_epoch(self) -> int:
        """Cresce a ogni (ri)connessione: un nuovo epoch invalida l'handshake."""
        ...

    async def get_meta_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/meta."""
        ...

    async def get_status_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/status (MCP-02a)."""
        ...

    async def get_reconciliation_status_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/reconciliation/status (MCP-02a)."""
        ...

    async def get_account_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/account (MCP-01e)."""
        ...

    async def get_exposure_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/exposure (MCP-01e)."""
        ...

    async def get_positions_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/positions (MCP-01f)."""
        ...

    async def get_orders_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/orders (MCP-01g)."""
        ...

    async def get_config_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/config (MCP-01j, impostazioni redatte)."""
        ...

    async def get_markets_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/markets (MCP-01l)."""
        ...

    async def get_market_book_raw(self, market_id: str) -> bytes:
        """Corpo grezzo di GET /v1/markets/{id}/book (MCP-01l); `market_id` già validato dal tool."""
        ...

    async def get_blackbox_status_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/blackbox/status (MCP-01o, PF-BLACKBOX-01)."""
        ...

    async def get_blackbox_sessions_raw(self) -> bytes:
        """Corpo grezzo di GET /v1/blackbox/sessions (MCP-01o)."""
        ...

    async def get_blackbox_events_raw(self, query: tuple[tuple[str, str], ...]) -> bytes:
        """Corpo grezzo di GET /v1/blackbox/events (MCP-01o); `query` già validata dal tool."""
        ...

    async def get_blackbox_event_raw(self, event_id: str) -> bytes:
        """Corpo grezzo di GET /v1/blackbox/events/{event_id} (MCP-01o); `event_id` già validato."""
        ...
