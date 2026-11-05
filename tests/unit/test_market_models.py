"""MCP-01l: contratto 1.8.0 — `MarketsResponse` e `MarketBookResponse`."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pickfair_control_api.contract import response_schema
from pickfair_control_api.schema_check import validate as server_validate
from pickfair_mcp.contract.parsing import UpstreamInvalidResponse, parse_market_book, parse_markets
from tests.control_api import bodies


def raw(b: dict[str, Any]) -> bytes:
    return json.dumps(b).encode()


def test_valid_bodies_pass_both_sides() -> None:
    m = bodies.markets(markets=[bodies.market("1.1"), bodies.market("1.2", book_status="SUSPENDED",
                                                                  inplay=None, total_matched=None,
                                                                  last_match_time=None)])
    server_validate(m, response_schema("markets"))
    assert len(parse_markets(raw(m)).markets or ()) == 2
    b = bodies.market_book("1.2")
    server_validate(b, response_schema("market_book"))
    assert parse_market_book(raw(b)).book.runners[0].back[0].price == "2.5"  # type: ignore[union-attr]
    nt = bodies.market_book("1.3", state="NOT_TRACKED", book=None)
    server_validate(nt, response_schema("market_book"))
    parse_market_book(raw(nt))


@pytest.mark.parametrize(
    "body",
    [
        bodies.markets(markets=[bodies.market("1.2"), bodies.market("1.1")]),          # non ordinati
        bodies.markets(markets=[bodies.market("1.1"), bodies.market("1.1")]),          # duplicati
        bodies.markets(markets=None, unavailable=[]),                                  # nullo non dichiarato
        bodies.markets(markets=None, unavailable=["markets"], truncated=True),
        bodies.markets(markets=[bodies.market("../x")]),
        bodies.markets(markets=[bodies.market(total_matched=12.5)]),                   # float
        bodies.markets(markets=[bodies.market(book_status="TRADABLE")]),              # giudizio inventato
        bodies.markets(markets=[bodies.market(event_name="Juventus v Inter")]),
    ],
)
def test_markets_rejected(body: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_markets(raw(body))


@pytest.mark.parametrize(
    "body",
    [
        bodies.market_book(state="NOT_TRACKED"),                                        # book con NOT_TRACKED
        bodies.market_book(state="OK", book=None),
        bodies.market_book(market_id="1.2/../x"),
        bodies.market_book(book={**bodies.market_book()["book"],
                                 "runners": [bodies.runner(back=[{"price": "2.4", "size": "1"},
                                                                 {"price": "2.5", "size": "1"}])]}),
        bodies.market_book(book={**bodies.market_book()["book"],
                                 "runners": [bodies.runner(lay=[{"price": "2.6", "size": "1"},
                                                                {"price": "2.5", "size": "1"}])]}),
        bodies.market_book(book={**bodies.market_book()["book"],
                                 "runners": [bodies.runner(), bodies.runner()]}),       # selezione doppia
        bodies.market_book(book={**bodies.market_book()["book"],
                                 "runners": [bodies.runner(back=[{"price": "-2", "size": "1"}])]}),
        bodies.market_book(book={**bodies.market_book()["book"],
                                 "runners": [bodies.runner(back=[{"price": "2", "size": "1"}] * 4)]}),
    ],
)
def test_book_rejected(body: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_market_book(raw(body))
