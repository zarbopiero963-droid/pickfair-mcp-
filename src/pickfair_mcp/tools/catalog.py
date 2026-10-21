"""Catalogo dei nomi tool approvati: un solo set, una route ciascuno.

I 25 nomi coprono le 25 route di pickfair-mcp- #1. Nessun tool per modalità
(niente prefissi sim_/live_), nessun tool per funzionalità sospese o future.
Essere nel catalogo NON significa essere esposto: in MCP-01a è registrato
soltanto `get_meta`.
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Final

APPROVED_TOOL_ROUTES: Final = MappingProxyType(
    {
        "get_meta": "GET /v1/meta",
        "get_status": "GET /v1/status",
        "get_account": "GET /v1/account",
        "get_exposure": "GET /v1/exposure",
        "get_config": "GET /v1/config",
        "list_events": "GET /v1/events",
        "list_markets": "GET /v1/markets",
        "get_market_book": "GET /v1/markets/{id}/book",
        "list_orders": "GET /v1/orders",
        "list_positions": "GET /v1/positions",
        "get_operation": "GET /v1/operations/{id}",
        "list_pending_operations": "GET /v1/operations?status=pending",
        "get_reconciliation_status": "GET /v1/reconciliation/status",
        "get_audit_trail": "GET /v1/audit/{correlation_id}",
        "preview_order": "POST /v1/preview",
        "place_order": "POST /v1/orders",
        "place_dutching": "POST /v1/dutching",
        "cancel_order": "POST /v1/orders/{id}/cancel",
        "replace_order": "POST /v1/orders/{id}/replace",
        "cashout": "POST /v1/cashout",
        "stop": "POST /v1/stop",
        "resume": "POST /v1/resume",
        "reconcile": "POST /v1/reconcile",
        "patch_config": "PATCH /v1/config",
        "set_mode": "POST /v1/mode",
    }
)

# Difesa in profondità: anche se un nome venisse aggiunto per errore al catalogo,
# queste forme restano vietate.
FORBIDDEN_TOOL_NAME_RE: Final = re.compile(
    r"(?i)^(sim|live)_|telegram|copy|mirror|follow|fan_?out|master|strateg|raw|rpc|betfair"
)
TOOL_NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
