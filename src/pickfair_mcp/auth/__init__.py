"""Autorizzazione MCP (MCP-01c): principal, scope e mappa statica tool → scope.

L'autorizzazione MCP è un filtro aggiuntivo: non sostituisce i controlli del core
Pickfair/Roserpina, unica autorità finanziaria. Il modello di autenticazione
MCP ↔ Control API (decisione D-11) resta aperto e va allineato in MCP-01d.
"""

from __future__ import annotations

from pickfair_mcp.auth.policy import (
    OWNER_ONLY_QUALIFIED,
    OWNER_ONLY_TOOLS,
    TOOL_SCOPES,
    AuthorizationDenied,
    authorize,
    required_scope,
)
from pickfair_mcp.auth.principal import Principal, PrincipalInvalid, Scope, parse_principal

__all__ = [
    "OWNER_ONLY_QUALIFIED",
    "OWNER_ONLY_TOOLS",
    "TOOL_SCOPES",
    "AuthorizationDenied",
    "Principal",
    "PrincipalInvalid",
    "Scope",
    "authorize",
    "parse_principal",
    "required_scope",
]
