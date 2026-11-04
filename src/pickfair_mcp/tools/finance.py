"""MCP-01e: `get_account` e `get_exposure` (sola lettura, contratto 1.2.0).

Stesso percorso di `get_status` (`tools/status.read_snapshot`): handshake sulla capability della
route, lettura con retry limitato, parsing strict, sorgente coerente con l'adapter, freschezza.

Il MCP non calcola nulla di finanziario: importi, drawdown, desk mode, esposizione e capacità di
recovery sono quelli del core, riportati come li ha prodotti. Un valore che il core non possiede
resta null ed è elencato in `unavailable`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated, Final

from pydantic import Field

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.auth import Scope
from pickfair_mcp.contract.models import (
    AccountResponse,
    ExposureResponse,
    PositionsResponse,
    StrictModel,
)
from pickfair_mcp.contract.parsing import parse_account, parse_exposure, parse_positions
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

ACCOUNT_ROUTE: Final = "GET /v1/account"
EXPOSURE_ROUTE: Final = "GET /v1/exposure"
POSITIONS_ROUTE: Final = "GET /v1/positions"

_MONEY = (
    " Amounts are EUR floats exactly as Pickfair holds them; execution_mode SIM means a "
    "fictitious simulated balance, never real money."
)
ACCOUNT_DESCRIPTION = (
    "Read-only. Returns Pickfair bankroll and account state from the local Control API "
    "(GET /v1/account): bankroll, equity peak, realized/unrealized P&L, drawdown, verified cash "
    "basis, the last exchange funds snapshot the runtime recorded (no new exchange call) and the "
    "desk mode (NORMAL/EXPANSION/DEFENSE/LOCKDOWN)." + _MONEY + SUFFIX
)
EXPOSURE_DESCRIPTION = (
    "Read-only. Returns Pickfair exposure from the local Control API (GET /v1/exposure): the "
    "Roserpina tables (status, market and selection ids, exposure, loss to recover), the total "
    "open exposure used by the max_open_exposure cap and the recovery capacity." + _MONEY + SUFFIX
)

POSITIONS_DESCRIPTION = (
    "Read-only. Returns Pickfair open positions from the local Control API (GET /v1/positions): "
    "market and selection ids, BACK/LAY/FLAT, open size, average entry price, realized and "
    "unrealized P&L (last mark-to-market done by Pickfair), exposure and liability. Amounts and "
    "prices are exact decimal strings, never floats; amounts_source says whether they come from "
    "Pickfair's Decimal ledger or from a float with the rest unavailable." + SUFFIX
)

Age = Annotated[float, Field(ge=0, le=MAX_SNAPSHOT_AGE_S)]


class GetAccountData(StrictModel):
    account: AccountResponse
    age_s: Age
    upstream: UpstreamInfo


class GetExposureData(StrictModel):
    exposure: ExposureResponse
    age_s: Age
    upstream: UpstreamInfo


def make_get_account(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(_: ToolContext) -> GetAccountData:
        snapshot, age = await read_snapshot(
            adapter,
            guard,
            route=ACCOUNT_ROUTE,
            read=adapter.get_account_raw,
            parse=parse_account,
            timeout_s=timeout_s,
            clock=clock,
        )
        return GetAccountData(account=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="get_account",
        route=ACCOUNT_ROUTE,
        scope=Scope.READ,
        description=ACCOUNT_DESCRIPTION,
        input_model=NoInput,
        data_model=GetAccountData,
        handler=handler,
    )


def make_get_exposure(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(_: ToolContext) -> GetExposureData:
        snapshot, age = await read_snapshot(
            adapter,
            guard,
            route=EXPOSURE_ROUTE,
            read=adapter.get_exposure_raw,
            parse=parse_exposure,
            timeout_s=timeout_s,
            clock=clock,
        )
        return GetExposureData(exposure=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="get_exposure",
        route=EXPOSURE_ROUTE,
        scope=Scope.READ,
        description=EXPOSURE_DESCRIPTION,
        input_model=NoInput,
        data_model=GetExposureData,
        handler=handler,
    )


class ListPositionsData(StrictModel):
    positions: PositionsResponse
    age_s: Age
    upstream: UpstreamInfo


def make_list_positions(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(_: ToolContext) -> ListPositionsData:
        snapshot, age = await read_snapshot(
            adapter,
            guard,
            route=POSITIONS_ROUTE,
            read=adapter.get_positions_raw,
            parse=parse_positions,
            timeout_s=timeout_s,
            clock=clock,
        )
        return ListPositionsData(positions=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="list_positions",
        route=POSITIONS_ROUTE,
        scope=Scope.READ,
        description=POSITIONS_DESCRIPTION,
        input_model=NoInput,
        data_model=ListPositionsData,
        handler=handler,
    )
