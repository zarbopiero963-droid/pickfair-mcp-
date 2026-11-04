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
    assert api_contract.CONTRACT_VERSION == SUPPORTED_CONTRACT_VERSION == "1.1.0"
    assert COMPAT_MATRIX == {"1.1.0": frozenset({contract_schema_hash()})}


def test_descriptor_covers_tools_errors_and_semantics() -> None:
    d = json.loads(GENERATED)
    assert set(d["tools"]) == {"get_meta", "get_status", "get_reconciliation_status"}
    for tool in d["tools"].values():
        assert tool["input_schema"]["additionalProperties"] is False
        assert "ok" in tool["output_schema"]["properties"]
        assert tool["scope"] == "read"
    assert set(d["error_codes"]["mcp"]) == {c.value for c in ErrorCode}
    assert "CONTRACT_SELF_CHECK" in d["error_codes"]["control_api"]
    assert set(d["upstream_schemas"]) == {"meta", "status", "reconciliation_status", "error"}
    assert {"unavailable", "codes", "consistency", "freshness"} <= set(d["semantics"])
    assert len(d["routes"]) == 25


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
