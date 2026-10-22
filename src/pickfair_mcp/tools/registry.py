"""Registro dei tool con guard strutturali applicati alla registrazione."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pickfair_mcp.auth import TOOL_SCOPES, Scope
from pickfair_mcp.contract.models import StrictModel
from pickfair_mcp.contract.routes import ROUTES_BY_KEY, RouteKind
from pickfair_mcp.policy import exposure
from pickfair_mcp.tools.catalog import APPROVED_TOOL_ROUTES, FORBIDDEN_TOOL_NAME_RE, TOOL_NAME_RE


class RegistryViolation(Exception):
    """Tentativo di registrare un tool non autorizzato."""


@dataclass(frozen=True, slots=True)
class ToolContext:
    request_id: str


Handler = Callable[[ToolContext], Awaitable[StrictModel]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    route: str
    scope: Scope
    description: str
    input_model: type[StrictModel]
    data_model: type[StrictModel]
    handler: Callable[[Any], Awaitable[StrictModel]]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not TOOL_NAME_RE.fullmatch(spec.name) or FORBIDDEN_TOOL_NAME_RE.search(spec.name):
            raise RegistryViolation(f"FORBIDDEN_NAME:{spec.name}")
        expected_route = APPROVED_TOOL_ROUTES.get(spec.name)
        if expected_route is None:
            raise RegistryViolation(f"NAME_NOT_APPROVED:{spec.name}")
        route = ROUTES_BY_KEY.get(spec.route)
        if route is None:
            raise RegistryViolation(f"ROUTE_NOT_APPROVED:{spec.route}")
        if spec.route != expected_route:
            raise RegistryViolation(f"ROUTE_MISMATCH:{spec.name}")
        declared = TOOL_SCOPES.get(spec.name)
        if declared is None or spec.scope is None:
            raise RegistryViolation(f"SCOPE_UNDECLARED:{spec.name}")
        if spec.scope is not declared:
            raise RegistryViolation(f"SCOPE_MISMATCH:{spec.name}")
        if route.kind is not RouteKind.READ and not exposure.commands_exposed():
            raise RegistryViolation(f"COMMAND_EXPOSURE_BLOCKED:{spec.name}")
        if spec.name in self._specs:
            raise RegistryViolation(f"DUPLICATE:{spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs.values())
