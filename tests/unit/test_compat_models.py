"""MCP-01k: contratto 1.7.0 — un ordine con esito non confermato (AMBIGUOUS, PENDING)
non porta importi.

Forma di riferimento: la riga AMBIGUOUS del fix P0 di Claude D conserva un report con `sizeMatched`
(`RISPOSTE_SENZA_ESITO`, branch `claude/pickfair-core-audit-slu9su`): quel numero non è un dato
confermato.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from pickfair_control_api.contract import response_schema
from pickfair_control_api.schema_check import validate as server_validate
from pickfair_mcp.contract.models import UNCONFIRMED_ORDER_STATUSES
from pickfair_mcp.contract.parsing import UpstreamInvalidResponse, parse_orders
from tests.control_api import bodies

NO_AMOUNTS = ["size_matched", "avg_price_matched", "size_remaining"]


def unconfirmed(core_status: str, status: str, **amounts: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "core_status": core_status,
        "status": status,
        "bet_id": "31415",
        **{k: None for k in NO_AMOUNTS},
    }
    base.update(amounts)
    missing = [k for k in NO_AMOUNTS if base[k] is None]
    order = bodies.order(**base, unavailable=missing)
    order["reconciliation"] = {**order["reconciliation"], "in_reconciliation": True}
    return bodies.orders(
        snapshot={
            "state": "OK",
            "reason": None,
            "orders": [order],
            "omitted": 0,
            "truncated": False,
        }
    )


def raw(body: dict[str, Any]) -> bytes:
    return json.dumps(body).encode()


def test_unconfirmed_statuses() -> None:
    assert UNCONFIRMED_ORDER_STATUSES == {"AMBIGUOUS", "PENDING"}


@pytest.mark.parametrize(
    ("core", "status"),
    [
        ("AMBIGUOUS", "AMBIGUOUS"),
        ("HEDGE_AMBIGUOUS", "AMBIGUOUS"),
        ("INFLIGHT", "PENDING"),
        ("HEDGE_PENDING", "PENDING"),
    ],
)
def test_unconfirmed_without_amounts_is_accepted_with_bet_id(core: str, status: str) -> None:
    body = unconfirmed(core, status)
    server_validate(body, response_schema("orders"))
    order = parse_orders(raw(body)).snapshot.orders[0]  # type: ignore[union-attr]
    assert order.bet_id == "31415" and order.size_matched is None


@pytest.mark.parametrize("field", NO_AMOUNTS)
@pytest.mark.parametrize(("core", "status"), [("AMBIGUOUS", "AMBIGUOUS"), ("INFLIGHT", "PENDING")])
def test_unconfirmed_with_any_amount_is_rejected(core: str, status: str, field: str) -> None:
    body = unconfirmed(core, status, **{field: "5"})
    server_validate(body, response_schema("orders"))  # lo schema lo ammette: la regola è del MCP
    with pytest.raises(UpstreamInvalidResponse):
        parse_orders(raw(body))


def test_confirmed_orders_keep_their_amounts() -> None:
    parse_orders(raw(bodies.orders()))  # SUBMITTED con importi espliciti (fixture standard)
