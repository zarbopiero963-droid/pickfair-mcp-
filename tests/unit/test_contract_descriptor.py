"""Fase C: descrittore canonico unico, copie identiche, hash condiviso, schemi coerenti.

Prova differenziale: per ogni corpo ostile, il parser strict del MCP (pydantic) e il
validatore della Control API (JSON Schema del descrittore) devono rifiutare entrambi; per i
corpi validi devono accettare entrambi. Una divergenza è un difetto di contratto.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

import pickfair_control_api.contract as api_contract
from pickfair_control_api.schema_check import SchemaViolation, validate
from pickfair_mcp.contract.descriptor import build_contract_descriptor, serialize_descriptor
from pickfair_mcp.contract.parsing import (
    UpstreamInvalidResponse,
    parse_account,
    parse_exposure,
    parse_orders,
    parse_positions,
    parse_reconciliation_status,
    parse_status,
)
from pickfair_mcp.contract.version import (
    COMPAT_MATRIX,
    DESCRIPTOR_PATH,
    SUPPORTED_CONTRACT_VERSION,
    contract_schema_hash,
)
from pickfair_mcp.errors import ErrorCode
from tests.control_api import bodies

GENERATED = serialize_descriptor(build_contract_descriptor())


def test_both_committed_copies_equal_the_generated_descriptor() -> None:
    assert Path(DESCRIPTOR_PATH).read_text(encoding="ascii") == GENERATED
    assert api_contract.DESCRIPTOR_PATH.read_text(encoding="ascii") == GENERATED


def test_hash_and_version_are_shared() -> None:
    assert api_contract.schema_hash() == contract_schema_hash()
    assert api_contract.CONTRACT_VERSION == SUPPORTED_CONTRACT_VERSION == "1.13.0"
    assert COMPAT_MATRIX == {"1.13.0": frozenset({contract_schema_hash()})}


def test_descriptor_covers_tools_errors_and_semantics() -> None:
    d = json.loads(GENERATED)
    assert set(d["tools"]) == {
        "get_meta",
        "get_status",
        "get_reconciliation_status",
        "get_account",
        "get_exposure",
        "list_positions",
        "list_orders",
        "get_config",
        "list_markets",
        "get_market_book",
        "get_blackbox_status",
        "list_blackbox_sessions",
        "list_blackbox_events",
        "get_blackbox_event",
    }
    for tool in d["tools"].values():
        assert tool["input_schema"]["additionalProperties"] is False
        assert "ok" in tool["output_schema"]["properties"]
        assert tool["scope"] == "read"
    assert set(d["error_codes"]["mcp"]) == {c.value for c in ErrorCode}
    assert "CONTRACT_SELF_CHECK" in d["error_codes"]["control_api"]
    assert set(d["upstream_schemas"]) == {
        "meta",
        "status",
        "reconciliation_status",
        "account",
        "exposure",
        "positions",
        "orders",
        "config",
        "markets",
        "market_book",
        "blackbox_status",
        "blackbox_sessions",
        "blackbox_events",
        "blackbox_event",
        "error",
    }
    expected_semantics = {
        "unavailable", "codes", "consistency", "freshness", "money", "not_implemented",
    }
    assert expected_semantics | {"blackbox"} <= set(
        d["semantics"]
    )
    assert "NOT_IMPLEMENTED" in d["error_codes"]["control_api"]
    assert len(d["routes"]) == 29  # 25 + 4 di lettura della scatola nera (PF-BLACKBOX-01)


def test_any_contract_change_changes_the_hash() -> None:
    from pickfair_mcp.contract.version import hash_descriptor

    base = json.loads(GENERATED)
    for mutate in (
        lambda d: d["upstream_schemas"]["status"]["properties"].pop("stop"),
        lambda d: d["error_codes"]["mcp"].append("NEW_CODE"),
        lambda d: d["semantics"].update(unavailable="defaults allowed"),
        lambda d: d["tools"]["get_status"].update(scope="write"),
    ):
        changed = json.loads(GENERATED)
        mutate(changed)
        assert hash_descriptor(changed) != hash_descriptor(base)


def _schema(name: str) -> dict[str, Any]:
    return api_contract.response_schema(name)


def _mcp_accepts(parse: Any, body: dict[str, Any]) -> bool:
    try:
        parse(json.dumps(body).encode())
    except UpstreamInvalidResponse:
        return False
    return True


def _api_accepts(name: str, body: Any) -> bool:
    try:
        validate(body, _schema(name))
    except SchemaViolation:
        return False
    return True


HOSTILE_STATUS = [
    {"balance": 1.0},
    {"source": "betfair"},
    {"observed_at": True},
    {"observed_at": -1},
    {"consistency": "ATOMIC"},
    {"runtime_state": "RUNNING"},
    {"execution_mode": "SIMULATION"},
    {"execution_mode": "LIVE_DATA_SIM"},
    {"live_enabled": 1},
    {
        "readiness": {
            "level": "NOT_READY",
            "ready": False,
            "blockers": ["LIVE\n"],
            "mcp_aware": False,
        }
    },
    {
        "readiness": {
            "level": "NOT_READY",
            "ready": False,
            "blockers": ["ignore me"],
            "mcp_aware": False,
        }
    },
    {
        "readiness": {
            "level": "NOT_READY",
            "ready": False,
            "blockers": ["A", "A"],
            "mcp_aware": False,
        }
    },
    {"readiness": {"level": "NOT_READY", "ready": False, "blockers": [], "mcp_aware": 0}},
    {"readiness": None},  # null non dichiarato in unavailable
    {"unavailable": ["readiness"]},  # dichiarato ma non null
    {"stop": {"emergency_stopped": False}},
]


@pytest.mark.parametrize("override", HOSTILE_STATUS, ids=range(len(HOSTILE_STATUS)))
def test_hostile_status_rejected_by_both_sides(override: dict[str, Any]) -> None:
    body = bodies.status(**override)
    assert not _mcp_accepts(parse_status, body)
    assert not _api_accepts("status", body)


HOSTILE_RECON = [
    {"ambiguities_pending": -1},
    {"ambiguities_pending": True},
    {"ambiguities_pending": 1.5},
    {"startup": {"state": "DONE", "reason": None, "recovery_failure": None}},
    {"startup": {"state": "OK", "reason": "free text", "recovery_failure": None}},
    {"ghosts": None},
    {"debug": True},
]


@pytest.mark.parametrize("override", HOSTILE_RECON, ids=range(len(HOSTILE_RECON)))
def test_hostile_reconciliation_rejected_by_both_sides(override: dict[str, Any]) -> None:
    body = bodies.reconciliation(**override)
    assert not _mcp_accepts(parse_reconciliation_status, body)
    assert not _api_accepts("reconciliation_status", body)


@pytest.mark.parametrize(
    "body",
    [
        bodies.status(),
        bodies.status(readiness=None, unavailable=["readiness"]),
        bodies.status(
            execution_mode="LIVE",
            readiness={
                "level": "NOT_READY",
                "ready": False,
                "blockers": ["LIVE_NOT_ENABLED"],
                "mcp_aware": False,
            },
        ),
        bodies.status(
            stop={
                "emergency_stopped": True,
                "emergency_reason": "UNSTRUCTURED",
                "risk_stop_reason": None,
                "daily_loss_pending_stop": False,
                "kill_switch_active": False,
            }
        ),
    ],
)
def test_valid_status_accepted_by_both_sides(body: dict[str, Any]) -> None:
    assert _mcp_accepts(parse_status, body)
    assert _api_accepts("status", body)


def test_valid_reconciliation_accepted_by_both_sides() -> None:
    for body in (
        bodies.reconciliation(),
        bodies.reconciliation(
            recovery_state=None,
            unavailable=["recovery_state"],
            startup={"state": "NOT_RUN", "reason": None, "recovery_failure": None},
        ),
    ):
        assert _mcp_accepts(parse_reconciliation_status, body)
        assert _api_accepts("reconciliation_status", body)


def test_non_finite_number_rejected_by_api_validator() -> None:
    assert not _api_accepts("status", bodies.status(observed_at=math.nan))
    assert not _api_accepts("status", bodies.status(observed_at=math.inf))


# ------------------------------------------------------------------ MCP-01e (contratto 1.2.0)

_FUNDS = bodies.account()["exchange_funds"]

HOSTILE_ACCOUNT = [
    {"password": "x"},
    {"consistency": "PER_FIELD_NON_ATOMIC"},
    {"execution_mode": "PAPER"},
    {"desk_mode": "YOLO"},
    {"cash": None},  # null non dichiarato
    {"unavailable": ["bankroll"]},  # dichiarato ma presente
    {"bankroll": {**bodies.account()["bankroll"], "bankroll_current": 1e12}},
    {"bankroll": {**bodies.account()["bankroll"], "drawdown_pct": 100.5}},
    {"bankroll": {**bodies.account()["bankroll"], "realized_pnl": True}},
    {"exchange_funds": {**_FUNDS, "available": -1.0}},
    {"exchange_funds": {**_FUNDS, "source": "sim broker"}},
    {"exchange_funds": {**_FUNDS, "reason": "free text"}},
    {"exchange_funds": {**_FUNDS, "error": "x"}},
]


@pytest.mark.parametrize("override", HOSTILE_ACCOUNT, ids=range(len(HOSTILE_ACCOUNT)))
def test_hostile_account_rejected_by_both_sides(override: dict[str, Any]) -> None:
    body = bodies.account(**override)
    assert not _mcp_accepts(parse_account, body)
    assert not _api_accepts("account", body)


HOSTILE_EXPOSURE = [
    {"total_exposure": -1.0},
    {"recovery": None},
    {"tables": [{**bodies.table(1), "customer_ref": "x"}]},
    {"tables": [{**bodies.table(1), "status": "BUSY"}]},
    {"tables": [{**bodies.table(1), "market_id": "Juventus v Inter"}]},
    {"tables": [{**bodies.table(1), "table_id": 0}]},
    {"tables": [bodies.table(i) for i in range(1, 258)]},
]


@pytest.mark.parametrize("override", HOSTILE_EXPOSURE, ids=range(len(HOSTILE_EXPOSURE)))
def test_hostile_exposure_rejected_by_both_sides(override: dict[str, Any]) -> None:
    body = bodies.exposure(**override)
    assert not _mcp_accepts(parse_exposure, body)
    assert not _api_accepts("exposure", body)


@pytest.mark.parametrize(
    ("name", "parse", "body"),
    [
        ("account", parse_account, bodies.account()),
        (
            "account",
            parse_account,
            bodies.account(bankroll=None, desk_mode=None, unavailable=["bankroll", "desk_mode"]),
        ),
        ("exposure", parse_exposure, bodies.exposure()),
        ("exposure", parse_exposure, bodies.exposure(tables=[])),
        (
            "exposure",
            parse_exposure,
            bodies.exposure(total_exposure=None, unavailable=["total_exposure"]),
        ),
    ],
)
def test_valid_finance_bodies_accepted_by_both_sides(name: str, parse: Any, body: Any) -> None:
    assert _mcp_accepts(parse, body)
    assert _api_accepts(name, body)


# Regole fra campi che JSON Schema non esprime: le applica SOLO il MCP (seconda barriera).
# Il ponte del core le rispetta per costruzione; se non lo facesse, la risposta arriva al MCP e
# viene rifiutata (UPSTREAM_INVALID_RESPONSE), mai accettata. L'elenco rende l'asimmetria esplicita.
MCP_ONLY_RULES = [
    ("account", parse_account, {"cash": {**bodies.account()["cash"], "verified": False}}),
    (
        "account",
        parse_account,
        {"cash": {**bodies.account()["cash"], "unverified_reason": "CASH_NOT_READ"}},
    ),
    ("account", parse_account, {"exchange_funds": {**_FUNDS, "ok": False}}),
    ("account", parse_account, {"bankroll": None, "unavailable": ["bankroll"]}),
    ("exposure", parse_exposure, {"tables": [bodies.table(1), bodies.table(1)]}),
]


@pytest.mark.parametrize(("name", "parse", "override"), MCP_ONLY_RULES)
def test_cross_field_rules_are_enforced_by_the_mcp(
    name: str, parse: Any, override: dict[str, Any]
) -> None:
    body = getattr(bodies, name)(**override)
    assert not _mcp_accepts(parse, body)
    assert _api_accepts(name, body)  # se questo cambia, la regola è passata anche nello schema


# ------------------------------------------------------------------ MCP-01f (contratto 1.3.0)


def _status_with_protection(**item: Any) -> dict[str, Any]:
    return bodies.status(protections=bodies.protections(kill_switch=bodies.protection(**item)))


HOSTILE_STATUS_13 = [
    _status_with_protection(state="SAFE"),
    _status_with_protection(state="ACTIVE", reason="X"),  # ACTIVE con motivo
    _status_with_protection(state="UNKNOWN", reason=None),  # non verificabile senza motivo
    _status_with_protection(state="TRIGGERED", reason=None),
    _status_with_protection(state="ACTIVE", reason=None, limit=10.0),  # float
    _status_with_protection(state="ACTIVE", reason=None, limit="1e3"),
    _status_with_protection(state="ACTIVE", reason=None, limit="-0"),
    bodies.status(engine={**bodies.engine(), "secret": "x"}),
    bodies.status(engine={**bodies.engine(), "stream": None, "unavailable": []}),
    bodies.status(
        engine={**bodies.engine(), "modes": {**bodies.engine()["modes"], "read_only_mode": "ON"}}
    ),
]


@pytest.mark.parametrize("body", HOSTILE_STATUS_13, ids=range(len(HOSTILE_STATUS_13)))
def test_hostile_13_status_rejected_by_both_sides(body: dict[str, Any]) -> None:
    assert not _mcp_accepts(parse_status, body)
    assert not _api_accepts("status", body)


HOSTILE_POSITIONS = [
    bodies.positions(positions=[bodies.position(open_size=10.0)]),
    bodies.positions(positions=[bodies.position(open_size="1e1")]),
    bodies.positions(positions=[bodies.position(side="BUY")]),
    bodies.positions(positions=[bodies.position(event_key="x")]),
    bodies.positions(positions=[bodies.position(exposure=None)]),  # null non dichiarato
    bodies.positions(positions=None),
    bodies.positions(positions=[bodies.position()] * 513),
]


@pytest.mark.parametrize("body", HOSTILE_POSITIONS, ids=range(len(HOSTILE_POSITIONS)))
def test_hostile_positions_rejected_by_both_sides(body: dict[str, Any]) -> None:
    assert not _mcp_accepts(parse_positions, body)
    assert not _api_accepts("positions", body)


def test_valid_13_bodies_accepted_by_both_sides() -> None:
    for name, parse, body in (
        ("status", parse_status, bodies.status()),
        ("positions", parse_positions, bodies.positions()),
        ("positions", parse_positions, bodies.positions(positions=[])),
        ("positions", parse_positions, bodies.positions(positions=None, unavailable=["positions"])),
    ):
        assert _mcp_accepts(parse, body), name
        assert _api_accepts(name, body), name


# Regole fra campi solo-MCP introdotte in 1.3.0 (JSON Schema non le esprime).
MCP_ONLY_RULES_13 = [
    (
        "status",
        parse_status,
        {**bodies.status(), "protections": {**bodies.protections(), "unverifiable": []}},
    ),  # elenco che tace UNAVAILABLE
    (
        "status",
        parse_status,
        {**bodies.status(), "protections": {**bodies.protections(), "disabled": ["kill_switch"]}},
    ),
    (
        "positions",
        parse_positions,
        bodies.positions(positions=[bodies.position(side="FLAT", exposure="5")]),
    ),
]


@pytest.mark.parametrize(("name", "parse", "body"), MCP_ONLY_RULES_13)
def test_13_cross_field_rules_are_enforced_by_the_mcp(name: str, parse: Any, body: Any) -> None:
    assert not _mcp_accepts(parse, body)
    assert _api_accepts(name, body)


def test_13_semantics_are_part_of_the_hash() -> None:
    d = build_contract_descriptor()
    assert "protections" in d["semantics"] and "positions" in d["upstream_schemas"]
    assert "UNKNOWN" in d["semantics"]["protections"]


# ------------------------------------------------------------------ MCP-01g (contratto 1.4.0)

HOSTILE_ORDERS = [
    bodies.orders(snapshot={**bodies.orders()["snapshot"], "orders": [bodies.order(stake=10.0)]}),
    bodies.orders(
        snapshot={**bodies.orders()["snapshot"], "orders": [bodies.order(customer_ref="x")]}
    ),
    bodies.orders(
        snapshot={**bodies.orders()["snapshot"], "orders": [bodies.order(status="CANCELLED")]}
    ),
    bodies.orders(snapshot={"state": "UNKNOWN", "reason": None}),
    bodies.orders(
        snapshot={
            "state": "CONSISTENT",
            "reason": None,
            "orders": [],
            "omitted": 0,
            "truncated": False,
        }
    ),
    bodies.orders(consistency="PER_SECTION_LOCKED"),
]


@pytest.mark.parametrize("body", HOSTILE_ORDERS, ids=range(len(HOSTILE_ORDERS)))
def test_hostile_orders_rejected_by_both_sides(body: dict[str, Any]) -> None:
    assert not _mcp_accepts(parse_orders, body)
    assert not _api_accepts("orders", body)


def test_valid_orders_accepted_by_both_sides() -> None:
    for body in (
        bodies.orders(),
        bodies.orders(snapshot={"state": "UNAVAILABLE", "reason": "DB_NOT_CONFIGURED"}),
    ):
        assert _mcp_accepts(parse_orders, body)
        assert _api_accepts("orders", body)


# Regole solo-MCP di 1.4.0: mappa degli stati e quantità esplicite (JSON Schema non le esprime).
MCP_ONLY_RULES_14 = [
    bodies.orders(
        snapshot={
            **bodies.orders()["snapshot"],
            "orders": [bodies.order(core_status="AMBIGUOUS", status="FAILED")],
        }
    ),
    bodies.orders(
        snapshot={**bodies.orders()["snapshot"], "orders": [bodies.order(size_remaining="0")]}
    ),  # PARTIAL con residuo 0
    bodies.orders(
        snapshot={"state": "OK", "reason": "X", "orders": [], "omitted": 0, "truncated": False}
    ),
]


@pytest.mark.parametrize("body", MCP_ONLY_RULES_14, ids=range(len(MCP_ONLY_RULES_14)))
def test_14_cross_field_rules_are_enforced_by_the_mcp(body: dict[str, Any]) -> None:
    assert not _mcp_accepts(parse_orders, body)
    assert _api_accepts("orders", body)


def test_14_order_map_is_part_of_the_hash() -> None:
    d = build_contract_descriptor()
    assert d["semantics"]["orders"]["status_map"]["AMBIGUOUS"] == ["AMBIGUOUS"]
    assert d["semantics"]["orders"]["not_in_core"] == ["APPROVED", "CANCELLED", "SETTLED"]


# ------------------------------------------------------------------ MCP-01h (contratto 1.5.0)

HOSTILE_15 = [
    (
        "exposure",
        parse_exposure,
        bodies.exposure(tables=[bodies.table(1, sl_tp={**bodies.not_armed(), "state": "SAFE"})]),
    ),
    (
        "exposure",
        parse_exposure,
        bodies.exposure(tables=[bodies.table(1, sl_tp={**bodies.not_armed(), "stop_loss": "-1"})]),
    ),
    (
        "exposure",
        parse_exposure,
        bodies.exposure(
            tables=[bodies.table(1, sl_tp={**bodies.not_armed(), "trailing": "ACTIVE"})]
        ),
    ),
    (
        "reconciliation_status",
        parse_reconciliation_status,
        bodies.reconciliation(settlement={**bodies.settlement(), "unrecorded_settlements": -1}),
    ),
    (
        "reconciliation_status",
        parse_reconciliation_status,
        bodies.reconciliation(settlement={**bodies.settlement(), "customer_refs": ["x"]}),
    ),
    (
        "reconciliation_status",
        parse_reconciliation_status,
        bodies.reconciliation(settlement={**bodies.settlement(), "sim_settlements": None}),
    ),
]


@pytest.mark.parametrize(("name", "parse", "body"), HOSTILE_15, ids=range(len(HOSTILE_15)))
def test_hostile_15_rejected_by_both_sides(name: str, parse: Any, body: Any) -> None:
    assert not _mcp_accepts(parse, body)
    assert not _api_accepts(name, body)


# Regole fra campi solo-MCP di 1.5.0.
MCP_ONLY_RULES_15 = [
    (
        "exposure",
        parse_exposure,
        bodies.exposure(tables=[bodies.table(1, sl_tp={**bodies.not_armed(), "stop_loss": "2"})]),
    ),
    (
        "reconciliation_status",
        parse_reconciliation_status,
        bodies.reconciliation(
            settlement={
                **bodies.settlement(),
                "effects": {"held": 3, "not_realized": 0, "by_outcome": []},
            }
        ),
    ),
]


@pytest.mark.parametrize(("name", "parse", "body"), MCP_ONLY_RULES_15)
def test_15_cross_field_rules_are_enforced_by_the_mcp(name: str, parse: Any, body: Any) -> None:
    assert not _mcp_accepts(parse, body)
    assert _api_accepts(name, body)
