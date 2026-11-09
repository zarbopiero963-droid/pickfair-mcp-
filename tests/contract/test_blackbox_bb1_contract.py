"""Contract test BB-1 (PF-BLACKBOX-01): lettore del motore -> adapter -> Control API reale -> MCP.

Il lettore è finto ma con i record nella forma del motore (pf_blackbox_01 §3). Quando BB-1 esiste,
gli
stessi test girano sulla classe reale di Claude B (vedi
`docs/design/BLACKBOX_BB1_COMPATIBILITY.md`): questo
file prova il contratto, non il motore reale, e non dichiara alcun PASS end-to-end sul motore.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from pickfair_control_api.blackbox_bridge import (
    Unmappable,
    check_reader,
    event_view,
    make_providers,
    make_request_hook,
)
from pickfair_control_api.server import ControlApiServer
from pickfair_control_api.tokens import TokenStore, issue_token_file
from pickfair_mcp.adapters.http import HttpControlApiAdapter
from pickfair_mcp.auth.token_file import LocalTokenFile
from tests.contract.fake_engine_blackbox import SESSION, FakeBlackboxQuery, record, uid
from tests.control_api.servers import SHA, Providers, secure_dir
from tests.integration.test_market_tools import call, session_for

pytestmark = [pytest.mark.anyio, pytest.mark.loopback]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@contextmanager
def engine_api(
    tmp_path: Path, reader: FakeBlackboxQuery
) -> Iterator[tuple[ControlApiServer, Path]]:
    token_path = secure_dir(tmp_path) / "control_api.token"
    store = TokenStore(issue_token_file(token_path))
    providers = {**Providers().mapping(), **make_providers(reader)}
    server = ControlApiServer(
        providers,
        port=0,
        tokens=store,
        git_sha=SHA,
        request_hook=make_request_hook(reader),
        allow_ephemeral_port=True,
    )
    server.start()
    try:
        yield server, token_path
    finally:
        server.stop()


def adapter_for(server: ControlApiServer, token_path: Path) -> HttpControlApiAdapter:
    return HttpControlApiAdapter(
        port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
    )


# ------------------------------------------------------------------ interfaccia e mappatura (puri)
def test_the_fake_has_exactly_the_bb1_reader_interface() -> None:
    assert check_reader(FakeBlackboxQuery()) == []


def test_compatibility_check_names_what_is_wrong() -> None:
    class Wrong:
        def status(self) -> dict[str, Any]:
            return {}

        def query(self, where: Any, cursor: int, limit: int) -> None: ...

        def delete(self, seq: int) -> None: ...

    problems = check_reader(Wrong())
    assert "sessions: assente" in problems and "get: assente" in problems
    assert any(p.startswith("query: parametri") for p in problems)
    assert "delete: un lettore non espone scritture" in problems


def test_engine_record_mapping() -> None:
    view = event_view(
        record(
            6,
            source="EXCHANGE",
            phase="RESULT",
            outcome="UNKNOWN",
            order_ref="cref-x",
            reason_code="AMBIGUOUS",
            causation_id=uid(5),
            order_id=42,
        )
    )
    assert view["event_id"] == uid(6).replace("-", "") and view["causation_id"] == uid(5).replace(
        "-", ""
    )
    assert view["ts_utc"] == "2026-11-08T15:00:06.123Z"  # µs troncati al ms, mai arrotondati
    assert (view["origin"], view["process_id"], view["event_type"]) == (
        "EXCHANGE",
        4242,
        "SESSION_START",
    )
    assert view["outcome"] == "UNKNOWN" and view["reason_code"] == "AMBIGUOUS"
    assert "order_ref" not in view and "cref-x" not in str(view)
    assert view["refs"]["order_id"] == 42
    # BB-1: ogni colonna a null è «non registrata» (not_recorded del motore, campi della vista)
    assert view["not_recorded"] == [
        "state_before", "state_after", "values_before", "values_after", "reason",
        "correlation_id", "data",
    ]


def test_not_recorded_comes_from_the_engine_and_from_absent_keys() -> None:
    rec = {k: v for k, v in record(9, not_recorded=[]).items() if k not in ("reason", "data")}
    view = event_view(rec)
    assert view["not_recorded"] == ["reason", "data"] and view["reason"] is None
    assert event_view(record(9, not_recorded=[]))["not_recorded"] == []  # null non dichiarato
    assert event_view(record(9, not_recorded=["reason"]))["not_recorded"] == ["reason"]


@pytest.mark.parametrize(
    "not_recorded",
    [
        ["reason_code"],  # dichiarato non registrato ma con un valore
        ["order_ref"],  # colonna che la vista non conosce
        "reason",  # non una lista
        [1],
    ],
)
def test_engine_not_recorded_never_hides_a_value(not_recorded: Any) -> None:
    with pytest.raises(Unmappable):
        event_view(record(9, reason_code="X", not_recorded=not_recorded))


@pytest.mark.parametrize(
    "over",
    [
        {"source": "ROBOT"},
        {"severity": "FATAL"},
        {"phase": "DONE"},
        {"outcome": "AMBIGUOUS"},
        {"phase": "ATTEMPT", "outcome": "VERIFIED"},
        {"ts_utc": "2026-11-08T15:00:00.1+01:00"},
        {"ts_utc": "2026-11-08 15:00:00"},
        {"event_id": "not-a-uuid"},
        {"type": "lower_case"},
        {"table_id": 0},
        {"market_id": "1.2/../x"},
        {"bet_id": "abc"},
        {"session_id": ""},
        {"causation_id": uid(1)},
    ],
)
def test_unmappable_records_are_refused_never_adjusted(over: dict[str, Any]) -> None:
    with pytest.raises(Unmappable):
        event_view(record(1, **over))


def test_values_are_flattened_exactly_and_unrepresentable_ones_counted() -> None:
    view = event_view(
        record(
            4,
            data={
                "bankroll_verified": 100.0,
                "mm": {"pct": 2.5},
                "legs": [1, 2],
                "note": "x" * 300,
                "BadName": 1,
                "nan": float("nan"),
            },
        )
    )
    assert view["data"] == {
        "bankroll_verified": "100.0",
        "mm.pct": "2.5",
    }  # float -> stringa esatta
    assert (
        view["omitted_values"] == 4
    )  # lista, testo lungo, nome fuori pattern, NaN: contati, non mostrati


# ------------------------------------------------------------------ catena completa fino all'MCP
async def test_owner_question_reconstructed_from_recorded_events_only(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            ok, page = await call(
                s,
                "list_blackbox_events",
                {"since": "2026-11-08T15:00:00Z", "until": "2026-11-08T17:00:00Z"},
            )
    assert ok is False, page
    events = page["data"]["events"]["events"]
    # Il seq 8 non è inventato: è una lacuna.
    assert [e["seq"] for e in events] == [1, 2, 3, 4, 5, 6, 7, 9, 10, 11]
    assert page["data"]["events"]["gaps_in_range"] == [
        {"from_seq": 8, "to_seq": 8, "kind": "CORRUPT"}
    ]
    by_seq = {e["seq"]: e for e in events}
    assert by_seq[2]["values_before"] == {
        "roserpina.stake_pct": "2.0"
    }  # impostazione: prima e dopo
    assert by_seq[3]["origin"] == "MCP"  # comando MCP registrato dal motore
    assert (by_seq[5]["phase"], by_seq[5]["outcome"]) == (
        "ATTEMPT",
        "PENDING",
    )  # inviato, non confermato
    assert (by_seq[6]["outcome"], by_seq[6]["reason_code"]) == (
        "UNKNOWN",
        "AMBIGUOUS",
    )  # da riconciliare
    assert (by_seq[7]["origin"], by_seq[7]["severity"]) == ("TELEGRAM", "TRACE")
    assert "reason" in by_seq[9]["not_recorded"] and by_seq[9]["reason"] is None
    assert "cref-secret-1" not in str(page)  # né order_ref né customer_ref escono mai


async def test_roserpina_stake_decision_is_readable_for_g7(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            ok, page = await call(
                s, "list_blackbox_events", {"strategy": "roserpina", "category": "MONEY"}
            )
    assert ok is False, page
    (decision,) = page["data"]["events"]["events"]
    assert decision["data"] == {
        "bankroll_verified": "100.0",
        "mm_pct": 2,
        "stake_theoretical": "2.00",
        "stake_authorized": "2.00",
        "reserved_funds": "2.00",
        "commission": "0.05",
        "currency": "EUR",
        "customer_ref": "[REDACTED]",
    }
    assert (
        decision["omitted_values"] == 1
        and decision["refs"]["correlation_id" if False else "order_id"] == 42
    )
    assert decision["correlation_id"] == "corr-1"
    assert reader.queries[-1][0] == {"strategy": "roserpina", "category": "MONEY"}


async def test_why_an_order_is_ambiguous_follows_the_causal_chain(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            ok, out = await call(s, "get_blackbox_event", {"event_id": uid(6).replace("-", "")})
    assert ok is False, out
    detail = out["data"]["event"]
    assert [c["event_type"] for c in detail["chain"]] == ["ORDER_PLACE", "STAKE_DECISION"]
    assert detail["chain_broken_at"] is None
    assert reader.gets == [(uid(6), 32)]  # il motore riceve il suo formato di id (32 hex)


async def test_filters_use_the_engine_names(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            await call(s, "list_blackbox_events", {"origin": "USER", "event_type": "CONFIG_CHANGE"})
    assert reader.queries[-1] == ({"source": "USER", "type": "CONFIG_CHANGE"}, 0, 200)


async def test_new_bb1_filters_reach_the_reader_in_the_engine_text_form(tmp_path: Path) -> None:
    """BB-1 confronta per uguale con il testo registrato: 3 != "3" sarebbe una pagina vuota muta."""
    reader = FakeBlackboxQuery()
    uuid_order = "0f8fad5b-d9cb-469f-a165-70867728950e"
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            ok, page = await call(
                s,
                "list_blackbox_events",
                {"table_id": 2, "selection_id": 47973, "order_id": uuid_order, "phase": "ATTEMPT"},
            )
            ok2, page2 = await call(
                s, "list_blackbox_events", {"severity": "ERROR", "causation_id": uid(5)}
            )
            ok3, page3 = await call(s, "list_blackbox_events", {"order_id": 42})
    assert reader.queries[0][0] == {
        "table_id": "2", "selection_id": "47973", "order_id": uuid_order, "phase": "ATTEMPT"
    }
    assert ok is False and [e["seq"] for e in page["data"]["events"]["events"]] == [11]
    (event,) = page["data"]["events"]["events"]
    assert event["refs"]["table_id"] == 2 and event["refs"]["selection_id"] == 47973
    assert event["refs"]["order_id"] == uuid_order
    assert reader.queries[1][0] == {"severity": "ERROR", "causation_id": uid(5)}
    # Il seq 6 (causato da 5) è INFO, non ERROR.
    assert ok2 is False and page2["data"]["events"]["events"] == []
    assert reader.queries[2][0] == {"order_id": "42"}
    assert ok3 is False and [e["seq"] for e in page3["data"]["events"]["events"]] == [4, 5, 6]


async def test_thread_component_is_shown_as_recorded(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            ok, page = await call(s, "list_blackbox_events", {"event_type": "TASK_EXCEPTION"})
    assert ok is False, page
    (event,) = page["data"]["events"]["events"]
    assert event["component"] == "thread:Thread-3 (poller)" and event["severity"] == "ERROR"


_WINDOW = {"seq": 7, "from_ts": "2026-11-08T15:00:07.000123Z", "to_ts": "2026-11-08T15:00:09Z",
           "outcome": "UNKNOWN", "reason_code": "UNCLEAN_TERMINATION"}


async def test_time_gaps_from_bb1_are_shown_as_unrecorded_windows(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    reader.time_gaps = [_WINDOW]
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            ok, page = await call(s, "list_blackbox_events")
    assert ok is False, page
    assert page["data"]["events"]["unrecorded_windows"] == [
        {"seq": 7, "from_ts": "2026-11-08T15:00:07.000Z", "to_ts": "2026-11-08T15:00:09.000Z",
         "reason_code": "UNCLEAN_TERMINATION"}
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {**_WINDOW, "outcome": "VERIFIED"},  # una finestra non registrata non ha mai un esito noto
        {**_WINDOW, "to_ts": "2026-11-08T15:00:06Z"},  # estremi invertiti
        {**_WINDOW, "from_ts": "2026-11-08T16:00:07+01:00"},
        {**_WINDOW, "seq": 0},
        {k: v for k, v in _WINDOW.items() if k != "reason_code"},
        "UNCLEAN_TERMINATION",
    ],
)
async def test_a_bad_time_gap_is_an_error_never_hidden(tmp_path: Path, bad: Any) -> None:
    reader = FakeBlackboxQuery()
    reader.time_gaps = [bad]
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            is_error, page = await call(s, "list_blackbox_events")
    assert is_error is True and page["data"] is None


async def test_paging_through_the_whole_range(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    seen: list[int] = []
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            cursor = 0
            for _ in range(10):
                ok, page = await call(s, "list_blackbox_events", {"after_seq": cursor, "limit": 3})
                assert ok is False, page
                seen += [e["seq"] for e in page["data"]["events"]["events"]]
                cursor = page["data"]["events"]["next_after_seq"]
                if not cursor:
                    break
    assert seen == [1, 2, 3, 4, 5, 6, 7, 9, 10, 11]


async def test_every_mcp_read_is_recorded_once_with_its_count(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    with engine_api(tmp_path, reader) as (server, token_path):
        adapter = adapter_for(server, token_path)
        async with session_for(adapter) as s:
            await call(s, "list_blackbox_events", {"table_id": 1})
    reads = [r for r in reader.requests if r["route"] == "/v1/blackbox/events"]
    assert [r["phase"] for r in reads] == ["ATTEMPT", "RESULT"]
    assert reads[1]["returned"] == 3 and reads[1]["params"] == {"limit": 200, "table_id": 1}
    assert reads[0]["request_id"] == adapter.last_request_id


async def test_unavailable_register_gives_no_data_but_status_still_answers(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            reader.accept_requests = False
            no, payload = await call(s, "list_blackbox_events")
            ok, status = await call(s, "get_blackbox_status")
    assert (
        no is True
        and payload["error"]["code"] == "UPSTREAM_UNAVAILABLE"
        and payload["data"] is None
    )
    assert ok is False and status["data"]["blackbox"]["requests_unrecorded"] >= 1


def test_a_truthy_non_true_answer_is_not_an_accepted_record() -> None:
    class Sloppy(FakeBlackboxQuery):
        def request_hook(self, record: dict[str, Any]) -> bool:
            return 1  # type: ignore[return-value]

    assert make_request_hook(Sloppy())({"phase": "ATTEMPT"}) is False


async def test_time_range_reaches_the_reader_as_from_ts_to_ts(tmp_path: Path) -> None:
    reader = FakeBlackboxQuery()
    with engine_api(tmp_path, reader) as (server, token_path):
        async with session_for(adapter_for(server, token_path)) as s:
            ok, page = await call(
                s,
                "list_blackbox_events",
                {"since": "2026-11-08T15:00:02Z", "until": "2026-11-08T15:00:04.500Z"},
            )
    assert ok is False, page
    assert reader.queries[-1][0] == {
        "from_ts": "2026-11-08T15:00:02.000Z",
        "to_ts": "2026-11-08T15:00:04.500Z",
    }
    assert [e["seq"] for e in page["data"]["events"]["events"]] == [2, 3, 4]


def test_the_fake_rejects_unknown_filters_like_bb1() -> None:
    with pytest.raises(ValueError):
        FakeBlackboxQuery().query({"since": "x"}, 0, 10, external=True)
    with pytest.raises(ValueError):
        FakeBlackboxQuery().query({"severity_min": "WARNING"}, 0, 10, external=True)


def test_status_never_claims_what_bb1_does_not_report() -> None:
    """BB-1 non riporta lacune per seq né l'ultimo errore: mai «nessuna lacuna», mai inventato."""
    body = make_providers(FakeBlackboxQuery())["blackbox_status"]()
    assert body["available"] is True and body["degraded"] is False
    assert (body["first_seq"], body["last_seq"], body["sessions"]) == (1, 11, 1)
    assert {"gaps", "last_write_error_code", "corrupt_records"} <= set(body["not_reported"])
    assert body["gaps"] == []  # vuota per forma, ma dichiarata non riportata


@pytest.mark.parametrize(
    ("ok", "degraded"), [(False, False), (True, True), ("true", False), (None, False)]
)
def test_only_a_literal_ok_and_not_degraded_register_is_available(ok: Any, degraded: Any) -> None:
    class _Status(FakeBlackboxQuery):
        def status(self) -> dict[str, Any]:
            return {**super().status(), "ok": ok, "degraded": degraded}

    assert make_providers(_Status())["blackbox_status"]()["available"] is False


@pytest.mark.parametrize(
    "shape",
    [
        (record(1), []),  # la vecchia coppia (record, chain): non è la forma di BB-1
        {k: v for k, v in record(1).items()},  # senza causation_chain: catena mai «vuota» per caso
        {**record(1), "causation_chain": "x"},
    ],
)
def test_get_in_a_shape_other_than_bb1_is_an_error(shape: Any) -> None:
    class _Get(FakeBlackboxQuery):
        def get(self, event_id: str, chain_depth: int, *, external: bool = False) -> Any:
            return shape

    with pytest.raises(ValueError, match="get shape"):
        make_providers(_Get())["blackbox_event"](uid(1))


def test_a_missing_link_breaks_the_chain_where_it_is() -> None:
    reader = FakeBlackboxQuery()
    reader.records = [r for r in reader.records if r["seq"] != 5]  # la causa del 6 manca
    body = make_providers(reader)["blackbox_event"](uid(6))
    assert body["state"] == "OK" and body["chain"] == []
    assert body["chain_broken_at"] == uid(5)


def test_sessions_tell_a_crash_from_the_running_session() -> None:
    class _Two(FakeBlackboxQuery):
        def sessions(self) -> list[dict[str, Any]]:
            crashed = {**super().sessions()[0], "session_id": "s-old", "last_ts":
                       "2026-11-08T14:00:00.5Z", "started": "2026-11-08T13:00:00Z"}
            return [crashed, *super().sessions()]

    items = make_providers(_Two())["blackbox_sessions"]()["sessions"]
    assert [(i["session_id"], i["end_reason"], i["ended_at"]) for i in items] == [
        ("s-old", "CRASH_DETECTED", None),  # l'ora vera del crash non è nota
        (SESSION, "RUNNING", None),
    ]
    assert items[0]["last_event_at"] == "2026-11-08T14:00:00.500Z"


def test_without_the_current_session_id_an_unclean_session_is_an_error() -> None:
    class _NoCurrent(FakeBlackboxQuery):
        def status(self) -> dict[str, Any]:
            return {k: v for k, v in super().status().items() if k != "session_id"}

    with pytest.raises(ValueError, match="clean_shutdown"):
        make_providers(_NoCurrent())["blackbox_sessions"]()
