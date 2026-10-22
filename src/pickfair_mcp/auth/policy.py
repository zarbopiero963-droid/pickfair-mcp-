"""Mappa statica tool → scope minimo e decisione di autorizzazione (fail-closed).

Lo scope dipende solo dal nome del tool (e da un qualificatore dichiarato dal
codice, es. il livello EMERGENCY di `stop`), mai dal contenuto della richiesta
né da testo upstream.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from pickfair_mcp.auth.principal import Principal, Scope, principal_is_valid
from pickfair_mcp.errors import ErrorCode, ToolError

TOOL_SCOPES: Final = MappingProxyType(
    {
        "get_meta": Scope.READ,
        "get_status": Scope.READ,
        "get_account": Scope.READ,
        "get_exposure": Scope.READ,
        "get_config": Scope.READ,
        "list_events": Scope.READ,
        "list_markets": Scope.READ,
        "get_market_book": Scope.READ,
        "list_orders": Scope.READ,
        "list_positions": Scope.READ,
        "get_operation": Scope.READ,
        "list_pending_operations": Scope.READ,
        "get_reconciliation_status": Scope.READ,
        "get_audit_trail": Scope.READ,
        "preview_order": Scope.WRITE,
        "place_order": Scope.WRITE,
        "place_dutching": Scope.WRITE,
        "cancel_order": Scope.WRITE,
        "replace_order": Scope.WRITE,
        "cashout": Scope.WRITE,
        "stop": Scope.WRITE,
        "resume": Scope.WRITE,
        "reconcile": Scope.WRITE,
        "patch_config": Scope.OWNER,
        "set_mode": Scope.OWNER,
    }
)

OWNER_ONLY_TOOLS: Final = frozenset({"set_mode", "patch_config"})
# Operazioni owner-only identificate da (tool, qualificatore) dichiarato dal codice.
OWNER_ONLY_QUALIFIED: Final = frozenset({("stop", "EMERGENCY")})


class AuthorizationDenied(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def to_tool_error(self) -> ToolError:
        return ToolError(ErrorCode.FORBIDDEN, reasons=(self.reason,))


def required_scope(tool: str, *, qualifier: str | None = None) -> Scope:
    scope = TOOL_SCOPES.get(tool)
    if scope is None:
        raise AuthorizationDenied("SCOPE_UNDECLARED")
    if (tool, qualifier) in OWNER_ONLY_QUALIFIED:
        return Scope.OWNER
    return scope


def authorize(principal: Principal | None, tool: str, *, qualifier: str | None = None) -> None:
    """Solleva AuthorizationDenied se il principal non possiede lo scope richiesto."""
    if principal is None:
        raise AuthorizationDenied("PRINCIPAL_MISSING")
    if type(principal) is not Principal or not principal_is_valid(
        principal.principal_id, principal.scopes
    ):
        raise AuthorizationDenied("PRINCIPAL_INVALID")
    if required_scope(tool, qualifier=qualifier) not in principal.scopes:
        raise AuthorizationDenied("SCOPE_MISSING")
