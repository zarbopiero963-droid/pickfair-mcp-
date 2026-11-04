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
