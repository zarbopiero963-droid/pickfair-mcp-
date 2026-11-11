"""MCP-01m: contratto 1.11.0 — `sl_tp.trailing` (F-03) e trigger TRAILING_STOP delle chiusure."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pickfair_control_api.contract import response_schema
from pickfair_control_api.schema_check import SchemaViolation
from pickfair_control_api.schema_check import validate as server_validate
from pickfair_mcp.contract.parsing import UpstreamInvalidResponse, parse_exposure
from tests.control_api import bodies


def trailing(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "state": "ARMED",
        "pct": "20",
        "peak": "15",
        "threshold": "12",
        "peak_source": "MEMORY",
    }
    data.update(overrides)
    return data


def body(tr: dict[str, Any]) -> dict[str, Any]:
    sl_tp = {**bodies.not_armed(), "trailing": tr}
    return bodies.exposure(tables=[bodies.table(1, sl_tp=sl_tp)])


def raw(b: dict[str, Any]) -> bytes:
    return json.dumps(b).encode()


@pytest.mark.parametrize(
    "tr",
    [
        trailing(),
        trailing(peak_source="PERSISTED"),
        trailing(state="TRIGGERED"),
        trailing(state="TRIGGERED", peak=None, threshold=None, peak_source="NONE"),
        trailing(state="WAITING_PROFIT", peak=None, threshold=None, peak_source="NONE"),
        trailing(state="OFF", pct=None, peak=None, threshold=None, peak_source="NONE"),
        trailing(state="NOT_IN_CORE", pct="20", peak=None, threshold=None, peak_source="NONE"),
        trailing(state="UNKNOWN", pct="20", peak=None, threshold=None, peak_source="NONE"),
        trailing(threshold="15"),  # soglia uguale al picco (pct molto piccola arrotondata)
    ],
)
def test_valid_trailing_states(tr: dict[str, Any]) -> None:
    b = body(tr)
    server_validate(b, response_schema("exposure"))
    parse_exposure(raw(b))


@pytest.mark.parametrize(
    "tr",
    [
        trailing(peak_source="NONE"),  # picco senza fonte (Y01)
        trailing(state="WAITING_PROFIT", peak=None, threshold=None),  # fonte senza picco (Y01)
        trailing(
            state="WAITING_PROFIT", pct=None, peak=None, threshold=None, peak_source="NONE"
        ),  # Y02
        trailing(state="TRIGGERED", pct=None),  # Y02
        trailing(state="OFF", pct="20", peak=None, threshold=None, peak_source="NONE"),  # Y03
        trailing(threshold=None),  # ARMED senza soglia (Y04)
        trailing(threshold="16"),  # soglia sopra il picco (Y05)
        trailing(state="NOT_IN_CORE"),  # picco senza trailing armato
        trailing(state="UNKNOWN", peak=None, peak_source="NONE"),  # soglia senza picco
    ],
)
def test_incoherent_trailing_is_rejected_by_the_mcp(tr: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_exposure(raw(body(tr)))


@pytest.mark.parametrize(
    "bad", [trailing(state="ACTIVE"), trailing(peak="-1"), trailing(peak=15.0), trailing(extra=1)]
)
def test_trailing_shape_is_closed_in_the_schema(bad: dict[str, Any]) -> None:
    with pytest.raises(SchemaViolation):
        server_validate(body(bad), response_schema("exposure"))


def test_trailing_stop_trigger_in_closes() -> None:
    close = bodies.sl_tp_close(trigger="TRAILING_STOP")
    b = bodies.exposure(sl_tp_closes=bodies.sl_tp_closes(close))
    server_validate(b, response_schema("exposure"))
    assert parse_exposure(raw(b)).sl_tp_closes.closes[0].trigger == "TRAILING_STOP"  # type: ignore[union-attr]
