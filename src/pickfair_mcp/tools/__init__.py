"""Tool MCP. Registro di default: `get_meta` (MCP-01a), `get_status` e
`get_reconciliation_status` (MCP-02a), `get_account` e `get_exposure` (MCP-01e),
`list_positions` (MCP-01f), `list_orders` (MCP-01g), `get_config` (MCP-01j), `list_markets` e
`get_market_book` (MCP-01l), lettura della scatola nera (MCP-01o). Nessun comando.

`register_read_tools` è l'UNICO elenco dei tool esposti: lo usano sia il server reale
(`server.build_server`) sia il descrittore del contratto, così ciò che il contratto dichiara e ciò
che il server espone non possono divergere.
"""

from __future__ import annotations

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter
from pickfair_mcp.policy.handshake import HandshakeGuard
from pickfair_mcp.tools.config import make_get_config
from pickfair_mcp.tools.blackbox import (
    make_get_blackbox_event,
    make_get_blackbox_status,
    make_list_blackbox_events,
    make_list_blackbox_sessions,
)
from pickfair_mcp.tools.markets import make_get_market_book, make_list_markets
from pickfair_mcp.tools.finance import (
    make_get_account,
    make_get_exposure,
    make_list_orders,
    make_list_positions,
)
from pickfair_mcp.tools.meta import make_get_meta
from pickfair_mcp.tools.registry import ToolRegistry
from pickfair_mcp.tools.status import make_get_reconciliation_status, make_get_status

DEFAULT_TIMEOUT_S = 5.0


def register_read_tools(
    registry: ToolRegistry,
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
) -> ToolRegistry:
    registry.register(make_get_meta(adapter, guard))
    registry.register(make_get_status(adapter, guard, timeout_s=timeout_s))
    registry.register(make_get_reconciliation_status(adapter, guard, timeout_s=timeout_s))
    registry.register(make_get_account(adapter, guard, timeout_s=timeout_s))
    registry.register(make_get_exposure(adapter, guard, timeout_s=timeout_s))
    registry.register(make_list_positions(adapter, guard, timeout_s=timeout_s))
    registry.register(make_list_orders(adapter, guard, timeout_s=timeout_s))
    registry.register(make_get_config(adapter, guard, timeout_s=timeout_s))
    registry.register(make_list_markets(adapter, guard, timeout_s=timeout_s))
    registry.register(make_get_market_book(adapter, guard, timeout_s=timeout_s))
    # MCP-01o (PF-BLACKBOX-01): lettura della scatola nera.
    registry.register(make_get_blackbox_status(adapter, guard, timeout_s=timeout_s))
    registry.register(make_list_blackbox_sessions(adapter, guard, timeout_s=timeout_s))
    registry.register(make_list_blackbox_events(adapter, guard, timeout_s=timeout_s))
    registry.register(make_get_blackbox_event(adapter, guard, timeout_s=timeout_s))
    return registry


def build_default_registry(
    adapter: ControlApiAdapter | None = None, guard: HandshakeGuard | None = None
) -> ToolRegistry:
    adapter = adapter if adapter is not None else SimulatedControlApiAdapter()
    guard = guard if guard is not None else HandshakeGuard(adapter, timeout_s=DEFAULT_TIMEOUT_S)
    return register_read_tools(ToolRegistry(), adapter, guard, timeout_s=DEFAULT_TIMEOUT_S)
