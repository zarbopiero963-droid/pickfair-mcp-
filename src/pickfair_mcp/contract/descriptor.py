"""Generatore del descrittore canonico del contratto Control API v1 (fonte di verità unica).

Lo schema hash copre TUTTO ciò che deve coincidere fra MCP e Control API:
route approvate, schemi delle risposte upstream, schemi di input/output dei tool esposti,
codici d'errore dei due lati e semantica (valori indisponibili, codici, consistenza,
freschezza). Una modifica a uno di questi elementi cambia l'hash e rende incompatibili
le due parti finché non vengono riallineate.

Il descrittore generato è salvato in due copie identiche:
``src/pickfair_mcp/contract/descriptor_v1.json`` (usata dal MCP) e
``src/pickfair_control_api/contract_v1.json`` (usata dalla Control API, solo libreria
standard). ``tests/unit/test_contract_descriptor.py`` rigenera il descrittore e fallisce
se una delle due copie differisce. Rigenerazione: ``pickfair-mcp contract-descriptor``.
"""

from __future__ import annotations

import json
from typing import Any, Final

from pickfair_mcp.contract.models import (
    CONFIG_KEYS,
    OPTIONAL_CONFIG_KEYS,
    ORDER_STATUS_MAP,
    AccountResponse,
    ConfigResponse,
    ExposureResponse,
    OrdersResponse,
    PositionsResponse,
    ReconciliationStatusResponse,
    StatusResponse,
)
from pickfair_mcp.contract.routes import APPROVED_ROUTES
from pickfair_mcp.contract.version import (
    CONTRACT_NAME,
    META_RESPONSE_SCHEMA,
    SUPPORTED_CONTRACT_VERSION,
    thaw,
)
from pickfair_mcp.envelope import Envelope
from pickfair_mcp.errors import ErrorCode
from pickfair_mcp.tools.status import MAX_CLOCK_SKEW_S, MAX_SNAPSHOT_AGE_S

# Codici d'errore della Control API (corpo `{"error": {"code": ...}}`), fissi.
CONTROL_API_ERROR_CODES: Final = (
    "BAD_HOST",
    "BODY_NOT_ALLOWED",
    "CONTRACT_SELF_CHECK",
    "INTERNAL",
    "METHOD_NOT_ALLOWED",
    "NOT_FOUND",
    "NOT_IMPLEMENTED",
    "UNAUTHORIZED",
)

SEMANTICS: Final = {
    "unavailable": (
        "A field is null if and only if its name is listed in `unavailable`; "
        "a value the core does not hold is never replaced by a default."
    ),
    "codes": (
        "Codes and reasons match ^[A-Z][A-Z0-9_]{0,63}$; free text from the core becomes "
        "UNSTRUCTURED and never crosses the API."
    ),
    "consistency": (
        "PER_FIELD_NON_ATOMIC: fields are read one at a time without a runtime-wide "
        "critical section; observed_at is the read instant. PER_SECTION_LOCKED: each section "
        "is produced by one core call under the lock of the component that owns it, or is one "
        "value replaced as a whole; two sections may reflect nearby instants."
    ),
    "money": (
        "Amounts are finite floats in EUR exactly as the core holds them, never rounded or "
        "defaulted; execution_mode SIM means the simulated broker's fictitious balance. "
        "Since 1.3.0 new amounts and prices are canonical decimal strings (no exponent, no "
        "float): lossless from the core's Decimal, or the shortest repr of the core's float "
        "when the core holds a float (declared by amounts_source)."
    ),
    "orders": {
        "source": (
            "The core's durable `orders` ledger read in one read-only transaction; hedge orders "
            "of cashouts (HEDGE_*) included; never a network call."
        ),
        "status_map": {k: list(v) for k, v in sorted(ORDER_STATUS_MAP.items())},
        "status_map_rule": (
            "A core status outside the map is UNKNOWN. UNMATCHED / PARTIALLY_MATCHED / MATCHED "
            "for an accepted order only with explicit size_matched and size_remaining. AMBIGUOUS "
            "stays AMBIGUOUS, never FAILED or absent."
        ),
        "not_in_core": ["APPROVED", "CANCELLED", "SETTLED"],
        "snapshot_states": (
            "OK complete; PARTIAL rows omitted or list truncated (reason); STALE read but the "
            "core's startup reconciliation is not done (reason); UNKNOWN database busy; "
            "UNAVAILABLE not readable. Missing values stay null, never zero."
        ),
    },
    "sl_tp": (
        "Per Roserpina table, read from the table meta as the core writes it: NOT_ARMED (no "
        "SL/TP amount), ARMED, TRIGGERED (core marked the trigger) or UNKNOWN (unreadable). "
        "Trailing appears only as a configured percentage: the core has no trailing logic and "
        "the contract never reports it as active."
    ),
    "settlement": (
        "Counts only (no payload, reference or event name): unrecorded settlements, held "
        "Dutching batches, settlement_effects by outcome, cycle checkpoints by stage, SIM "
        "broker settlements (null in LIVE)."
    ),
    "config": {
        "source": (
            "The core's RoserpinaConfig, read through one reference (reload_config swaps it "
            "whole). Only the allowlisted keys below are returned; credentials, tokens, "
            "certificates and persisted settings are never read."
        ),
        "keys": dict(CONFIG_KEYS),
        "optional_keys": sorted(OPTIONAL_CONFIG_KEYS),
        "states": (
            "SET exact value; NOT_SET optional setting not configured (the core treats a missing "
            "risk percentage as a block, a missing optional cap as inactive); INVALID present but "
            "unreadable, never shown as zero."
        ),
        "unlisted": (
            "Names of other core config fields, never their values; a sensitive name is never "
            "listed, only counted in `redacted`."
        ),
    },
    "protections": (
        "Each protection is ACTIVE, INACTIVE, TRIGGERED, UNKNOWN or UNAVAILABLE; only ACTIVE has "
        "no reason. A protection that cannot be verified is UNKNOWN (core has it, value not "
        "readable) or UNAVAILABLE (core does not expose it yet), never ACTIVE or INACTIVE; the "
        "derived lists `disabled` and `unverifiable` must match the items."
    ),
    "not_implemented": (
        "An approved read route the Control API does not serve yet answers 501 NOT_IMPLEMENTED; "
        "a path outside the approved routes answers 404 NOT_FOUND; any method other than GET "
        "answers 405 METHOD_NOT_ALLOWED. No command route is served."
    ),
    "freshness": {
        "max_snapshot_age_s": MAX_SNAPSHOT_AGE_S,
        "max_clock_skew_s": MAX_CLOCK_SKEW_S,
    },
    "source": "Responses declare source=core; the simulated adapter declares source=simulated.",
    "transport": (
        "HTTP/1.1 GET only on 127.0.0.1, Authorization Bearer token required, "
        "Host must be 127.0.0.1:<port>, no redirects, Content-Type application/json; "
        "charset=utf-8, body at most 65536 bytes."
    ),
}


def _schema(model: Any) -> dict[str, Any]:
    result: dict[str, Any] = model.model_json_schema(mode="validation")
    return result


def build_contract_descriptor() -> dict[str, Any]:
    # Import locale: il registro dei tool importa a sua volta il contratto.
    from pickfair_mcp.tools import build_default_registry

    tools = {
        spec.name: {
            "route": spec.route,
            "scope": spec.scope.value,
            "input_schema": _schema(spec.input_model),
            "output_schema": _schema(Envelope[spec.data_model]),  # type: ignore[name-defined]
        }
        for spec in build_default_registry().specs()
    }
    error_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["error"],
        "properties": {
            "error": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code"],
                "properties": {"code": {"enum": list(CONTROL_API_ERROR_CODES)}},
            }
        },
    }
    return {
        "contract_name": CONTRACT_NAME,
        "contract_version": SUPPORTED_CONTRACT_VERSION,
        "routes": [[r.kind.value, r.method, r.path] for r in APPROVED_ROUTES],
        "upstream_schemas": {
            "meta": thaw(META_RESPONSE_SCHEMA),
            "status": _schema(StatusResponse),
            "reconciliation_status": _schema(ReconciliationStatusResponse),
            "account": _schema(AccountResponse),
            "exposure": _schema(ExposureResponse),
            "positions": _schema(PositionsResponse),
            "orders": _schema(OrdersResponse),
            "config": _schema(ConfigResponse),
            "error": error_schema,
        },
        "tools": tools,
        "error_codes": {
            "control_api": list(CONTROL_API_ERROR_CODES),
            "mcp": sorted(code.value for code in ErrorCode),
        },
        "semantics": SEMANTICS,
    }


def serialize_descriptor(descriptor: dict[str, Any]) -> str:
    """Forma su disco: deterministica, ASCII, una riga finale."""
    return json.dumps(descriptor, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
