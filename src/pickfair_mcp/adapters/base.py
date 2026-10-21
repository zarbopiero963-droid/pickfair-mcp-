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
