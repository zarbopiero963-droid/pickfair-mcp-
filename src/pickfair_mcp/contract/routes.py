"""Tabella unica delle route Control API v1 approvate (pickfair-mcp- #1).

Copia fedele delle 25 route approvate (14 di lettura e 11 comandi) più le 4 route di
SOLA LETTURA della scatola nera ratificate dalla decisione owner PF-BLACKBOX-01 del
08/11/2026: 29 in tutto, 18 di lettura. Nessuna route oltre queste può essere introdotta
senza una nuova decisione owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RouteKind(Enum):
    READ = "read"
    COMMAND = "command"


@dataclass(frozen=True, slots=True)
class Route:
    kind: RouteKind
    method: str
    path: str
    purpose: str


def route_key(route: Route) -> str:
    """Identificatore canonico «METODO path» usato anche come capability."""
    return f"{route.method} {route.path}"


_R = RouteKind.READ
_C = RouteKind.COMMAND

APPROVED_ROUTES: tuple[Route, ...] = (
    Route(_R, "GET", "/v1/meta", "Version/capabilities/git SHA/schema hash"),
    Route(_R, "GET", "/v1/status", "Runtime/readiness"),
    Route(
        _R, "GET", "/v1/account", "Account/saldo reale o fittizio secondo contratto; niente secret"
    ),
    Route(_R, "GET", "/v1/exposure", "Esposizione/liability/pending"),
    Route(_R, "GET", "/v1/config", "Config redatta"),
    Route(_R, "GET", "/v1/events", "Eventi per nome"),
    Route(_R, "GET", "/v1/markets", "Mercati/runner per nome"),
    Route(_R, "GET", "/v1/markets/{id}/book", "Book/freshness"),
    Route(
        _R,
        "GET",
        "/v1/orders",
        "Current/cleared secondo filtro contrattuale, senza route duplicate",
    ),
    Route(_R, "GET", "/v1/positions", "Posizioni pertinenti"),
    Route(_R, "GET", "/v1/operations/{id}", "Async status operation_id"),
    Route(_R, "GET", "/v1/operations?status=pending", "Pending operations"),
    Route(_R, "GET", "/v1/reconciliation/status", "Recovery/readiness"),
    Route(_R, "GET", "/v1/audit/{correlation_id}", "Audit trail redatto"),
    # PF-BLACKBOX-01 (owner, 08/11/2026): lettura della scatola nera, mai scrittura.
    Route(_R, "GET", "/v1/blackbox/status", "Stato del registro cronologico, lacune, integrità"),
    Route(_R, "GET", "/v1/blackbox/sessions", "Sessioni di avvio registrate"),
    Route(_R, "GET", "/v1/blackbox/events", "Eventi per seq con filtri in whitelist chiusa"),
    Route(_R, "GET", "/v1/blackbox/events/{event_id}", "Un evento e la sua catena causale"),
    Route(_C, "POST", "/v1/preview", "Zero effetti ordine; schema e business autorevoli"),
    Route(_C, "POST", "/v1/orders", "Place order tramite authority"),
    Route(_C, "POST", "/v1/dutching", "Dutching tramite authority"),
    Route(_C, "POST", "/v1/orders/{id}/cancel", "Cancel pertinente"),
    Route(_C, "POST", "/v1/orders/{id}/replace", "Replace, no retry cieco"),
    Route(
        _C,
        "POST",
        "/v1/cashout",
        "target/selection/market/all/fraction/percentage/Void/intent/lifecycle nel body",
    ),
    Route(_C, "POST", "/v1/stop", "PAUSE/STOP/RISK_STOP/EMERGENCY secondo schema runtime"),
    Route(_C, "POST", "/v1/resume", "Nuova readiness completa"),
    Route(_C, "POST", "/v1/reconcile", "Via runtime, non secondo reconciler"),
    Route(
        _C,
        "PATCH",
        "/v1/config",
        "Config patch via contract; non POST config né MM/risk endpoint paralleli",
    ),
    Route(_C, "POST", "/v1/mode", "Switch SOLO su comando owner, tutti i gate restano"),
)

ROUTES_BY_KEY: dict[str, Route] = {route_key(r): r for r in APPROVED_ROUTES}
