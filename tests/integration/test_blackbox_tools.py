"""MCP-01o: strumenti di lettura della scatola nera (PF-BLACKBOX-01) dal server MCP reale."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import pytest

from pickfair_mcp.adapters.http import HttpControlApiAdapter
from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter, StatusScenario
from pickfair_mcp.auth.token_file import LocalTokenFile
from tests.control_api import bodies
from tests.control_api.servers import control_api
from tests.integration.test_market_tools import call, session_for

pytestmark = pytest.mark.anyio

TOOLS = (
    "get_blackbox_status",
    "list_blackbox_sessions",
    "list_blackbox_events",
    "get_blackbox_event",
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_simulated_blackbox_tools_are_read_only_and_valid() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        results = {
            "get_blackbox_status": await call(s, "get_blackbox_status"),
            "list_blackbox_sessions": await call(s, "list_blackbox_sessions"),
            "list_blackbox_events": await call(
                s, "list_blackbox_events", {"table_id": 1, "origin": "STRATEGY"}
            ),
            "get_blackbox_event": await call(s, "get_blackbox_event", {"event_id": f"{3:032x}"}),
        }
    for name in TOOLS:
        is_error, payload = results[name]
        assert is_error is False, (name, payload)
        jsonschema.validate(payload, tools[name].outputSchema)
        assert tools[name].annotations.readOnlyHint is True  # type: ignore[union-attr]
        assert tools[name].annotations.destructiveHint is False  # type: ignore[union-attr]
    events = results["list_blackbox_events"][1]["data"]["events"]["events"]
    assert [e["phase"] for e in events] == ["OBSERVATION", "ATTEMPT", "RESULT"]
    assert events[1]["outcome"] == "PENDING"  # il tentativo non è mai un'operazione confermata
    chain = results["get_blackbox_event"][1]["data"]["event"]["chain"]
    assert [c["event_type"] for c in chain] == ["ORDER_PLACE_ATTEMPT"]  # perché è successo
    assert adapter.blackbox_queries == [(("table_id", "1"), ("origin", "STRATEGY"))]


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("list_blackbox_events", {"since": "2026-11-07 15:00"}),  # mai un'ora locale
        ("list_blackbox_events", {"since": "2026-11-07T15:00:00+01:00"}),
        (
            "list_blackbox_events",
            {"since": "2026-11-07T17:00:00Z", "until": "2026-11-07T15:00:00.500Z"},
        ),
        ("list_blackbox_events", {"limit": 501}),
        ("list_blackbox_events", {"origin": "robot"}),
        ("list_blackbox_events", {"q": "a&limit=500"}),  # nessuna iniezione di query
        ("list_blackbox_events", {"customer_ref": "c"}),
        ("get_blackbox_event", {"event_id": "../x"}),
        ("get_blackbox_event", {}),
    ],
)
async def test_bad_input_never_reaches_the_adapter(tool: str, args: dict[str, Any]) -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as s:
        is_error, payload = await call(s, tool, args)
    assert is_error is True and payload["error"]["code"] == "INVALID_REQUEST"
    assert adapter.blackbox_calls == 0


async def test_close_bounds_with_and_without_milliseconds_are_ordered_by_instant() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as s:
        ok = await call(
            s,
            "list_blackbox_events",
            {"since": "2026-11-07T15:00:00Z", "until": "2026-11-07T15:00:00.500Z"},
        )
    assert ok[0] is False  # 15:00:00.000 viene prima di 15:00:00.500 anche se «Z» > «.»


@pytest.mark.parametrize(
    "scenario",
    [
        StatusScenario.EXTRA_FIELD,
        StatusScenario.INJECTION_TEXT,
        StatusScenario.INCONSISTENT,
        StatusScenario.WRONG_SOURCE,
    ],
)
async def test_bad_blackbox_bodies_are_rejected(scenario: StatusScenario) -> None:
    async with session_for(SimulatedControlApiAdapter(status_scenario=scenario)) as s:
        is_error, payload = await call(s, "list_blackbox_events")
    if scenario is StatusScenario.INJECTION_TEXT:
        # Il testo resta un dato (motivazione registrata), mai un'istruzione: è valido e non esegue
        # nulla.
        assert (
            is_error is False
            and "IGNORE PREVIOUS" in payload["data"]["events"]["events"][0]["reason"]
        )
    else:
        assert is_error is True and payload["data"] is None


@pytest.mark.loopback
async def test_real_control_api_round_trip_records_the_mcp_request(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        adapter = HttpControlApiAdapter(
            port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
        )
        async with session_for(adapter) as s:
            ok = await call(
                s,
                "list_blackbox_events",
                {
                    "since": "2026-11-07T15:00:00Z",
                    "until": "2026-11-07T17:00:00Z",
                    "q": "risk stop",
                },
            )
        assert ok[0] is False, ok
        (filters,) = providers.bb_queries
        assert (
            filters["q"] == "risk stop"
            and filters["since"].hour == 15
            and filters["until"].hour == 17
        )
        attempts = [
            r
            for r in providers.records
            if r["phase"] == "ATTEMPT" and r["route"] == "/v1/blackbox/events"
        ]
        assert len(attempts) == 1 and attempts[0]["request_id"] == adapter.last_request_id
        assert adapter.last_request_id is not None and adapter.last_request_id.startswith("mcp-")


@pytest.mark.loopback
async def test_unrecordable_request_is_an_unavailable_upstream_never_data(tmp_path: Path) -> None:
    with control_api(tmp_path) as (server, _s, token_path, providers):
        adapter = HttpControlApiAdapter(
            port=server.port, token_file=LocalTokenFile(token_path), timeout_s=2.0
        )
        async with session_for(adapter) as s:
            providers.hook_accepts = (
                lambda r: r.get("route") == "/v1/meta"
            )  # solo l'handshake è registrabile
            is_error, payload = await call(s, "list_blackbox_events")
    assert is_error is True and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_UNAVAILABLE"


@pytest.mark.parametrize(
    "query",
    [
        (("customer_ref", "x"),),
        (("q", "a&b"),),
        (("limit", "1\n"),),
        (("q", "a" * 65),),
        (("since", "%00"),),
    ],
)
async def test_http_adapter_never_sends_an_unvalidated_query(tmp_path: Path, query: Any) -> None:
    """Seconda barriera: chiamato direttamente, l'adapter non costruisce query fuori whitelist."""
    adapter = HttpControlApiAdapter(
        port=1, token_file=LocalTokenFile(tmp_path / "t"), timeout_s=0.1
    )
    with pytest.raises(ValueError):
        await adapter.get_blackbox_events_raw(query)


def test_mcp_and_server_whitelists_are_the_same() -> None:
    from pickfair_control_api.blackbox_query import ALLOWED
    from pickfair_mcp.adapters.http import _BLACKBOX_PARAMS
    from pickfair_mcp.tools.blackbox import ListBlackboxEventsInput

    assert _BLACKBOX_PARAMS == ALLOWED == frozenset(ListBlackboxEventsInput.model_fields)


def test_body_builders_match_the_server_schema() -> None:
    from pickfair_control_api.contract import response_schema
    from pickfair_control_api.schema_check import validate

    validate(bodies.bb_events(), response_schema("blackbox_events"))
    validate(bodies.bb_event_detail(), response_schema("blackbox_event"))


async def test_a_core_that_ignores_the_cursor_is_not_trusted() -> None:
    # Il simulato restituisce sempre i seq 1-3: con after_seq=2 la pagina ripete eventi già letti.
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as s:
        is_error, payload = await call(s, "list_blackbox_events", {"after_seq": 2})
        ok = await call(s, "list_blackbox_events", {"after_seq": 0})
    assert is_error is True and payload["data"] is None
    assert payload["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    assert ok[0] is False
