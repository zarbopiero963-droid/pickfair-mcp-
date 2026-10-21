"""Tool MCP. In MCP-01a il registro di default contiene solo `get_meta`."""

from __future__ import annotations

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter
from pickfair_mcp.policy.handshake import HandshakeGuard
from pickfair_mcp.tools.meta import make_get_meta
from pickfair_mcp.tools.registry import ToolRegistry

DEFAULT_TIMEOUT_S = 5.0


def build_default_registry(
    adapter: ControlApiAdapter | None = None, guard: HandshakeGuard | None = None
) -> ToolRegistry:
    adapter = adapter if adapter is not None else SimulatedControlApiAdapter()
    guard = guard if guard is not None else HandshakeGuard(adapter, timeout_s=DEFAULT_TIMEOUT_S)
    registry = ToolRegistry()
    registry.register(make_get_meta(adapter, guard))
    return registry
