"""MCP-01f: contratto 1.3.0 — diagnostica motore e protezioni in GET /v1/status, posizioni in
GET /v1/positions. Ogni regola ha un caso PASS e almeno un caso BLOCK.

Regola centrale: una protezione non verificabile è UNKNOWN o UNAVAILABLE, MAI ACTIVE/INACTIVE; lo
stato «disabilitata» o «non verificabile» sta in elenchi derivati controllati dal contratto.
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from typing import Any

import pytest

from pickfair_mcp.contract.models import DECIMAL_PATTERN
from pickfair_mcp.contract.parsing import (
    UpstreamInvalidResponse,
    parse_positions,
    parse_status,
)
from tests.control_api import bodies


def raw(body: dict[str, Any]) -> bytes:
    return json.dumps(body).encode()


def test_valid_status_with_engine_and_protections_parses() -> None:
    status = parse_status(raw(bodies.status()))
    assert status.protections is not None
    assert status.protections.items.funds_freshness.state == "UNAVAILABLE"
    assert status.engine is not None and status.engine.stream is None


# ------------------------------------------------------------------ protezioni


def _with_item(key: str, **item: Any) -> dict[str, Any]:
    return bodies.status(protections=bodies.protections(**{key: bodies.protection(**item)}))


@pytest.mark.parametrize(
    "item",
    [
        {"state": "ACTIVE", "reason": "X"},  # attiva con un motivo
        {"state": "TRIGGERED", "reason": None},  # scattata senza motivo
        {"state": "UNKNOWN", "reason": None},  # non verificabile senza motivo
        {"state": "UNAVAILABLE", "reason": None},
        {"state": "INACTIVE", "reason": None},  # disattivata senza dire perché
        {"state": "SAFE"},  # stato inesistente
        {"state": "OK"},
        {"state": "ACTIVE", "reason": None, "limit": "1e3"},  # notazione esponenziale
        {"state": "ACTIVE", "reason": None, "limit": 10.5},  # float, non Decimal
        {"state": "ACTIVE", "reason": None, "limit": "NaN"},
        {"state": "ACTIVE", "reason": None, "source": "config file"},
        {"state": "ACTIVE", "reason": None, "as_of": -1.0},
    ],
)
def test_incoherent_protection_is_rejected(item: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(_with_item("kill_switch", **item)))


def test_unknown_is_never_reported_as_safe_in_the_derived_lists() -> None:
    body = _with_item("risk_stop", state="UNKNOWN", reason="LOCK_BUSY", source="RUNTIME")
    assert "risk_stop" in parse_status(raw(body)).protections.unverifiable  # type: ignore[union-attr]
    body["protections"]["unverifiable"] = []  # elenco che tace una protezione non verificabile
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(body))


def test_disabled_controls_must_be_declared() -> None:
    body = _with_item("anti_duplication", state="INACTIVE", reason="DISABLED_BY_CONFIG")
    assert parse_status(raw(body)).protections.disabled == ("anti_duplication",)  # type: ignore[union-attr]
    body["protections"]["disabled"] = []
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(body))


def test_every_protection_key_is_mandatory_and_closed() -> None:
    body = bodies.status()
    del body["protections"]["items"]["kill_switch"]
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(body))
    body = bodies.status()
    body["protections"]["items"]["new_shortcut"] = bodies.protection()
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(body))


def test_protections_null_only_when_declared_unavailable() -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(bodies.status(protections=None)))
    assert parse_status(raw(bodies.status(protections=None, unavailable=["protections"])))


# ------------------------------------------------------------------ motore


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("trading_engine", "state"), "RUNNING"),
        (("trading_engine", "evaluated_at"), "NOW"),
        (("trading_engine", "components"), [{"name": "db", "state": "READY", "reason": None}] * 2),
        (("trading_engine", "components"), [{"name": "DB!", "state": "READY", "reason": None}]),
        (("betfair", "client_kind"), "PAPER"),
        (("betfair", "app_key"), "x"),  # credenziali: il contratto è chiuso
        (("io", "last_latency_ms"), -1.0),
        (("io", "last_error"), "timeout talking to api.betfair.com"),  # testo libero vietato
        (("event_bus", "queue_depth"), -1),
        (("modes", "read_only_mode"), "ENABLED"),  # il core non ha READ_ONLY: mai inventato
        (("modes", "configured_execution_mode"), "PAPER"),
        (("unavailable",), ["stream"]),  # last_signal_at null ma non dichiarato
    ],
)
def test_engine_violations_are_rejected(path: tuple[str, ...], value: Any) -> None:
    eng = copy.deepcopy(bodies.engine())
    target = eng
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(bodies.status(engine=eng)))


def test_ready_engine_with_failing_component_is_rejected() -> None:
    eng = bodies.engine()
    eng["trading_engine"]["state"] = "READY"  # componente DEGRADED ma motore READY
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(bodies.status(engine=eng)))


# ------------------------------------------------------------------ posizioni e Decimal


def test_positions_parse_with_lossless_decimal_strings() -> None:
    body = bodies.positions(
        positions=[
            bodies.position(open_size="0.1", avg_entry_price="1.0000000000000000000000000001")
        ]
    )
    pos = parse_positions(raw(body)).positions[0]  # type: ignore[index]
    assert pos.open_size == "0.1" and Decimal(pos.open_size) == Decimal("0.1")
    assert Decimal(pos.avg_entry_price) - 1 == Decimal("1E-28")  # nessuna perdita via float


@pytest.mark.parametrize(
    "override",
    [
        {"open_size": 10.0},  # float finanziario
        {"open_size": "1e1"},
        {"open_size": "10."},
        {"open_size": ".5"},
        {"open_size": "+1"},
        {"open_size": "01"},
        {"open_size": "-0"},
        {"open_size": "Infinity"},
        {"open_size": "1" * 16},  # oltre 15 cifre intere
        {"side": "BUY"},
        {"table_id": 0},
        {"market_id": "Juventus v Inter"},
        {"amounts_source": "GUESS"},
        {"event_key": "Juventus v Inter"},  # chiave interna: mai esposta
        {"customer_ref": "abc"},
        {"exposure": None},  # null non dichiarato
        {"unavailable": ["exposure"]},  # dichiarato ma presente
    ],
)
def test_position_violations_are_rejected(override: dict[str, Any]) -> None:
    body = bodies.positions(positions=[bodies.position(**override)])
    with pytest.raises(UpstreamInvalidResponse):
        parse_positions(raw(body))


def test_float_sourced_position_declares_missing_amounts() -> None:
    pos = bodies.position(
        amounts_source="CORE_FLOAT",
        realized_pnl=None,
        unrealized_pnl=None,
        exposure=None,
        liability=None,
        unavailable=["realized_pnl", "unrealized_pnl", "exposure", "liability"],
    )
    parsed = parse_positions(raw(bodies.positions(positions=[pos]))).positions[0]  # type: ignore[index]
    assert parsed.exposure is None and parsed.amounts_source == "CORE_FLOAT"


def test_flat_position_has_no_exposure() -> None:
    body = bodies.positions(positions=[bodies.position(side="FLAT", exposure="5")])
    with pytest.raises(UpstreamInvalidResponse):
        parse_positions(raw(body))


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("0", True),
        ("12.5", True),
        ("-3.25", True),
        ("123456789012345.1234567890123456789012345678", True),
        ("1e3", False),
        ("-0", False),
        ("-0.00", False),
        ("-0.05", True),
        ("0.000", True),
        ("00.1", False),
        ("1.", False),
        ("1.2.3", False),
        (" 1", False),
        ("1\n", False),
    ],
)
def test_decimal_pattern(text: str, ok: bool) -> None:
    import re

    assert bool(re.fullmatch(DECIMAL_PATTERN.strip("^$"), text)) is ok
