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
    BlackboxEventResponse,
    BlackboxEventsResponse,
    BlackboxSessionsResponse,
    BlackboxStatusResponse,
    ConfigResponse,
    ExposureResponse,
    MarketBookResponse,
    MarketsResponse,
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
    "BAD_REQUEST",
    "BLACKBOX_UNAVAILABLE",
    "BODY_NOT_ALLOWED",
    "CONTRACT_SELF_CHECK",
    "INTERNAL",
    "METHOD_NOT_ALLOWED",
    "NOT_FOUND",
    "NOT_IMPLEMENTED",
    "QUERY_ENCODING",
    "QUERY_PARAM",
    "QUERY_PARAM_REPEATED",
    "QUERY_RANGE",
    "QUERY_TOO_LONG",
    "QUERY_VALUE",
    "RATE_LIMITED",
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
            "stays AMBIGUOUS, never FAILED or absent. AMBIGUOUS and PENDING orders never carry "
            "size_matched, avg_price_matched or size_remaining: an unconfirmed report is not data; "
            "their bet_id stays (the core's reconciliation identity)."
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
        "SL/TP amount), ARMED, TRIGGERED (core marked an SL or TP trigger) or UNKNOWN (unreadable). "
        "trailing (MCP-01m, F-03): NOT_IN_CORE without the core's trailing logic, OFF, WAITING_PROFIT, "
        "ARMED (peak and threshold computed by the core's trailing_stop module), TRIGGERED or UNKNOWN "
        "(persisted peak unreadable); peak from the table meta (MEMORY) or the persisted "
        "risk.trailing_peak record (PERSISTED). A trailing trigger never changes the SL/TP state."
    ),
    "sl_tp_closes": (
        "get_exposure.sl_tp_closes: closes persisted by the core's SL/TP close (F-04, settings "
        "`risk.sl_tp_close.*`), read in one read-only transaction with the position's orders and the "
        "ledger hedge rows: table, position, trigger, close state (CLAIMED/ROUTED/NOT_EXECUTED/"
        "UNCERTAIN, unreadable UNKNOWN), retryable as the core decides, detail code, residual "
        "exposure only from the table that still holds the position. Hedges of the close are the "
        "ledger rows whose cashout_request_id is recorded in the close (cashout_request_ids); null "
        "when the record does not carry them. Closes rejected before the claim "
        "are not persisted by the core and never appear. Without F-04: UNAVAILABLE CORE_PENDING_F04."
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
    "markets": (
        "list_markets / get_market_book: the core MarketTracker's last received book per market, "
        "copied in one read; no network call. NOT_TRACKED for a market Pickfair does not hold. "
        "book_status is Betfair book data, never a tradability judgement (protection "
        "market_tradability). book_age_s (MCP-01n): seconds since Pickfair received the book, "
        "from the tracker's monotonic receive instant, read before the book so it is never "
        "underestimated; null when not provable. Prices and sizes "
        "are exact decimal strings; best three levels per side; market id pattern "
        "^[0-9]{1,4}\\.[0-9]{1,15}$, anything else is 404 on the Control API."
    ),
    "blackbox": (
        "PF-BLACKBOX-01, read-only. The engine's permanent chronological register; the reader "
        "never invents: a field the engine did not record is null and listed in the event's "
        "`not_recorded`. seq is the persistent progressive number: missing seq are reported as "
        "gaps (LOST, CORRUPT, or RETENTION when removed by the configured retention), never "
        "repaired; time windows the engine could not record (e.g. after an unclean stop) are "
        "`unrecorded_windows`, whose outcome is unknown. phase ATTEMPT is what Pickfair tried "
        "(outcome always PENDING), RESULT what "
        "actually happened; an exchange AMBIGUOUS is outcome UNKNOWN, never FAILED. Timestamps "
        "are UTC with milliseconds; local time is the viewer's job. Values of sensitive names "
        "are always [REDACTED]. Filters only on GET /v1/blackbox/events, from a closed "
        "whitelist (since, until, after_seq, limit 1-500, session_id, table_id, market_id, "
        "order_id (opaque alias ord_<32 hex>), bet_id, selection_id, strategy, correlation_id, "
        "causation_id, category, origin, severity, phase, event_type, outcome: the filters of "
        "the engine's BB-1 reader); an unknown or repeated parameter, a value out of pattern or a "
        "range over 31 days is 400 without calling the core. Every Control API request is "
        "recorded once in the register (never once per returned event); a request that cannot "
        "be recorded is refused 503 BLACKBOX_UNAVAILABLE, except /v1/blackbox/status and /v1/meta "
        "(the handshake, no Pickfair data), so the register's failure stays visible."
    ),
    "protections": (
        "Each protection is ACTIVE, INACTIVE, TRIGGERED, UNKNOWN or UNAVAILABLE; only ACTIVE has "
        "no reason. A protection that cannot be verified is UNKNOWN (core has it, value not "
        "readable) or UNAVAILABLE (core does not expose it yet), never ACTIVE or INACTIVE; the "
        "derived lists `disabled` and `unverifiable` must match the items."
    ),
    "rate_limit": (
        "C-AUD-06, contract 1.16.0. The Control API limits requests per Bearer token with a token "
        "bucket configured by the core launcher (rate 0.1-20 requests/s, burst 1-50; values out of "
        "range refuse startup, there is no unlimited setting). The limit applies after "
        "authentication and before any Pickfair read: over the limit the answer is 429 "
        "RATE_LIMITED with Retry-After in whole seconds and Pickfair is not queried. Rejections "
        "are recorded in the black box aggregated per window (count, first and last UTC instant, "
        "total since start); a rejection that cannot be recorded is counted in "
        "requests_unrecorded. The MCP reports RATE_LIMITED as retryable and never retries it "
        "automatically."
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
    "security": (
        "Control API: token of at least 43 URL-safe characters (shorter or malformed tokens are "
        "refused at construction), rotations serialized end to end; at most 16 connections served "
        "at once (others closed without a thread), each closed within 10 s; protocol errors answer "
        "400 BAD_REQUEST or 405 METHOD_NOT_ALLOWED with a fixed JSON body, never echoing the input; "
        "no per-request log or traceback."
    ),
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
            "markets": _schema(MarketsResponse),
            "market_book": _schema(MarketBookResponse),
            "blackbox_status": _schema(BlackboxStatusResponse),
            "blackbox_sessions": _schema(BlackboxSessionsResponse),
            "blackbox_events": _schema(BlackboxEventsResponse),
            "blackbox_event": _schema(BlackboxEventResponse),
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
