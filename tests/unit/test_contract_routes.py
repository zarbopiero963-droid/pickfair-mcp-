"""La tabella delle route è la copia fedele delle 25 route approvate in pickfair-mcp- #1.

L'insieme atteso è scritto qui in modo indipendente dal codice: aggiungere, togliere
o rinominare una route deve far fallire questo test.
"""

from __future__ import annotations

import re

from pickfair_mcp.contract.routes import APPROVED_ROUTES, RouteKind, route_key

EXPECTED_READ = {
    "GET /v1/meta",
    "GET /v1/status",
    "GET /v1/account",
    "GET /v1/exposure",
    "GET /v1/config",
    "GET /v1/events",
    "GET /v1/markets",
    "GET /v1/markets/{id}/book",
    "GET /v1/orders",
    "GET /v1/positions",
    "GET /v1/operations/{id}",
    "GET /v1/operations?status=pending",
    "GET /v1/reconciliation/status",
    "GET /v1/audit/{correlation_id}",
}
EXPECTED_COMMAND = {
    "POST /v1/preview",
    "POST /v1/orders",
    "POST /v1/dutching",
    "POST /v1/orders/{id}/cancel",
    "POST /v1/orders/{id}/replace",
    "POST /v1/cashout",
    "POST /v1/stop",
    "POST /v1/resume",
    "POST /v1/reconcile",
    "PATCH /v1/config",
    "POST /v1/mode",
}


def test_exactly_the_25_approved_routes() -> None:
    reads = {route_key(r) for r in APPROVED_ROUTES if r.kind is RouteKind.READ}
    commands = {route_key(r) for r in APPROVED_ROUTES if r.kind is RouteKind.COMMAND}
    assert reads == EXPECTED_READ
    assert commands == EXPECTED_COMMAND
    assert len(APPROVED_ROUTES) == 25
    assert len({route_key(r) for r in APPROVED_ROUTES}) == 25


def test_read_routes_are_get_and_commands_are_not() -> None:
    for route in APPROVED_ROUTES:
        if route.kind is RouteKind.READ:
            assert route.method == "GET"
        else:
            assert route.method in {"POST", "PATCH"}


FORBIDDEN_ROUTE_PATTERNS = [
    r"^/v1/cashout/.+",  # un solo /v1/cashout, varianti nel body
    r"^/v1/(sim|live)/",  # nessuna route per modalità
    r"telegram|copy|mirror|follow|fan-?out|strateg",  # funzionalità sospese o future
]


def test_no_forbidden_route_shapes() -> None:
    for route in APPROVED_ROUTES:
        for pattern in FORBIDDEN_ROUTE_PATTERNS:
            assert not re.search(pattern, route.path, re.IGNORECASE), route_key(route)


def test_config_is_patch_not_post() -> None:
    keys = {route_key(r) for r in APPROVED_ROUTES}
    assert "PATCH /v1/config" in keys
    assert "POST /v1/config" not in keys
    assert "PUT /v1/config" not in keys


# Testo «Capacità / vincolo» della tabella in pickfair-mcp- #1, copiato alla lettera.
EXPECTED_PURPOSE = {
    "GET /v1/meta": "Version/capabilities/git SHA/schema hash",
    "GET /v1/status": "Runtime/readiness",
    "GET /v1/account": "Account/saldo reale o fittizio secondo contratto; niente secret",
    "GET /v1/exposure": "Esposizione/liability/pending",
    "GET /v1/config": "Config redatta",
    "GET /v1/events": "Eventi per nome",
    "GET /v1/markets": "Mercati/runner per nome",
    "GET /v1/markets/{id}/book": "Book/freshness",
    "GET /v1/orders": "Current/cleared secondo filtro contrattuale, senza route duplicate",
    "GET /v1/positions": "Posizioni pertinenti",
    "GET /v1/operations/{id}": "Async status operation_id",
    "GET /v1/operations?status=pending": "Pending operations",
    "GET /v1/reconciliation/status": "Recovery/readiness",
    "GET /v1/audit/{correlation_id}": "Audit trail redatto",
    "POST /v1/preview": "Zero effetti ordine; schema e business autorevoli",
    "POST /v1/orders": "Place order tramite authority",
    "POST /v1/dutching": "Dutching tramite authority",
    "POST /v1/orders/{id}/cancel": "Cancel pertinente",
    "POST /v1/orders/{id}/replace": "Replace, no retry cieco",
    "POST /v1/cashout": (
        "target/selection/market/all/fraction/percentage/Void/intent/lifecycle nel body"
    ),
    "POST /v1/stop": "PAUSE/STOP/RISK_STOP/EMERGENCY secondo schema runtime",
    "POST /v1/resume": "Nuova readiness completa",
    "POST /v1/reconcile": "Via runtime, non secondo reconciler",
    "PATCH /v1/config": (
        "Config patch via contract; non POST config né MM/risk endpoint paralleli"
    ),
    "POST /v1/mode": "Switch SOLO su comando owner, tutti i gate restano",
}


def test_route_purposes_are_verbatim_copies_of_issue_1() -> None:
    assert {route_key(r): r.purpose for r in APPROVED_ROUTES} == EXPECTED_PURPOSE
