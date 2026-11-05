"""MCP-01l: `list_markets` e `get_market_book` (sola lettura, contratto 1.8.0).

Fonte: il `MarketTracker` del core, cioè l'ultimo book che Pickfair ha ricevuto per ogni mercato. Nessuna
chiamata di rete: un mercato che Pickfair non segue risponde `NOT_TRACKED`. Lo stato del mercato è quello
riportato dal book (dato Betfair), non un giudizio di negoziabilità: quello è la protezione
`market_tradability` di `get_status` (F-23, Claude D). Prezzi e importi sono stringhe decimali esatte.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated, Final

from pydantic import Field

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.auth import Scope
from pickfair_mcp.contract.models import (
    MarketBookResponse,
    MarketId,
    MarketsResponse,
    StrictModel,
)
from pickfair_mcp.contract.parsing import parse_market_book, parse_markets
from pickfair_mcp.policy.handshake import HandshakeGuard
from pickfair_mcp.tools.meta import UpstreamInfo
from pickfair_mcp.tools.registry import ToolContext, ToolSpec
from pickfair_mcp.tools.status import (
    MAX_SNAPSHOT_AGE_S,
    SUFFIX,
    NoInput,
    _invalid,
    read_snapshot,
    upstream_info,
)

MARKETS_ROUTE: Final = "GET /v1/markets"
MARKET_BOOK_ROUTE: Final = "GET /v1/markets/{id}/book"

_NOTE = (
    " The book is the last one Pickfair received (no network call); its age is known only through "
    "last_match_time. book_status is Betfair data, not a tradability judgement: use "
    "get_status.protections.market_tradability for that."
)
MARKETS_DESCRIPTION = (
    "Read-only. Lists the markets Pickfair currently tracks from the local Control API "
    "(GET /v1/markets): market id, book status, in-play flag, number of runners, total matched "
    "and last match time." + _NOTE + SUFFIX
)
MARKET_BOOK_DESCRIPTION = (
    "Read-only. Returns the order book Pickfair holds for one market from the local Control API "
    "(GET /v1/markets/{id}/book): for each runner the status, last traded price, total matched "
    "and the best three back and lay prices with available size, as exact decimal strings. "
    "state NOT_TRACKED means Pickfair has no book for that market." + _NOTE + SUFFIX
)

Age = Annotated[float, Field(ge=0, le=MAX_SNAPSHOT_AGE_S)]


class MarketBookInput(StrictModel):
    market_id: MarketId


class ListMarketsData(StrictModel):
    markets: MarketsResponse
    age_s: Age
    upstream: UpstreamInfo


class GetMarketBookData(StrictModel):
    book: MarketBookResponse
    age_s: Age
    upstream: UpstreamInfo


def make_list_markets(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(_: ToolContext) -> ListMarketsData:
        snapshot, age = await read_snapshot(
            adapter, guard, route=MARKETS_ROUTE, read=adapter.get_markets_raw,
            parse=parse_markets, timeout_s=timeout_s, clock=clock,
        )
        return ListMarketsData(markets=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="list_markets",
        route=MARKETS_ROUTE,
        scope=Scope.READ,
        description=MARKETS_DESCRIPTION,
        input_model=NoInput,
        data_model=ListMarketsData,
        handler=handler,
    )


def make_get_market_book(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(ctx: ToolContext) -> GetMarketBookData:
        args = ctx.arguments
        if not isinstance(args, MarketBookInput):  # il server passa sempre l'input validato
            raise _invalid("INPUT_MISSING")
        market_id = args.market_id
        snapshot, age = await read_snapshot(
            adapter, guard, route=MARKET_BOOK_ROUTE,
            read=lambda: adapter.get_market_book_raw(market_id),
            parse=parse_market_book, timeout_s=timeout_s, clock=clock,
        )
        if snapshot.market_id != market_id:
            raise _invalid("MARKET_ID_MISMATCH")
        return GetMarketBookData(book=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="get_market_book",
        route=MARKET_BOOK_ROUTE,
        scope=Scope.READ,
        description=MARKET_BOOK_DESCRIPTION,
        input_model=MarketBookInput,
        data_model=GetMarketBookData,
        handler=handler,
    )
