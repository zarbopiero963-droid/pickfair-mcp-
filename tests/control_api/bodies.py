"""Corpi di risposta validi per i test della Control API (stessa forma delle viste del core)."""

from __future__ import annotations

import time
from typing import Any


def status(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core",
        "observed_at": time.time(),
        "consistency": "PER_FIELD_NON_ATOMIC",
        "runtime_state": "ACTIVE",
        "execution_mode": "SIM",
        "live_enabled": False,
        "readiness": {"level": "DEGRADED", "ready": False, "blockers": [], "mcp_aware": False},
        "stop": {
            "emergency_stopped": False,
            "emergency_reason": None,
            "risk_stop_reason": None,
            "daily_loss_pending_stop": False,
            "kill_switch_active": False,
        },
        "engine": engine(),
        "protections": protections(),
        "unavailable": [],
    }
    body.update(overrides)
    return body


def protection(state: str = "ACTIVE", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "state": state,
        "reason": None if state == "ACTIVE" else "NOT_CONFIGURED",
        "source": "CONFIG",
        "limit": None,
        "as_of": None,
    }
    data.update(overrides)
    return data


PROTECTION_KEYS = (
    "kill_switch",
    "emergency_stop",
    "runtime_lockdown",
    "desk_lockdown",
    "drawdown_pct_hard_stop",
    "drawdown_abs_hard_stop",
    "session_loss",
    "daily_loss",
    "risk_stop",
    "exposure_stop",
    "max_open_exposure",
    "max_order_exposure",
    "max_market_exposure",
    "max_event_exposure_abs",
    "max_total_exposure_pct",
    "max_event_exposure_pct",
    "funds_freshness",
    "book_guard",
    "market_tradability",
    "anti_duplication",
    "order_circuit_breaker",
    "recovery_state",
    "config_validity",
)


def protections(**overrides: dict[str, Any]) -> dict[str, Any]:
    items = {key: protection() for key in PROTECTION_KEYS}
    items["funds_freshness"] = protection("UNAVAILABLE", reason="CORE_PENDING_F16", source="NONE")
    items["market_tradability"] = protection(
        "UNAVAILABLE", reason="CORE_PENDING_F23", source="NONE"
    )
    items["max_total_exposure_pct"] = protection("ACTIVE", limit="40")
    items.update(overrides)
    disabled = sorted(k for k, v in items.items() if v["state"] == "INACTIVE")
    unverifiable = sorted(k for k, v in items.items() if v["state"] in ("UNKNOWN", "UNAVAILABLE"))
    return {"items": items, "disabled": disabled, "unverifiable": unverifiable}


def engine(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "trading_engine": {
            "state": "DEGRADED",
            "evaluated_at": "ENGINE_START",
            "risk_gate_wired": True,
            "components": [
                {"name": "db", "state": "READY", "reason": None},
                {"name": "executor", "state": "DEGRADED", "reason": "MISSING"},
            ],
        },
        "betfair": {
            "connected": True,
            "has_client": True,
            "client_kind": "SIMULATION",
            "error_present": False,
            "keepalive": {
                "running": False,
                "failure_count": 0,
                "last_ok_at": None,
                "error_present": False,
            },
        },
        "stream": None,
        "io": {
            "last_status": "UNKNOWN",
            "total_count": 0,
            "slow_count": 0,
            "degraded_count": 0,
            "unavailable_count": 0,
            "last_latency_ms": 0.0,
            "error_present": False,
        },
        "event_bus": {
            "queue_depth": 0,
            "queue_high_watermark": 3,
            "enqueued_total": 10,
            "dequeued_total": 10,
            "running": True,
            "accepting": True,
            "seconds_since_last_dequeue": 1.5,
        },
        "queues": {
            "cashout_inflight": 0,
            "cashout_uncertain": 0,
            "cashout_barriers": 0,
            "direct_unmatched": 0,
        },
        "modes": {
            "configured_execution_mode": "SIM",
            "simulation_flag": True,
            "live_enabled": False,
            "live_readiness_ok": False,
            "client_kind": "SIMULATION",
            "read_only_mode": "NOT_IN_CORE",
        },
        "last_signal_at": None,
        "unavailable": ["stream", "last_signal_at"],
    }
    body.update(overrides)
    return body


def reconciliation(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core",
        "observed_at": time.time(),
        "consistency": "PER_FIELD_NON_ATOMIC",
        "startup": {"state": "OK", "reason": None, "recovery_failure": None},
        "ambiguities_pending": 0,
        "ghosts": {"ghost_orders": 0, "suspected_ghosts": 0, "unconfirmed_inflight": 0},
        "hedge_registry_unreliable": False,
        "recovery_state": {"unreadable": False, "persist_failed": False},
        "settlement": settlement(),
        "unavailable": [],
    }
    body.update(overrides)
    return body


def account(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core",
        "observed_at": time.time(),
        "consistency": "PER_SECTION_LOCKED",
        "execution_mode": "SIM",
        "bankroll": {
            "bankroll_start": 1000.0,
            "bankroll_current": 1012.5,
            "equity_peak": 1020.0,
            "equity_current": 1015.0,
            "realized_pnl": 12.5,
            "unrealized_pnl": 2.5,
            "drawdown_pct": 0.49,
        },
        "cash": {
            "verified": True,
            "cash_equity": 1012.5,
            "committed_exposure": 40.0,
            "unverified_reason": None,
        },
        "exchange_funds": {
            "ok": True,
            "available": 972.5,
            "committed": 40.0,
            "cash_equity": 1012.5,
            "reason": None,
            "source": "SIM_BROKER",
            "age_s": 2.0,
        },
        "desk_mode": "NORMAL",
        "unavailable": [],
    }
    body.update(overrides)
    return body


def table(table_id: int, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "table_id": table_id,
        "status": "FREE",
        "occupied": False,
        "in_recovery": False,
        "market_id": None,
        "selection_id": None,
        "current_exposure": 0.0,
        "loss_amount": 0.0,
        "sl_tp": not_armed(),
    }
    data.update(overrides)
    return data


def not_armed() -> dict[str, Any]:
    return {
        "state": "NOT_ARMED",
        "stop_loss": None,
        "take_profit": None,
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "trailing_stop_pct": None,
        "trailing": {"state": "NOT_IN_CORE", "pct": None, "peak": None, "threshold": None,
                     "peak_source": "NONE"},
    }


def settlement(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "unrecorded_settlements": 0,
        "held_batches": 0,
        "effects": {
            "held": 1,
            "not_realized": 1,
            "by_outcome": [{"outcome": "APPLIED", "count": 3}, {"outcome": "HELD", "count": 1}],
        },
        "checkpoints": {
            "by_stage": [{"stage": "NEXT_TRADE_SUBMIT_CONFIRMED", "count": 2}],
            "cycle_ambiguous": 0,
            "submit_ambiguous": 0,
        },
        "sim_settlements": 4,
        "unavailable": [],
    }
    data.update(overrides)
    return data


def exposure(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core",
        "observed_at": time.time(),
        "consistency": "PER_SECTION_LOCKED",
        "tables": [
            table(
                1,
                status="ACTIVE",
                occupied=True,
                market_id="1.200000001",
                selection_id="47972",
                current_exposure=40.0,
            ),
            table(2),
        ],
        "total_exposure": 40.0,
        "recovery": {"active_count": 0, "max_recovery_tables": 0, "allow_recovery": False},
        "unavailable": [],
        "sl_tp_closes": {"state": "OK", "reason": None, "closes": [], "omitted": 0,
                         "truncated": False},
    }
    body.update(overrides)
    return body


def position(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "market_id": "1.200000001",
        "selection_id": "47972",
        "side": "BACK",
        "table_id": 1,
        "open_size": "10.00",
        "avg_entry_price": "2.5",
        "realized_pnl": "0",
        "unrealized_pnl": "1.25",
        "exposure": "10.00",
        "liability": "10.00",
        "amounts_source": "LEDGER_DECIMAL",
        "unrealized_basis": "LAST_MARK",
        "unavailable": [],
    }
    data.update(overrides)
    return data


def positions(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core",
        "observed_at": time.time(),
        "consistency": "PER_SECTION_LOCKED",
        "positions": [position()],
        "unavailable": [],
    }
    body.update(overrides)
    return body


def order(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "local_id": 7,
        "bet_id": "1000000000001",
        "role": "ENTRY",
        "core_status": "SUBMITTED",
        "status": "PARTIALLY_MATCHED",
        "market_id": "1.200000001",
        "selection_id": "47972",
        "side": "BACK",
        "price": "2.5",
        "stake": "10",
        "size_matched": "4",
        "avg_price_matched": "2.5",
        "size_remaining": "6",
        "table_id": 1,
        "created_at": 1_700_000_000.0,
        "updated_at": 1_700_000_001.5,
        "reconciliation": {
            "in_reconciliation": True,
            "in_engine_queue": False,
            "finalized": False,
            "ambiguity_reason": None,
        },
        "broker_view": "PRESENT",
        "unavailable": [],
    }
    data.update(overrides)
    return data


def orders(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core",
        "observed_at": time.time(),
        "consistency": "SINGLE_READ_TRANSACTION",
        "snapshot": {
            "state": "OK",
            "reason": None,
            "orders": [order()],
            "omitted": 0,
            "truncated": False,
        },
    }
    body.update(overrides)
    return body


def setting(key: str, **overrides: Any) -> dict[str, Any]:
    from pickfair_mcp.contract.models import CONFIG_KEYS, OPTIONAL_CONFIG_KEYS

    kind = CONFIG_KEYS[key]
    if key in OPTIONAL_CONFIG_KEYS:
        data: dict[str, Any] = {"key": key, "kind": kind, "state": "NOT_SET", "value": None}
    else:
        value = {"DECIMAL": "1.5", "BOOL": True, "INT": 5, "ENUM": "BALANCED"}[kind]
        data = {"key": key, "kind": kind, "state": "SET", "value": value}
    data.update(overrides)
    return data


def config(**overrides: Any) -> dict[str, Any]:
    from pickfair_mcp.contract.models import CONFIG_KEYS

    body: dict[str, Any] = {
        "source": "core",
        "observed_at": time.time(),
        "consistency": "SINGLE_REFERENCE_READ",
        "settings": [setting(k) for k in CONFIG_KEYS],
        "unlisted": [],
        "redacted": 0,
        "invalid_persisted": [],
        "unavailable": [],
    }
    body.update(overrides)
    return body


def market(market_id: str = "1.200000001", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"market_id": market_id, "book_status": "OPEN", "inplay": False,
                            "runners": 2, "total_matched": "1500.25",
                            "last_match_time": time.time() - 3.0, "book_age_s": "1.5"}
    data.update(overrides)
    return data


def markets(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"source": "core", "observed_at": time.time(),
                            "consistency": "SINGLE_REFERENCE_READ", "markets": [market()],
                            "omitted": 0, "truncated": False, "unavailable": []}
    body.update(overrides)
    return body


def runner(selection_id: str = "47972", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"selection_id": selection_id, "status": "ACTIVE", "last_price_traded": "2.5",
                            "total_matched": "800", "back": [{"price": "2.5", "size": "100"},
                                                             {"price": "2.48", "size": "40"}],
                            "lay": [{"price": "2.52", "size": "70"}, {"price": "2.54", "size": "15"}]}
    data.update(overrides)
    return data


def market_book(market_id: str = "1.200000001", **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core", "observed_at": time.time(), "consistency": "SINGLE_REFERENCE_READ",
        "market_id": market_id, "state": "OK",
        "book": {"book_status": "OPEN", "inplay": False, "total_matched": "1500.25",
                 "last_match_time": time.time() - 3.0, "runners": [runner()], "omitted_runners": 0,
                 "book_age_s": "1.5"},
    }
    body.update(overrides)
    return body
def sl_tp_close(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "table_id": 1,
        "market_id": "1.200000001",
        "selection_id": "47972",
        "side": "BACK",
        "trigger": "STOP_LOSS",
        "close_state": "ROUTED",
        "retryable": False,
        "detail": None,
        "recorded_at": 1_700_000_100.0,
        "bet_ids": ["1000000000001"],
        "position": {"orders": 1, "partially_matched": 0, "in_reconciliation": 1, "ambiguous": 0,
                     "unreadable": 0},
        "residual_exposure": "40",
        "residual_source": "TABLE",
        "hedges": {"requests": 1, "pending": 1, "placed": 0, "unmatched": 0, "ambiguous": 0,
                   "failed": 0, "not_in_ledger": 0},
    }
    data.update(overrides)
    return data


def sl_tp_closes(*closes: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"state": "OK", "reason": None, "closes": list(closes), "omitted": 0,
                            "truncated": False}
    data.update(overrides)
    return data


# ------------------------------------------------------------- MCP-01o: scatola nera
# (PF-BLACKBOX-01)
def bb_event(seq: int = 1, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "seq": seq, "event_id": f"{seq:032x}", "ts_utc": "2026-11-07T15:00:00.123Z",
        "session_id": "s-20261107-1", "process_id": 4242, "component": "core.order_manager",
        "origin": "STRATEGY", "category": "ORDER", "event_type": "ORDER_PLACE_RESULT",
        "severity": "INFO", "phase": "RESULT", "outcome": "VERIFIED", "state_before": "INFLIGHT",
        "state_after": "SUBMITTED",
        "values_before": None, "values_after": {"stake": "2.50", "price": "3.1"},
        "reason": None, "reason_code": None, "correlation_id": "corr-1", "causation_id": None,
        "refs": {"table_id": 1, "market_id": "1.234567", "selection_id": 47972, "order_id": 42,
                 "bet_id": "31415", "strategy": "roserpina"},
        "data": None, "omitted_values": 0,
        "not_recorded": [],
    }
    data.update(overrides)
    return data


def bb_events(events: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    evs = [bb_event(1), bb_event(2)] if events is None else events
    body: dict[str, Any] = {
        "source": "core", "observed_at": time.time(), "consistency": "SINGLE_READ_SNAPSHOT",
        "events": evs, "next_after_seq": 0, "truncated": False,
        "as_of_seq": max((e["seq"] for e in evs), default=0), "gaps_in_range": [],
        "unrecorded_windows": [], "redacted": 0,
        "unavailable": [],
    }
    body.update(overrides)
    return body


def bb_event_detail(**overrides: Any) -> dict[str, Any]:
    cause = bb_event(1, phase="ATTEMPT", outcome="PENDING", event_type="ORDER_PLACE_ATTEMPT")
    event = bb_event(2, causation_id=cause["event_id"])
    body: dict[str, Any] = {
        "source": "core", "observed_at": time.time(), "consistency": "SINGLE_READ_SNAPSHOT",
        "event_id": event["event_id"], "state": "OK", "event": event, "chain": [cause],
        "chain_truncated": False, "chain_broken_at": None, "redacted": 0,
    }
    body.update(overrides)
    return body


def bb_session(session_id: str = "s-20261107-1", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "session_id": session_id, "process_id": 4242, "started_at": "2026-11-07T14:00:00.000Z",
        "ended_at": "2026-11-07T18:00:00.000Z", "last_event_at": "2026-11-07T18:00:00.000Z",
        "end_reason": "CLEAN_STOP", "first_seq": 1,
        "last_seq": 900,
    }
    data.update(overrides)
    return data


def bb_sessions(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core", "observed_at": time.time(), "consistency": "SINGLE_READ_SNAPSHOT",
        "sessions": [bb_session(), bb_session("s-20261108-1", started_at="2026-11-08T09:00:00.000Z",
                                              ended_at=None, end_reason="RUNNING", first_seq=901,
                                              last_event_at="2026-11-08T09:30:00.000Z",
                                              last_seq=950)],
        "truncated": False, "unavailable": [],
    }
    body.update(overrides)
    return body


def bb_status(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": "core", "observed_at": time.time(), "consistency": "PER_FIELD_NON_ATOMIC",
        "available": True, "degraded": False, "dropped_non_critical": 0,
        "first_seq": 1, "last_seq": 950, "retained_from_seq": 1,
        "gaps": [{"from_seq": 400, "to_seq": 402, "kind": "LOST"}], "gaps_truncated": False,
        "corrupt_records": 0, "sessions": 2, "current_session_id": "s-20261108-1",
        "last_write_error_code": None, "last_durable_write_at": "2026-11-08T09:30:00.000Z",
        "retention_days": 365, "requests_unrecorded": 0, "not_reported": [],
    }
    body.update(overrides)
    return body
