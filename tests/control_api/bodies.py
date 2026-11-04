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
        "unavailable": [],
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
