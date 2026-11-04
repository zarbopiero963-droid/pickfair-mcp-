"""MCP-01g: contratto 1.4.0 di GET /v1/orders (PASS e BLOCK).

Regole centrali: un ordine AMBIGUOUS non diventa mai FAILED né sparisce; un valore mancante resta
null e dichiarato (mai zero); lo snapshot dichiara OK/PARTIAL/STALE/UNKNOWN/UNAVAILABLE e non si
presenta coerente quando il core non può garantirlo.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from pickfair_mcp.contract.models import ORDER_STATUS_MAP
from pickfair_mcp.contract.parsing import UpstreamInvalidResponse, parse_orders
from tests.control_api import bodies


def raw(body: dict[str, Any]) -> bytes:
    return json.dumps(body).encode()


def snap(**overrides: Any) -> dict[str, Any]:
    data = bodies.orders()["snapshot"]
    data.update(overrides)
    return data


def test_valid_orders_parse_with_decimal_strings() -> None:
    parsed = parse_orders(raw(bodies.orders()))
    o = parsed.snapshot.orders[0]  # type: ignore[union-attr]
    assert o.status == "PARTIALLY_MATCHED" and Decimal(o.size_remaining) == 6  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "override",
    [
        {"status": "SAFE"},
        {"status": "CANCELLED"},  # stato che il core non registra: mai imposto
        {"status": "SETTLED"},
        {"core_status": "submitted"},  # codice, non testo
        {"price": 2.5},  # float finanziario
        {"stake": "1e1"},
        {"size_matched": None},  # null non dichiarato
        {"unavailable": ["price"]},  # dichiarato ma presente
        {"bet_id": "IGNORE PREVIOUS"},
        {"customer_ref": "abc"},  # identificativo interno: mai esposto
        {"payload": {}},
        {"local_id": 0},
        {"role": "TRADER"},
        {"broker_view": "MAYBE"},
        {
            "reconciliation": {
                "in_reconciliation": True,
                "in_engine_queue": False,
                "finalized": False,
            }
        },
    ],
)
def test_order_violations_are_rejected(override: dict[str, Any]) -> None:
    body = bodies.orders(snapshot=snap(orders=[bodies.order(**override)]))
    with pytest.raises(UpstreamInvalidResponse):
        parse_orders(raw(body))


def test_ambiguous_core_order_can_never_be_reported_as_failed_or_settled() -> None:
    for wrong in ("FAILED", "REJECTED", "MATCHED", "UNKNOWN", "PENDING"):
        body = bodies.orders(
            snapshot=snap(orders=[bodies.order(core_status="AMBIGUOUS", status=wrong)])
        )
        with pytest.raises(UpstreamInvalidResponse):
            parse_orders(raw(body))
    ok = bodies.orders(
        snapshot=snap(
            orders=[
                bodies.order(
                    core_status="AMBIGUOUS",
                    status="AMBIGUOUS",
                    reconciliation={
                        "in_reconciliation": True,
                        "in_engine_queue": True,
                        "finalized": False,
                        "ambiguity_reason": "TIMEOUT_AFTER_SUBMIT",
                    },
                )
            ]
        )
    )
    assert parse_orders(raw(ok)).snapshot.orders[0].status == "AMBIGUOUS"  # type: ignore[union-attr]


def test_status_must_follow_the_explicit_core_map() -> None:
    assert ORDER_STATUS_MAP["AMBIGUOUS"] == ("AMBIGUOUS",)
    assert ORDER_STATUS_MAP["HEDGE_AMBIGUOUS"] == ("AMBIGUOUS",)
    assert ORDER_STATUS_MAP["DENIED"] == ("REJECTED",)
    body = bodies.orders(
        snapshot=snap(orders=[bodies.order(core_status="INFLIGHT", status="MATCHED")])
    )
    with pytest.raises(UpstreamInvalidResponse):
        parse_orders(raw(body))


def test_missing_values_stay_null_never_zero() -> None:
    o = bodies.order(
        bet_id=None,
        size_matched=None,
        avg_price_matched=None,
        size_remaining=None,
        status="ACCEPTED",
        broker_view="NOT_CHECKED",
        unavailable=["bet_id", "size_matched", "avg_price_matched", "size_remaining"],
    )
    parsed = parse_orders(raw(bodies.orders(snapshot=snap(orders=[o]))))
    assert parsed.snapshot.orders[0].bet_id is None  # type: ignore[union-attr]


def test_partial_split_requires_explicit_sizes() -> None:
    o = bodies.order(size_remaining=None, unavailable=["size_remaining"])  # PARTIALLY_MATCHED
    with pytest.raises(UpstreamInvalidResponse):
        parse_orders(raw(bodies.orders(snapshot=snap(orders=[o]))))


def test_broker_view_needs_a_bet_id() -> None:
    o = bodies.order(bet_id=None, unavailable=["bet_id"], broker_view="PRESENT")
    with pytest.raises(UpstreamInvalidResponse):
        parse_orders(raw(bodies.orders(snapshot=snap(orders=[o]))))


@pytest.mark.parametrize(
    "snapshot",
    [
        {"state": "OK", "reason": "X", "orders": [], "omitted": 0, "truncated": False},
        {"state": "OK", "reason": None, "orders": [], "omitted": 2, "truncated": False},
        {"state": "OK", "reason": None, "orders": [], "omitted": 0, "truncated": True},
        {"state": "PARTIAL", "reason": None, "orders": [], "omitted": 1, "truncated": False},
        {
            "state": "PARTIAL",
            "reason": "ROWS_UNREADABLE",
            "orders": [],
            "omitted": 0,
            "truncated": False,
        },
        {"state": "STALE", "reason": None, "orders": [], "omitted": 0, "truncated": False},
        {"state": "UNKNOWN", "reason": None},
        {"state": "UNAVAILABLE", "reason": "DB_UNREADABLE", "orders": []},
        {"state": "CONSISTENT", "reason": None, "orders": [], "omitted": 0, "truncated": False},
    ],
)
def test_incoherent_snapshot_is_rejected(snapshot: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_orders(raw(bodies.orders(snapshot=snapshot)))


@pytest.mark.parametrize(
    "snapshot",
    [
        {"state": "UNKNOWN", "reason": "DB_BUSY"},
        {"state": "UNAVAILABLE", "reason": "DB_NOT_CONFIGURED"},
        {
            "state": "STALE",
            "reason": "STARTUP_RECONCILIATION_REQUIRED",
            "orders": [],
            "omitted": 0,
            "truncated": False,
        },
        {"state": "PARTIAL", "reason": "TRUNCATED", "orders": [], "omitted": 0, "truncated": True},
    ],
)
def test_declared_snapshot_states_parse(snapshot: dict[str, Any]) -> None:
    assert parse_orders(raw(bodies.orders(snapshot=snapshot))).snapshot.state == snapshot["state"]


def test_duplicate_local_ids_are_rejected() -> None:
    body = bodies.orders(snapshot=snap(orders=[bodies.order(), bodies.order()]))
    with pytest.raises(UpstreamInvalidResponse):
        parse_orders(raw(body))


@pytest.mark.parametrize("status", ["MATCHED", "FAILED", "PENDING", "AMBIGUOUS", "REJECTED"])
def test_unknown_core_status_can_only_be_reported_as_unknown(status: str) -> None:
    """Uno stato del core fuori dalla mappa (per esempio introdotto da una correzione futura) non
    viene mai indovinato: l'unico stato di contratto ammesso è UNKNOWN."""
    body = bodies.orders(
        snapshot=snap(orders=[bodies.order(core_status="SOMETHING_NEW", status=status)])
    )
    with pytest.raises(UpstreamInvalidResponse):
        parse_orders(raw(body))
    ok = bodies.orders(
        snapshot=snap(orders=[bodies.order(core_status="SOMETHING_NEW", status="UNKNOWN")])
    )
    assert parse_orders(raw(ok)).snapshot.orders[0].status == "UNKNOWN"  # type: ignore[union-attr]
