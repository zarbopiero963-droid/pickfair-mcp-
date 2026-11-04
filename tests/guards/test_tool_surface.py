"""Un solo elenco di tool: ciò che il contratto dichiara è ciò che il server espone.

Regressione trovata durante MCP-01e: `server.build_server` registrava i tool per conto suo, quindi
un tool aggiunto al registro di default compariva nel descrittore del contratto ma non nel server
reale (o viceversa). Ora entrambi usano `tools.register_read_tools`; questo test lo blocca.
"""

from __future__ import annotations

import pytest

from pickfair_control_api import contract as api_contract
from pickfair_mcp.adapters.simulated import SIMULATED_CAPABILITIES, SimulatedControlApiAdapter
from pickfair_mcp.cli import LOCAL_STDIO_PRINCIPAL
from pickfair_mcp.contract.version import load_contract_descriptor
from pickfair_mcp.server import PickfairMcpApp, build_server
from pickfair_mcp.tools import build_default_registry

pytestmark = pytest.mark.guard


def _server_tools() -> set[str]:
    captured: list[set[str]] = []
    original = PickfairMcpApp.__init__

    def spy(self, registry, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(set(registry.names()))
        original(self, registry, **kwargs)

    PickfairMcpApp.__init__ = spy  # type: ignore[method-assign]
    try:
        build_server(SimulatedControlApiAdapter(), timeout_s=1.0, principal=LOCAL_STDIO_PRINCIPAL)
    finally:
        PickfairMcpApp.__init__ = original  # type: ignore[method-assign]
    assert len(captured) == 1
    return captured[0]


def test_server_exposes_exactly_the_contract_tools() -> None:
    declared = set(load_contract_descriptor()["tools"])
    assert _server_tools() == declared == set(build_default_registry().names())


def test_every_exposed_read_route_is_served_by_the_control_api() -> None:
    routes = {spec.route for spec in build_default_registry().specs()}
    assert routes <= set(api_contract.CAPABILITIES)
    assert routes <= set(SIMULATED_CAPABILITIES)


def test_control_api_serves_only_read_routes() -> None:
    # Confronto su metodo + percorso: /v1/orders è una lettura (GET, MCP-01g) e un comando (POST)
    # approvato ma NON servito. Il server ha solo do_GET; ogni altro metodo è 405.
    assert all(c.startswith("GET /v1/") for c in api_contract.CAPABILITIES)
    commands = {
        f"{method} {path}"
        for kind, method, path in load_contract_descriptor()["routes"]
        if kind == "command"
    }
    assert commands and not commands & set(api_contract.CAPABILITIES)
    from pickfair_control_api.server import _Handler

    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert getattr(_Handler, f"do_{verb}") is _Handler._method_not_allowed
