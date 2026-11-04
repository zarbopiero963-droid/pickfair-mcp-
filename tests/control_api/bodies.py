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
