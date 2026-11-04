"""Tool MCP. Registro di default: `get_meta` (MCP-01a), `get_status` e
`get_reconciliation_status` (MCP-02a). Nessun comando."""

from __future__ import annotations

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter
from pickfair_mcp.policy.handshake import HandshakeGuard
from pickfair_mcp.tools.meta import make_get_meta
from pickfair_mcp.tools.registry import ToolRegistry
from pickfair_mcp.tools.status import make_get_reconciliation_status, make_get_status

DEFAULT_TIMEOUT_S = 5.0


def build_default_registry(
    adapter: ControlApiAdapter | None = None, guard: HandshakeGuard | None = None
) -> ToolRegistry:
    adapter = adapter if adapter is not None else SimulatedControlApiAdapter()
    guard = guard if guard is not None else HandshakeGuard(adapter, timeout_s=DEFAULT_TIMEOUT_S)
    registry = ToolRegistry()
    registry.register(make_get_meta(adapter, guard))
    registry.register(make_get_status(adapter, guard, timeout_s=DEFAULT_TIMEOUT_S))
    registry.register(make_get_reconciliation_status(adapter, guard, timeout_s=DEFAULT_TIMEOUT_S))
    return registry
