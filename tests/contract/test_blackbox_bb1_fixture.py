"""Contract test sulle forme REALI di BB-1: fixture di B (pfab-b-20261109-bb1-schema-d1d3-001).

`fixtures/bb1_reader_74be0f92.json` è l'output di `core.blackbox_query.BlackBoxReader` (BB-1 locale
9626f95, `external=True`, dati sintetici, orologio sintetico del 2025) generato da B. Sostituisce
c11e4108… (0df7a411) e b275d7ea… (46e722b): TRACE, ATTEMPT dell'hook, `returned`, e lo schema D1-D2
(order_id come alias opaco ord_<32 hex>, `exchange_ts` distinto da `ts_utc`). Il file è
salvato byte per byte com'è stato dichiarato (JSON minificato a chiavi ordinate): lo sha256 qui
sotto è quello dichiarato da B. Se B rigenera la fixture, cambiano file e hash insieme.

Il lettore qui sotto RIPRODUCE quelle risposte: prova che l'adapter mappa le forme reali, non che la
classe reale si comporti così in ogni caso (resta da eseguire `check_reader` e gli stessi scenari
sulla classe reale quando BB-1 è integrata).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from pickfair_control_api.blackbox_bridge import (
    check_reader,
    event_view,
    make_providers,
    make_request_hook,
)
from tests.contract.test_blackbox_bb1_contract import adapter_for, engine_api
from tests.integration.test_market_tools import call, session_for

pytestmark = [pytest.mark.anyio, pytest.mark.loopback]

FIXTURE = Path(__file__).parent / "fixtures" / "bb1_reader_74be0f92.json"
FIXTURE_SHA256 = "74be0f92274b5dda252061148c82a0c54329be2d50e1d1ddd23e31691a36f6df"
REAL = json.loads(FIXTURE.read_bytes())


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FixtureReader:
    """Risponde con gli output reali della fixture; registra le chiamate come il finto."""

    FILTERS = frozenset()

    def __init__(self, status_key: str = "c_status_healthy", scope: str | None = "RUNTIME") -> None:
        self.real = copy.deepcopy(REAL)
        self.status_key = status_key
        # La fixture 74be0f92 precede `health_scope` (BB-1 dd7b7369). Per provare la mappatura dei
        # valori reali si aggiunge lo scope del runtime, come lo riporta la classe attuale; con
        # `scope=None` lo stato resta esattamente quello della fixture.
        if scope is not None:
            for key in ("c_status_healthy", "c_status_degraded"):
                self.real[key] = {**self.real[key], "health_scope": scope}
        self.queries: list[tuple[dict[str, Any], int, int]] = []
        self.requests: list[dict[str, Any]] = []

    def status(self) -> dict[str, Any]:
        return self.real[self.status_key]

    def sessions(self) -> list[dict[str, Any]]:
        return self.real["d_sessions"]

    def query(
        self, filters: dict[str, Any], after_seq: int, limit: int, *, external: bool = False
    ) -> dict[str, Any]:
        assert external is True
        self.queries.append((dict(filters), after_seq, limit))
        return self.real["a_query_page"]

    def get(
        self, event_id: str, chain_depth: int, *, external: bool = False
    ) -> dict[str, Any] | None:
        assert external is True
        found = self.real["b_get_with_chain_2"]
        return found if event_id == found["event_id"] else self.real["b_get_missing"]

    def request_hook(self, record: dict[str, Any]) -> bool:
        self.requests.append(record)
        key = "e_request_hook_attempt_return" if record.get("phase") == "ATTEMPT" else (
            "e_request_hook_return"
        )
        return self.real[key]


def test_the_fixture_is_the_one_b_declared() -> None:
    data = FIXTURE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256 and len(data) == 20484
    assert REAL["source"].startswith("core.blackbox_query.BlackBoxReader")


def test_the_replica_has_the_reader_interface() -> None:
    assert check_reader(FixtureReader()) == []


def test_every_real_record_maps_none_becomes_corrupt() -> None:
    views = [event_view(r) for r in REAL["a_query_page"]["records"]]
    assert [v["seq"] for v in views] == list(range(1, 16))


async def test_the_real_page_through_control_api_and_mcp(tmp_path: Path) -> None:
    reader = FixtureReader()
    with engine_api(tmp_path, reader) as (server, token_path):  # type: ignore[arg-type]
        async with session_for(adapter_for(server, token_path)) as s:
            ok, page = await call(s, "list_blackbox_events", {"limit": 50})
    assert ok is False, page
    body = page["data"]["events"]
    by_seq = {e["seq"]: e for e in body["events"]}
    assert sorted(by_seq) == list(range(1, 16)) and body["gaps_in_range"] == []
    assert body["as_of_seq"] == 15 and body["next_after_seq"] == 0 and body["truncated"] is False
    # Arresto non pulito di s_crash: finestra non registrata, esito mai «niente è successo».
    assert body["unrecorded_windows"] == [
        {"seq": 6, "from_ts": "2025-11-09T12:00:07.000Z", "to_ts": "2025-11-09T12:01:08.000Z",
         "reason_code": "UNCLEAN_TERMINATION"}
    ]
    # D1: l'ordine è un alias opaco, uguale fra tentativo, risposta ed abbinamento; anche col DB
    # degradato (seq 11). Nessun id interno nella vista.
    assert by_seq[4]["refs"]["order_id"] == "ord_9554703cbbc9a3793d578c15d4633758"
    assert {by_seq[n]["refs"]["order_id"] for n in (8, 9, 10)} == {
        "ord_3b505fdff4e2c84910d6f14005edc427"
    }
    assert by_seq[11]["refs"]["order_id"] == "ord_181b6b06be617c8c929805943837dbb6"
    assert (by_seq[4]["refs"]["table_id"], by_seq[4]["refs"]["selection_id"]) == (3, 123456)
    # D2: ora dell'exchange solo dove dichiarata, distinta da quella osservata; altrove null.
    assert (by_seq[10]["exchange_ts"], by_seq[10]["ts_utc"]) == (
        "2025-11-09T12:01:10.500Z", "2025-11-09T12:01:11.000Z"
    )
    assert by_seq[9]["exchange_ts"] is None and "exchange_ts" in by_seq[9]["not_recorded"]
    assert by_seq[11]["reason_code"] == "DB_DEGRADED_LOCAL_ID"
    # Eccezione di un thread: componente e nome dell'eccezione come registrati.
    assert (by_seq[12]["component"], by_seq[12]["reason_code"]) == ("thread:worker-x", "KeyError")
    assert by_seq[12]["severity"] == "CRITICAL"
    # not_recorded del motore; la lista di argv non si mostra ed è contata.
    assert "data" in by_seq[2]["not_recorded"] and by_seq[2]["data"] is None
    assert by_seq[1]["data"] == {"pid": 1001} and by_seq[1]["omitted_values"] == 1
    assert by_seq[4]["values_after"] == {"price": "2.12", "stake": "1.5"}  # float esatti
    assert by_seq[9]["values_before"] == {"status": "INFLIGHT"}
    # TRACE del giornale (categoria BETFAIR nel vocabolario di event_journal).
    assert (by_seq[13]["severity"], by_seq[13]["category"]) == ("TRACE", "BETFAIR")
    # La lettura dell'MCP registrata due volte: tentativo prima, risultato con il conteggio dopo.
    attempt, result = by_seq[14], by_seq[15]
    assert (attempt["phase"], attempt["outcome"]) == ("ATTEMPT", "PENDING")
    assert attempt["data"]["returned"] is None and attempt["data"]["status"] is None
    assert (result["phase"], result["outcome"]) == ("RESULT", "VERIFIED")
    assert (result["data"]["returned"], result["data"]["status"]) == (13, 200)
    assert result["data"]["params.limit"] == 50 and result["origin"] == "CONTROL_API"
    # request_id dell'MCP non normalizzato: nessuna cifra inventata.
    assert result["correlation_id"] == attempt["correlation_id"] == "mcp-0123456789abcdef01234567"


async def test_the_real_causal_chain(tmp_path: Path) -> None:
    reader = FixtureReader()
    with engine_api(tmp_path, reader) as (server, token_path):  # type: ignore[arg-type]
        async with session_for(adapter_for(server, token_path)) as s:
            ok, out = await call(
                s, "get_blackbox_event", {"event_id": "b10b3bd7864e4f82b94e0147088a2c58"}
            )
            ok2, missing = await call(s, "get_blackbox_event", {"event_id": "0" * 32})
    assert ok is False, out
    detail = out["data"]["event"]
    assert detail["state"] == "OK" and detail["event"]["event_type"] == "ORDER_MATCHED"
    assert [c["seq"] for c in detail["chain"]] == [9, 8]  # dal più vicino al più lontano
    assert detail["chain_broken_at"] is None and detail["chain_truncated"] is False
    assert ok2 is False and missing["data"]["event"]["state"] == "NOT_FOUND"


def test_a_real_missing_link_breaks_the_chain() -> None:
    reader = FixtureReader()
    chain = reader.real["b_get_with_chain_2"]["causation_chain"]
    chain[1] = {"event_id": chain[1]["event_id"], "missing": True}
    body = make_providers(reader)["blackbox_event"]("b10b3bd7864e4f82b94e0147088a2c58")
    assert [c["seq"] for c in body["chain"]] == [9]
    assert body["chain_broken_at"] == "f43c3d6ced674f0b91175f2335f686ed"


def test_the_real_healthy_status() -> None:
    body = make_providers(FixtureReader())["blackbox_status"]()
    assert body["available"] is True and body["degraded"] is False
    assert body["dropped_non_critical"] == 0
    assert (body["first_seq"], body["last_seq"], body["sessions"]) == (1, 15, 3)
    assert body["current_session_id"] == "s_current"
    # Ciò che BB-1 non riporta resta dichiarato, mai riempito.
    assert set(body["not_reported"]) == {
        "corrupt_records", "last_durable_write_at", "retention_days", "gaps",
        "last_write_error_code",
    }


def test_the_fixture_status_without_health_scope_is_never_healthy() -> None:
    """Così com'è la fixture non dice di chi è la salute: fail-closed, nessuna sessione presunta."""
    p = make_providers(FixtureReader(scope=None))
    body = p["blackbox_status"]()
    assert body["available"] is False and body["degraded"] is None
    assert body["current_session_id"] is None
    assert {"degraded", "dropped_non_critical"} <= set(body["not_reported"])
    with pytest.raises(ValueError, match="clean_shutdown"):
        p["blackbox_sessions"]()


def test_the_real_degraded_status_is_not_available() -> None:
    body = make_providers(FixtureReader("c_status_degraded"))["blackbox_status"]()
    assert body["available"] is False and body["degraded"] is True
    assert body["dropped_non_critical"] == 1
    assert "last_write_error_code" in body["not_reported"]  # last_error_detail di BB-1


async def test_status_and_sessions_pass_the_server_schema(tmp_path: Path) -> None:
    for key in ("c_status_healthy", "c_status_degraded"):
        reader = FixtureReader(key)
        (tmp_path / key).mkdir()
        with engine_api(tmp_path / key, reader) as (server, token_path):  # type: ignore[arg-type]
            async with session_for(adapter_for(server, token_path)) as s:
                ok, status = await call(s, "get_blackbox_status")
                ok2, sessions = await call(s, "list_blackbox_sessions")
        assert ok is False and ok2 is False, (status, sessions)
        assert status["data"]["blackbox"]["available"] is (key == "c_status_healthy")
        items = sessions["data"]["sessions"]["sessions"]
        assert [(i["session_id"], i["end_reason"]) for i in items] == [
            ("s_clean", "CLEAN_STOP"), ("s_crash", "CRASH_DETECTED"), ("s_current", "RUNNING")
        ]
        assert items[0]["ended_at"] == items[0]["last_event_at"] == "2025-11-09T12:00:01.000Z"
        assert items[1]["ended_at"] is None and items[1]["last_event_at"] == (
            "2025-11-09T12:00:07.000Z"
        )


def test_the_real_hook_answers_are_accepted_records() -> None:
    reader = FixtureReader()
    hook = make_request_hook(reader)
    assert hook({"phase": "ATTEMPT", "route": "/v1/status"}) is True
    assert hook({"phase": "RESULT", "route": "/v1/status", "returned": 1}) is True
    assert [r["phase"] for r in reader.requests] == ["ATTEMPT", "RESULT"]
