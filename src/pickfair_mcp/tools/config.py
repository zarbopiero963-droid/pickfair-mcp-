"""MCP-01j: `get_config` (sola lettura, contratto 1.6.0).

Stesso percorso degli altri tool di lettura (`tools/status.read_snapshot`). Il MCP non modifica la
configurazione e non interpreta i valori: riporta le impostazioni operative di `RoserpinaConfig`
come il core le possiede, da un'allowlist fissata nel contratto (`models.CONFIG_KEYS`). Credenziali,
token e certificati non fanno parte della risposta; il nome di un campo sensibile non compare.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated, Final

from pydantic import Field

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.auth import Scope
from pickfair_mcp.contract.models import ConfigResponse, StrictModel
from pickfair_mcp.contract.parsing import parse_config
from pickfair_mcp.policy.handshake import HandshakeGuard
from pickfair_mcp.tools.meta import UpstreamInfo
from pickfair_mcp.tools.registry import ToolContext, ToolSpec
from pickfair_mcp.tools.status import (
    MAX_SNAPSHOT_AGE_S,
    SUFFIX,
    NoInput,
    read_snapshot,
    upstream_info,
)

CONFIG_ROUTE: Final = "GET /v1/config"

CONFIG_DESCRIPTION = (
    "Read-only. Returns Pickfair's operational settings from the local Control API "
    "(GET /v1/config): the Roserpina money-management and risk settings (risk percentages, "
    "optional absolute caps, drawdown thresholds, multipliers, risk profile, table count, "
    "recovery, liquidity and book guards, commission, minimum stake and price, auto-green). Each "
    "setting is SET with its exact value, NOT_SET (optional, not configured) or INVALID "
    "(unreadable in Pickfair, never shown as zero). Credentials, tokens and certificates are "
    "never returned; nothing can be changed through this tool." + SUFFIX
)

Age = Annotated[float, Field(ge=0, le=MAX_SNAPSHOT_AGE_S)]


class GetConfigData(StrictModel):
    config: ConfigResponse
    age_s: Age
    upstream: UpstreamInfo


def make_get_config(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(_: ToolContext) -> GetConfigData:
        snapshot, age = await read_snapshot(
            adapter,
            guard,
            route=CONFIG_ROUTE,
            read=adapter.get_config_raw,
            parse=parse_config,
            timeout_s=timeout_s,
            clock=clock,
        )
        return GetConfigData(config=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="get_config",
        route=CONFIG_ROUTE,
        scope=Scope.READ,
        description=CONFIG_DESCRIPTION,
        input_model=NoInput,
        data_model=GetConfigData,
        handler=handler,
    )
