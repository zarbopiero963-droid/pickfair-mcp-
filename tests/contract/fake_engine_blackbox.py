"""Lettore finto della scatola nera, fedele a pf_blackbox_01 §3 e §4-bis (Claude B), per i contract
test.

Record nella forma del MOTORE (non della vista): `source`, `type`, `pid`, `ts_utc` al microsecondo,
`event_id` uuid con trattini, `order_ref` (customer_order_ref), `data` annidato con float. Nessuna
scrittura
esposta oltre al record dell'hook della Control API, come nell'interfaccia di BB-1.
"""

from __future__ import annotations

import uuid
from typing import Any

SESSION = "s-20261108-1"


def uid(n: int) -> str:
    return str(uuid.UUID(int=n))


def record(seq: int, **over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "seq": seq,
        "event_id": uid(seq),
        "ts_utc": f"2026-11-08T15:00:{seq % 60:02d}.123456Z",
        "mono": 1000.0 + seq,
        "session_id": SESSION,
        "session_seq": seq,
        "pid": 4242,
        "source": "SYSTEM",
        "component": "core.runtime",
        "category": "SESSION",
        "type": "SESSION_START",
        "severity": "INFO",
        "state_before": None,
        "state_after": None,
        "values_before": None,
        "values_after": None,
        "reason_code": None,
        "reason": None,
        "correlation_id": None,
        "causation_id": None,
        "table_id": None,
        "market_id": None,
        "selection_id": None,
        "order_ref": None,
        "order_id": None,
        "bet_id": None,
        "strategy": None,
        "phase": "OBSERVATION",
        "outcome": "NOT_APPLICABLE",
        "data": None,
        "prev_hash": "0" * 64,
        "hash": "1" * 64,
    }
    data.update(over)
    return data


def scenario() -> list[dict[str, Any]]:
    """Sessione con impostazione cambiata, comando MCP, decisione di Roserpina, ordine AMBIGUOUS."""
    order = {
        "table_id": 1,
        "market_id": "1.234567",
        "selection_id": 47972,
        "order_ref": "cref-secret-1",
        "order_id": 42,
        "strategy": "roserpina",
        "correlation_id": "corr-1",
    }
    return [
        record(1),
        record(
            2,
            source="USER",
            category="CONFIG",
            type="CONFIG_CHANGE",
            phase="RESULT",
            outcome="VERIFIED",
            values_before={"roserpina": {"stake_pct": 2.0}},
            values_after={"roserpina": {"stake_pct": 2.5}},
            reason_code="SET_BY_USER",
        ),
        record(
            3,
            source="MCP",
            component="control_api",
            category="CONTROL_API",
            type="READ_REQUEST",
            phase="RESULT",
            outcome="VERIFIED",
            data={"route": "/v1/status", "returned": 1},
        ),
        record(
            4,
            source="STRATEGY",
            component="roserpina",
            category="MONEY",
            type="STAKE_DECISION",
            phase="RESULT",
            outcome="VERIFIED",
            reason_code="STAKE_AUTHORIZED",
            data={
                "bankroll_verified": 100.0,
                "mm_pct": 2,
                "stake_theoretical": "2.00",
                "stake_authorized": "2.00",
                "reserved_funds": "2.00",
                "commission": 0.05,
                "currency": "EUR",
                "customer_ref": "cref-secret-1",
                "legs": [1, 2],
            },
            **order,
        ),
        record(
            5,
            source="STRATEGY",
            component="order_manager",
            category="ORDER",
            type="ORDER_PLACE",
            phase="ATTEMPT",
            outcome="PENDING",
            causation_id=uid(4),
            **order,
        ),
        record(
            6,
            source="EXCHANGE",
            component="betfair",
            category="ORDER",
            type="ORDER_PLACE",
            phase="RESULT",
            outcome="UNKNOWN",
            reason_code="AMBIGUOUS",
            reason="nessun esito dall'exchange: riconciliazione richiesta",
            causation_id=uid(5),
            state_before="INFLIGHT",
            state_after="AMBIGUOUS",
            **order,
        ),
        record(7, source="TELEGRAM", severity="TRACE", category="SIGNAL", type="SIGNAL_RECEIVED"),
        record(
            8, source="ROBOT"
        ),  # fuori vocabolario: deve diventare una lacuna CORRUPT, mai un evento
        {k: v for k, v in record(9, category="SYSTEM", type="HEARTBEAT").items() if k != "reason"},
    ]


class FakeBlackboxQuery:
    """Interfaccia di lettura di BB-1 (`core/blackbox_query`), in memoria."""

    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.records = records if records is not None else scenario()
        self.requests: list[dict[str, Any]] = []
        self.accept_requests = True
        self.queries: list[tuple[dict[str, Any], int, int]] = []
        self.gets: list[tuple[str, int]] = []
        self.gaps: list[tuple[int, int, str]] = []

    def status(self) -> dict[str, Any]:
        seqs = [r["seq"] for r in self.records]
        return {
            "available": True,
            "first_seq": min(seqs),
            "last_seq": max(seqs),
            "retained_from_seq": 1,
            "gaps": list(self.gaps),
            "corrupt_records": 0,
            "sessions": 1,
            "current_session_id": SESSION,
            "last_write_error_code": None,
            "last_durable_write_at": "2026-11-08T15:00:09.000001Z",
        }

    def sessions(self) -> list[dict[str, Any]]:
        return [
            {
                "session_id": SESSION,
                "pid": 4242,
                "started_at": "2026-11-08T15:00:01.123456Z",
                "ended_at": None,
                "end_reason": "RUNNING",
                "first_seq": 1,
                "last_seq": max(r["seq"] for r in self.records),
            }
        ]

    def query(
        self, filters: dict[str, Any], after_seq: int, limit: int
    ) -> tuple[Any, int, Any, int]:
        self.queries.append((dict(filters), after_seq, limit))
        out = [r for r in self.records if r["seq"] > after_seq]
        for name, value in filters.items():
            if name in ("since", "until", "severity_min", "q"):
                continue
            out = [r for r in out if r.get(name) == value]
        page = out[:limit]
        more = len(out) > limit
        gaps = [g for g in self.gaps if page and page[0]["seq"] <= g[0] <= page[-1]["seq"]]
        return page, (page[-1]["seq"] if more else 0), gaps, max(r["seq"] for r in self.records)

    def get(self, event_id: str, chain_depth: int) -> tuple[Any, list[Any]]:
        self.gets.append((event_id, chain_depth))
        by_id = {r["event_id"]: r for r in self.records}
        rec = by_id.get(event_id)
        chain, cause = [], rec.get("causation_id") if rec else None
        while cause and cause in by_id and len(chain) < chain_depth:
            chain.append(by_id[cause])
            cause = by_id[cause].get("causation_id")
        return rec, chain

    def record_control_api_request(self, fields: dict[str, Any]) -> bool:
        if not self.accept_requests:
            return False
        self.requests.append(fields)
        return True
