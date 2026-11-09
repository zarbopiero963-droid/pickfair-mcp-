"""Lettore finto della scatola nera, fedele a pf_blackbox_01 §3 e §4-bis (Claude B), per i contract
test.

Forme REALI di BB-1 (fixture di Claude B, sha256 74be0f92…36f6df, in `fixtures/`): record con
`source`, `type`, `pid`, `ts_utc` al microsecondo, id in 32 hex, `not_recorded` (i campi a null),
`data` annidato con float; `get` con la catena in `causation_chain`; `status` {ok, degraded, …};
`sessions` {started, last_ts, clean_shutdown, …}. Nessuna scrittura esposta oltre a `request_hook`.
Il campo `order_ref` resta nei record finti per provare che la vista lo ignora comunque.
"""

from __future__ import annotations

import uuid
from typing import Any

SESSION = "s-20261108-1"


ORDER_ALIAS = "ord_" + uuid.UUID(int=42).hex  # alias opaco di BB-1 (HMAC dell'id interno)
ORDER_ALIAS_2 = "ord_" + uuid.UUID(int=43).hex


def uid(n: int) -> str:
    """Id nella forma di BB-1: uuid in 32 hex minuscoli senza trattini (event, causation)."""
    return uuid.UUID(int=n).hex


# Colonne che BB-1 elenca in `not_recorded` quando sono null.
NULLABLE = (
    "bet_id", "causation_id", "correlation_id", "data", "exchange_ts", "market_id", "order_id",
    "reason",
    "reason_code", "selection_id", "state_after", "state_before", "strategy", "table_id",
    "values_after", "values_before",
)


def record(seq: int, **over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "seq": seq,
        "event_id": uid(seq),
        "ts_utc": f"2026-11-08T15:00:{seq % 60:02d}.123456Z",
        "exchange_ts": None,
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
    if "not_recorded" not in over:  # come BB-1: ogni colonna a null è non registrata
        data["not_recorded"] = [k for k in NULLABLE if data.get(k) is None]
    return data


def scenario() -> list[dict[str, Any]]:
    """Sessione con impostazione cambiata, comando MCP, decisione di Roserpina, ordine AMBIGUOUS."""
    order = {  # BB-1: table_id e selection_id come testo di cifre; order_id alias opaco (D1)
        "table_id": "1",
        "market_id": "1.234567",
        "selection_id": "47972",
        "order_ref": "cref-secret-1",
        "order_id": ORDER_ALIAS,
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
        record(10, component="thread:Thread-3 (poller)", category="SYSTEM", type="TASK_EXCEPTION",
               severity="ERROR"),
        record(11, source="STRATEGY", category="ORDER", type="ORDER_PLACE", phase="ATTEMPT",
               outcome="PENDING", table_id="2", selection_id="47973",
               order_id=ORDER_ALIAS_2),  # BB-1: cifre come stringhe; alias dell'ordine
    ]


class FakeBlackboxQuery:
    """Interfaccia di lettura di BB-1 (`core/blackbox_query`), in memoria."""

    # Filtri accettati dal lettore (nomi del motore); qualunque altro nome è un errore.
    FILTERS = frozenset({  # i 17 filtri del lettore di BB-1 (pfab-b-20261109-adapter-check-001)
        "from_ts", "to_ts", "session_id", "table_id", "market_id", "order_id", "bet_id", "strategy",
        "correlation_id", "category", "source", "type", "outcome", "selection_id", "phase",
        "causation_id", "severity",
    })

    ok = True
    degraded = False

    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.records = records if records is not None else scenario()
        self.requests: list[dict[str, Any]] = []
        self.accept_requests = True
        self.queries: list[tuple[dict[str, Any], int, int]] = []
        self.gets: list[tuple[str, int]] = []
        self.gaps: list[tuple[int, int, str]] = []
        self.time_gaps: list[dict[str, Any]] = []

    def status(self) -> dict[str, Any]:
        seqs = [r["seq"] for r in self.records]
        return {  # forma di c_status_healthy della fixture di B
            "as_of_seq": max(seqs), "buffered": 0, "count": len(seqs), "degraded": self.degraded,
            "dropped_non_critical": int(self.degraded), "ok": self.ok and not self.degraded,
            "not_reported": ["last_error_detail"] if self.degraded else [], "session_id": SESSION,
        }

    def sessions(self) -> list[dict[str, Any]]:
        return [  # forma di d_sessions della fixture di B
            {
                "session_id": SESSION,
                "pid": 4242,
                "started": "2026-11-08T15:00:01.123456Z",
                "last_ts": max(r["ts_utc"] for r in self.records),
                "clean_shutdown": False,
                "first_seq": 1,
                "last_seq": max(r["seq"] for r in self.records),
            }
        ]

    def query(
        self, filters: dict[str, Any], after_seq: int, limit: int, *, external: bool = False
    ) -> dict[str, Any]:
        assert external is True  # la vista esterna di BB-1: order_ref/customer_ref già esclusi
        self.queries.append((dict(filters), after_seq, limit))
        unknown = set(filters) - self.FILTERS
        if unknown:
            raise ValueError(f"filtro sconosciuto: {sorted(unknown)}")  # come BB-1: mai ignorato
        out = [r for r in self.records if r["seq"] > after_seq]
        for name, value in filters.items():
            if name == "from_ts":
                out = [r for r in out if r["ts_utc"][:23] >= str(value)[:23]]
            elif name == "to_ts":
                out = [r for r in out if r["ts_utc"][:23] <= str(value)[:23]]
            else:
                out = [r for r in out if r.get(name) == value]
        page = out[:limit]
        more = len(out) > limit
        # Forma di BB-1: dict; gaps_in_range sono lacune per tempo (vuote in questo scenario).
        return {"records": page, "next_after_seq": page[-1]["seq"] if more else 0,
                "gaps_in_range": list(self.time_gaps),
                "as_of_seq": max(r["seq"] for r in self.records)}

    def get(
        self, event_id: str, chain_depth: int, *, external: bool = False
    ) -> dict[str, Any] | None:
        """Forma di b_get_with_chain_2: il record con `causation_chain` dal più vicino; un anello
        assente vale {event_id, missing: true}; un evento inesistente dà None."""
        assert external is True
        self.gets.append((event_id, chain_depth))
        by_id = {r["event_id"]: r for r in self.records}
        rec = by_id.get(event_id)
        if rec is None:
            return None
        chain: list[dict[str, Any]] = []
        cause = rec.get("causation_id")
        while cause and len(chain) < chain_depth:
            if cause not in by_id:
                chain.append({"event_id": cause, "missing": True})
                break
            chain.append(by_id[cause])
            cause = by_id[cause].get("causation_id")
        return {**rec, "causation_chain": chain}

    def request_hook(self, record: dict[str, Any]) -> bool:
        if not self.accept_requests:
            return False
        self.requests.append(record)
        return True
