"""Guard sul catalogo dei tool: solo nomi approvati, nessun comando esposto in MCP-01a."""

from __future__ import annotations

import pytest

from pickfair_mcp.contract.models import StrictModel
from pickfair_mcp.contract.routes import APPROVED_ROUTES, route_key
from pickfair_mcp.policy import exposure
from pickfair_mcp.tools.catalog import APPROVED_TOOL_ROUTES
from pickfair_mcp.tools.registry import RegistryViolation, ToolRegistry, ToolSpec


class NoInput(StrictModel):
    pass


class NoData(StrictModel):
    pass


async def _handler(_: object) -> NoData:
    return NoData()


def spec(name: str, route: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        route=route,
        description="test",
        input_model=NoInput,
        data_model=NoData,
        handler=_handler,
    )


def test_catalog_maps_25_names_onto_the_25_routes() -> None:
    assert len(APPROVED_TOOL_ROUTES) == 25
    assert set(APPROVED_TOOL_ROUTES.values()) == {route_key(r) for r in APPROVED_ROUTES}


def test_default_registry_exposes_only_get_meta() -> None:
    from pickfair_mcp.tools import build_default_registry

    assert build_default_registry().names() == ("get_meta",)


def test_read_tool_with_approved_name_registers() -> None:
    registry = ToolRegistry()
    registry.register(spec("get_status", "GET /v1/status"))
    assert registry.names() == ("get_status",)


@pytest.mark.parametrize(
    ("name", "route"),
    [
        ("place_order", "POST /v1/orders"),
        ("cashout", "POST /v1/cashout"),
        ("stop", "POST /v1/stop"),
        ("set_mode", "POST /v1/mode"),
        ("patch_config", "PATCH /v1/config"),
        ("preview_order", "POST /v1/preview"),
    ],
)
def test_command_tools_are_refused_while_exposure_blocked(name: str, route: str) -> None:
    with pytest.raises(RegistryViolation, match="COMMAND_EXPOSURE_BLOCKED"):
        ToolRegistry().register(spec(name, route))


@pytest.mark.parametrize(
    ("name", "route"),
    [
        ("sim_place_order", "POST /v1/orders"),
        ("live_cashout", "POST /v1/cashout"),
        ("get_telegram_status", "GET /v1/status"),
        ("copy_trade", "POST /v1/orders"),
        ("mirror_orders", "GET /v1/orders"),
        ("follow_master", "GET /v1/orders"),
        ("list_strategies", "GET /v1/config"),
        ("cashout_all", "POST /v1/cashout"),
        ("raw_rpc", "GET /v1/meta"),
    ],
)
def test_unapproved_names_are_refused(name: str, route: str) -> None:
    with pytest.raises(RegistryViolation):
        ToolRegistry().register(spec(name, route))


def test_name_route_mismatch_is_refused() -> None:
    with pytest.raises(RegistryViolation, match="ROUTE_MISMATCH"):
        ToolRegistry().register(spec("get_status", "GET /v1/account"))


def test_unapproved_route_is_refused() -> None:
    with pytest.raises(RegistryViolation, match=r"^ROUTE_NOT_APPROVED:GET /v1/cashout/all$"):
        ToolRegistry().register(spec("get_meta", "GET /v1/cashout/all"))


def test_name_outside_catalog_is_refused_with_code() -> None:
    with pytest.raises(RegistryViolation, match=r"^NAME_NOT_APPROVED:get_balance$"):
        ToolRegistry().register(spec("get_balance", "GET /v1/account"))


def test_tool_error_string_is_the_code() -> None:
    from pickfair_mcp.errors import ErrorCode, ToolError

    assert str(ToolError(ErrorCode.UNKNOWN_TOOL)) == "UNKNOWN_TOOL"


def test_duplicate_registration_is_refused() -> None:
    registry = ToolRegistry()
    registry.register(spec("get_meta", "GET /v1/meta"))
    with pytest.raises(RegistryViolation, match="DUPLICATE"):
        registry.register(spec("get_meta", "GET /v1/meta"))


def test_exposure_constants_are_blocked() -> None:
    assert exposure.MUTATION_EXPOSURE == "BLOCKED_UNTIL_CORE_AUTHORITY_READY"
    assert exposure.LIVE_COMMANDS == "DISABLED"
    assert exposure.commands_exposed() is False


@pytest.mark.parametrize(
    "var",
    [
        "PICKFAIR_MCP_MUTATION_EXPOSURE",
        "PICKFAIR_MCP_LIVE_COMMANDS",
        "MUTATION_EXPOSURE",
        "LIVE_COMMANDS",
    ],
)
def test_environment_cannot_enable_commands(monkeypatch: pytest.MonkeyPatch, var: str) -> None:
    monkeypatch.setenv(var, "ENABLED")
    assert exposure.commands_exposed() is False
    with pytest.raises(RegistryViolation):
        ToolRegistry().register(spec("place_order", "POST /v1/orders"))


def test_forbidden_name_is_refused_even_if_catalog_were_extended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import MappingProxyType

    from pickfair_mcp.tools import registry as registry_module

    extended = dict(APPROVED_TOOL_ROUTES)
    extended["live_get_status"] = "GET /v1/status"
    monkeypatch.setattr(registry_module, "APPROVED_TOOL_ROUTES", MappingProxyType(extended))
    with pytest.raises(RegistryViolation, match="FORBIDDEN_NAME"):
        ToolRegistry().register(spec("live_get_status", "GET /v1/status"))


def test_default_registry_uses_the_given_adapter_and_guard() -> None:
    import anyio

    from pickfair_mcp.adapters.simulated import Scenario, SimulatedControlApiAdapter
    from pickfair_mcp.policy.handshake import HandshakeGuard
    from pickfair_mcp.tools import build_default_registry
    from pickfair_mcp.tools.registry import ToolContext

    adapter = SimulatedControlApiAdapter(Scenario.COMPATIBLE)
    guard = HandshakeGuard(adapter, timeout_s=1.0)
    spec_ = build_default_registry(adapter, guard).get("get_meta")
    assert spec_ is not None
    data = anyio.run(spec_.handler, ToolContext(request_id="req_" + "0" * 32))
    assert adapter.meta_calls == 1
    assert guard.last_result is not None

    other = SimulatedControlApiAdapter()
    spec2 = build_default_registry(other).get("get_meta")
    assert spec2 is not None
    anyio.run(spec2.handler, ToolContext(request_id="req_" + "0" * 32))
    assert other.meta_calls == 1
    assert data is not None


def test_get_meta_description_states_read_only() -> None:
    from pickfair_mcp.tools import build_default_registry

    spec_ = build_default_registry().get("get_meta")
    assert spec_ is not None
    assert spec_.description.startswith("Read-only.")
    assert "Never places, cancels or changes anything." in spec_.description
