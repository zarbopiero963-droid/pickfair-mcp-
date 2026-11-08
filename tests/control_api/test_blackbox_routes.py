"""MCP-01o: route della scatola nera e registrazione di ogni richiesta (PF-BLACKBOX-01).

Sul server Control API reale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pickfair_control_api import server as server_mod
from pickfair_control_api.tokens import TokenStore
from tests.control_api import bodies
from tests.control_api.servers import control_api
from tests.control_api.test_server import request

pytestmark = pytest.mark.loopback


@pytest.fixture
def api(tmp_path: Path) -> Any:
    with control_api(tmp_path) as ctx:
        yield ctx


def wait_records(prov: Any, n: int) -> list[dict[str, Any]]:
    """Il record dell'esito si scrive dopo l'invio della risposta: attesa limitata."""
    import time

    deadline = time.monotonic() + 2.0
    while len(prov.records) < n and time.monotonic() < deadline:
        time.sleep(0.005)
    return prov.records


def get(api: Any, path: str, **headers: str) -> tuple[int, Any]:
    server, _s, token_path, _p = api
    status, _h, body = request(
        server.port, "GET", path, token=token_path.read_text(), headers=headers
    )
    return status, body


def test_events_route_passes_only_validated_filters(api: Any) -> None:
    _srv, _s, _t, prov = api
    status, body = get(
        api,
        "/v1/blackbox/events?since=2026-11-07T15:00:00Z&until=2026-11-07T17:00:00Z"
        "&origin=MCP&table_id=3&q=SETTINGS+risk",
    )
    assert status == 200 and [e["seq"] for e in body["events"]] == [1, 2]
    (filters,) = prov.bb_queries
    assert (
        filters["origin"] == "MCP" and filters["table_id"] == 3 and filters["q"] == "SETTINGS risk"
    )
    assert filters["limit"] == 200 and filters["since"].hour == 15


def test_events_route_without_query_uses_the_defaults(api: Any) -> None:
    assert get(api, "/v1/blackbox/events")[0] == 200
    assert api[3].bb_queries == [{"limit": 200}]


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/v1/blackbox/events?foo=1", "QUERY_PARAM"),
        ("/v1/blackbox/events?limit=1&limit=2", "QUERY_PARAM_REPEATED"),
        ("/v1/blackbox/events?origin=robot", "QUERY_VALUE"),
        (
            "/v1/blackbox/events?since=2026-11-07T17:00:00Z&until=2026-11-07T15:00:00Z",
            "QUERY_RANGE",
        ),
        ("/v1/blackbox/events?q=%00", "QUERY_ENCODING"),
        ("/v1/blackbox/events?customer_ref=x", "QUERY_PARAM"),
    ],
)
def test_bad_query_is_400_without_calling_the_core(api: Any, path: str, code: str) -> None:
    status, body = get(api, path)
    assert (status, body) == (400, {"error": {"code": code}})
    assert api[3].calls == 0


@pytest.mark.parametrize(
    "path",
    [
        "/v1/status?x=1",
        "/v1/blackbox/status?limit=1",
        "/v1/markets?limit=1",
        f"/v1/blackbox/events/{'a' * 32}?x=1",
    ],
)
def test_every_other_route_still_refuses_a_query(api: Any, path: str) -> None:
    assert get(api, path)[0] == 404
    assert api[3].calls == 0


def test_event_detail_route_validates_the_id(api: Any) -> None:
    assert get(api, f"/v1/blackbox/events/{'a' * 32}")[0] == 200
    for bad in ("A" * 32, "a" * 31, "a" * 33, "..", "g" * 32):
        assert get(api, f"/v1/blackbox/events/{bad}")[0] == 404


def test_one_record_per_request_never_one_per_event(api: Any) -> None:
    prov = api[3]
    prov.bb_events = lambda f: bodies.bb_events([bodies.bb_event(i) for i in range(1, 51)])
    status, body = get(api, "/v1/blackbox/events?limit=50", **{"X-Request-Id": "mcp-req-0001"})
    assert status == 200 and len(body["events"]) == 50
    assert [r["phase"] for r in wait_records(prov, 2)] == ["ATTEMPT", "RESULT"]  # 2 record, non 50
    attempt, result = prov.records
    assert attempt["route"] == "/v1/blackbox/events" and attempt["request_id"] == "mcp-req-0001"
    assert attempt["params"] == {"limit": 50} and attempt["status"] is None
    assert (result["status"], result["code"]) == (200, "OK") and result["duration_ms"] >= 0


def test_record_params_are_validated_values_never_raw_text(api: Any) -> None:
    get(api, "/v1/blackbox/events?since=2026-11-07T15:00:00Z&q=a+b")
    params = api[3].records[0]["params"]
    assert params == {"limit": 200, "q": "a b", "since": "2026-11-07T15:00:00.000Z"}


def test_rejected_requests_are_recorded_with_their_code(api: Any) -> None:
    server, _s, _t, prov = api
    request(server.port, "GET", "/v1/status", token="wrong-" + "z" * 50)
    get(api, "/v1/blackbox/events?foo=1")
    get(api, "/v1/nope")
    codes = [(r["phase"], r["status"], r["code"]) for r in wait_records(prov, 3)]
    assert codes == [
        ("RESULT", 401, "UNAUTHORIZED"),
        ("RESULT", 400, "QUERY_PARAM"),
        ("RESULT", 404, "NOT_FOUND"),
    ]
    assert prov.records[1]["route"] == "/v1/blackbox/events"


@pytest.mark.parametrize("hook", [False, "raise"])
def test_unrecordable_request_gets_no_data(api: Any, hook: Any) -> None:
    prov = api[3]

    def failing(record: dict[str, Any]) -> bool:
        raise RuntimeError("disk full")

    prov.hook_accepts = failing if hook == "raise" else False
    for path in ("/v1/status", "/v1/blackbox/events", f"/v1/blackbox/events/{'a' * 32}"):
        assert get(api, path) == (503, {"error": {"code": "BLACKBOX_UNAVAILABLE"}})
    assert prov.calls == 0  # nessun dato è uscito né è stato letto


def test_status_is_served_and_counts_the_unrecorded_requests(api: Any) -> None:
    prov = api[3]
    prov.hook_accepts = False
    get(api, "/v1/status")
    get(api, "/v1/status")
    status, body = get(api, "/v1/blackbox/status")
    assert status == 200 and body["requests_unrecorded"] == 3  # due rifiutate + questa


def test_request_id_must_be_well_formed(api: Any) -> None:
    for bad in ("short", "x" * 65, "bad id here", "a/b-12345678"):
        assert get(api, "/v1/status", **{"X-Request-Id": bad})[0] == 400
    assert get(api, "/v1/status", **{"X-Request-Id": "abcd-1234"})[0] == 200


def test_capabilities_list_the_blackbox_routes(api: Any) -> None:
    caps = get(api, "/v1/meta")[1]["capabilities"]
    assert {
        "GET /v1/blackbox/status",
        "GET /v1/blackbox/sessions",
        "GET /v1/blackbox/events",
        "GET /v1/blackbox/events/{event_id}",
    } <= set(caps)


# ------------------------------------------------------------- aggregazione (orologio iniettato)
class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_app(hook: Any, clock: Clock) -> Any:
    return server_mod._App({}, TokenStore("a" * 43), 1, request_hook=hook, clock=clock)


def test_over_the_rate_records_are_counted_and_carried() -> None:
    seen: list[dict[str, Any]] = []
    clock = Clock()
    app = make_app(lambda r: seen.append(r) or True, clock)
    for _ in range(int(server_mod.RECORD_BURST) + 5):
        assert app.record({"phase": "RESULT"}) is True
    assert len(seen) == int(server_mod.RECORD_BURST)  # 5 contati, non scritti
    clock.now = 1.0  # il ritmo ricarica il budget
    app.record({"phase": "RESULT"})
    assert seen[-1]["coalesced_before"] == 5 and app.unrecorded_count() == 0


def test_carried_counts_become_unrecorded_if_the_next_write_fails() -> None:
    clock = Clock()
    accept = {"ok": True}
    app = make_app(lambda r: accept["ok"], clock)
    for _ in range(int(server_mod.RECORD_BURST) + 3):
        app.record({"phase": "RESULT"})
    accept["ok"] = False
    clock.now = 1.0
    assert app.record({"phase": "RESULT"}) is False
    assert app.unrecorded_count() == 3  # i tre aggregati; la richiesta la conta il gestore


# ------------------------------------------------------------- seconda redazione (§5)
def test_sensitive_values_never_leave_even_if_the_engine_wrote_them(api: Any) -> None:
    prov = api[3]
    leak = bodies.bb_event(
        1,
        values_after={"api_key": "SECRET-1", "stake": "2.5"},
        values_before={"telegram_bot_token": "123:ABC"},
    )
    prov.bb_events = lambda f: bodies.bb_events([leak])
    status, body = get(api, "/v1/blackbox/events")
    assert status == 200 and "SECRET-1" not in str(body) and "123:ABC" not in str(body)
    ev = body["events"][0]
    assert ev["values_after"] == {"api_key": "[REDACTED]", "stake": "2.5"} and body["redacted"] == 2
    assert (
        leak["values_after"]["api_key"] == "SECRET-1"
    )  # nessuna modifica in place del dato del core


def test_detail_and_chain_are_redacted_too(api: Any) -> None:
    prov = api[3]
    detail = bodies.bb_event_detail()
    detail["event"]["values_after"] = {"password": "x"}
    detail["chain"][0]["values_before"] = {"customer_ref": "cref-1"}
    prov.bb_event = lambda eid: detail
    status, body = get(api, f"/v1/blackbox/events/{detail['event_id']}")
    assert status == 200 and body["redacted"] == 2 and "cref-1" not in str(body)


def test_sensitive_lists_are_the_same_on_both_sides() -> None:
    from pickfair_control_api.blackbox_redact import SENSITIVE_FRAGMENTS
    from pickfair_mcp.contract.models import BLACKBOX_SENSITIVE_FRAGMENTS

    assert SENSITIVE_FRAGMENTS == BLACKBOX_SENSITIVE_FRAGMENTS
