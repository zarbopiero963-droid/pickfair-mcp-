"""MCP-01i: contratto 1.8.0 — `get_exposure.sl_tp_closes` (chiusure SL/TP persistite da F-04)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pickfair_control_api.contract import response_schema
from pickfair_control_api.schema_check import SchemaViolation
from pickfair_control_api.schema_check import validate as server_validate
from pickfair_mcp.contract.parsing import UpstreamInvalidResponse, parse_exposure
from tests.control_api import bodies


def body(*closes: dict[str, Any], **section: Any) -> dict[str, Any]:
    return bodies.exposure(sl_tp_closes=bodies.sl_tp_closes(*closes, **section))


def raw(b: dict[str, Any]) -> bytes:
    return json.dumps(b).encode()


def rejected(b: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_exposure(raw(b))


def test_valid_close_is_accepted_by_both_sides() -> None:
    b = body(
        bodies.sl_tp_close(),
        bodies.sl_tp_close(
            table_id=2,
            close_state="NOT_EXECUTED",
            retryable=True,
            detail="NO_HEDGE_PUBLISHED",
            residual_exposure=None,
            residual_source="TABLE_RELEASED",
        ),
    )
    server_validate(b, response_schema("exposure"))
    parsed = parse_exposure(raw(b))
    assert parsed.sl_tp_closes.closes[1].retryable is True  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "missing",
    [
        {"state": "UNAVAILABLE", "reason": "CORE_PENDING_F04"},
        {"state": "UNKNOWN", "reason": "DB_BUSY"},
    ],
)
def test_section_missing_is_explicit(missing: dict[str, Any]) -> None:
    b = bodies.exposure(sl_tp_closes=missing)
    server_validate(b, response_schema("exposure"))
    parse_exposure(raw(b))


@pytest.mark.parametrize(
    "overrides",
    [
        {"residual_exposure": "40", "residual_source": "TABLE_RELEASED"},  # residuo senza il tavolo
        {"residual_exposure": None, "residual_source": "TABLE"},
        {"retryable": True},  # ROUTED mai ritentabile
        {"close_state": "UNCERTAIN", "retryable": True},
        {"bet_ids": []},  # rivendicata senza betId
        {"bet_ids": ["1", "1"]},
        {
            "position": {
                "orders": 1,
                "partially_matched": 2,
                "in_reconciliation": 0,
                "ambiguous": 0,
                "unreadable": 0,
            }
        },
        {
            "hedges": {
                "requests": 1,
                "pending": 0,
                "placed": 0,
                "unmatched": 0,
                "ambiguous": 0,
                "failed": 0,
                "not_in_ledger": 2,
            }
        },  # più mancanti che richieste
        {
            "hedges": {
                "requests": 0,
                "pending": 1,
                "placed": 0,
                "unmatched": 0,
                "ambiguous": 0,
                "failed": 0,
                "not_in_ledger": 0,
            }
        },  # riga senza richiesta
    ],
)
def test_close_rules_are_enforced_by_the_mcp(overrides: dict[str, Any]) -> None:
    rejected(body(bodies.sl_tp_close(**overrides)))


@pytest.mark.parametrize(
    "overrides",
    [
        {"customer_ref": "cref-secret"},  # riferimento della posizione: mai
        {"close_state": "DONE"},
        {"trigger": "TRAILING"},
        {"residual_exposure": 40.0},  # importo in float
        {"residual_exposure": "-1"},
        {
            "hedges": {
                "requests": 1,
                "pending": 0,
                "placed": 0,
                "unmatched": 0,
                "ambiguous": 0,
                "failed": 0,
                "not_in_ledger": 0,
                "selection_id": "1",
            }
        },  # schema chiuso
        {"detail": "free text with spaces"},
    ],
)
def test_close_shape_is_closed_in_the_schema(overrides: dict[str, Any]) -> None:
    b = body(bodies.sl_tp_close(**overrides))
    with pytest.raises(SchemaViolation):
        server_validate(b, response_schema("exposure"))
    rejected(b)


@pytest.mark.parametrize(
    "section",
    [
        {"state": "OK", "reason": "X", "omitted": 0, "truncated": False},
        {"state": "OK", "reason": None, "omitted": 1, "truncated": False},
        {"state": "PARTIAL", "reason": None, "omitted": 1, "truncated": False},
        {"state": "PARTIAL", "reason": "TRUNCATED", "omitted": 0, "truncated": False},
    ],
)
def test_snapshot_state_rules(section: dict[str, Any]) -> None:
    rejected(body(**section))


def test_hedges_null_when_the_record_has_no_request_ids() -> None:
    parse_exposure(raw(body(bodies.sl_tp_close(hedges=None))))
