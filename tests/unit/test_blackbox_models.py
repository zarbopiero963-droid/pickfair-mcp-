"""MCP-01o: modelli di lettura della scatola nera (PF-BLACKBOX-01)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pickfair_mcp.contract.parsing import (
    UpstreamInvalidResponse,
    parse_blackbox_event,
    parse_blackbox_events,
    parse_blackbox_sessions,
    parse_blackbox_status,
)
from tests.control_api import bodies


def raw(b: dict[str, Any]) -> bytes:
    return json.dumps(b).encode()


def test_valid_bodies_parse() -> None:
    assert [e.seq for e in parse_blackbox_events(raw(bodies.bb_events())).events or ()] == [1, 2]
    detail = parse_blackbox_event(raw(bodies.bb_event_detail()))
    assert detail.event is not None and detail.chain[0].phase == "ATTEMPT"
    assert len(parse_blackbox_sessions(raw(bodies.bb_sessions())).sessions or ()) == 2
    assert parse_blackbox_status(raw(bodies.bb_status())).gaps[0].kind == "LOST"


def ev(**over: Any) -> dict[str, Any]:
    return bodies.bb_events([bodies.bb_event(1, **over)])


@pytest.mark.parametrize(
    "body",
    [
        # Un tentativo non è mai mostrato come confermato.
        ev(phase="ATTEMPT", outcome="VERIFIED"),
        ev(phase="ATTEMPT", outcome="FAILED"),
        # Segreti: un nome sensibile esce solo redatto.
        ev(values_after={"api_key": "abc"}),
        ev(values_before={"telegram_bot_token": "123:ABC"}),
        ev(values_after={"customer_ref": "cref-secret"}),
        # Un campo dichiarato non registrato non porta un valore.
        ev(not_recorded=["reason"], reason="x"),
        ev(not_recorded=["reason", "reason"], reason=None),
        # Un evento non causa se stesso.
        ev(causation_id=f"{1:032x}"),
        # Forme.
        ev(ts_utc="2026-11-07T15:00:00Z"),  # senza millisecondi
        ev(ts_utc="2026-11-07T15:00:00.123+01:00"),  # mai un'ora locale
        ev(origin="ROBOT"),
        ev(outcome="AMBIGUOUS"),  # l'esito ignoto è UNKNOWN
        ev(event_type="order placed"),
        ev(
            refs={
                "table_id": 1,
                "market_id": "1.2",
                "order_id": 1,
                "bet_id": "1",
                "strategy": "x",
                "customer_ref": "c",
            }
        ),
        ev(values_after={"stake": 2.5}),  # nessun float: importi come stringhe
        ev(values_after={f"v{i}": "1" for i in range(33)}),
        # Ordine, duplicati, paginazione coerente.
        bodies.bb_events([bodies.bb_event(2), bodies.bb_event(1)]),
        bodies.bb_events([bodies.bb_event(1), bodies.bb_event(1)]),
        bodies.bb_events([bodies.bb_event(1), bodies.bb_event(2, event_id=f"{1:032x}")]),
        bodies.bb_events(truncated=True),  # troncato senza cursore
        bodies.bb_events(next_after_seq=1, truncated=True),  # il cursore è l'ultimo seq
        bodies.bb_events(next_after_seq=2),  # cursore senza troncamento
        bodies.bb_events(as_of_seq=None),  # nullo non dichiarato
        bodies.bb_events(as_of_seq=1),  # evento oltre la posizione scritta
        {**bodies.bb_events(), "events": None},  # nullo non dichiarato
        {**bodies.bb_events(), "events": None, "unavailable": ["events"], "redacted": 1},
        bodies.bb_events(gaps_in_range=[{"from_seq": 5, "to_seq": 3, "kind": "LOST"}]),
        bodies.bb_events(
            gaps_in_range=[
                {"from_seq": 1, "to_seq": 3, "kind": "LOST"},
                {"from_seq": 3, "to_seq": 4, "kind": "CORRUPT"},
            ]
        ),
        bodies.bb_events(gaps_in_range=[{"from_seq": 1, "to_seq": 3, "kind": "MISSING"}]),
    ],
)
def test_events_rejected(body: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_blackbox_events(raw(body))


def test_redacted_sensitive_value_and_unavailable_null_are_accepted() -> None:
    body = ev(
        values_after={"api_key": "[REDACTED]", "stake": "2.5"}, not_recorded=["reason"], reason=None
    )
    e = (parse_blackbox_events(raw(body)).events or ())[0]
    assert e.values_after == {"api_key": "[REDACTED]", "stake": "2.5"}


def test_unavailable_events_are_declared_never_an_empty_list() -> None:
    body = {
        **bodies.bb_events(),
        "events": None,
        "unavailable": ["events", "as_of_seq"],
        "as_of_seq": None,
    }
    assert parse_blackbox_events(raw(body)).events is None


def test_truncated_page_with_its_cursor() -> None:
    body = bodies.bb_events(next_after_seq=2, truncated=True)
    assert parse_blackbox_events(raw(body)).next_after_seq == 2


@pytest.mark.parametrize(
    "body",
    [
        bodies.bb_event_detail(state="NOT_FOUND"),  # evento con NOT_FOUND
        bodies.bb_event_detail(event_id=f"{9:032x}"),  # id diverso
        bodies.bb_event_detail(chain=[bodies.bb_event(7)]),  # catena non segue la causa
        bodies.bb_event_detail(chain=[], chain_broken_at=f"{5:032x}"),  # rottura non sulla causa
        bodies.bb_event_detail(state="NOT_FOUND", event=None, chain=[], redacted=1),
    ],
)
def test_event_detail_rejected(body: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_blackbox_event(raw(body))


def test_chain_broken_at_the_missing_cause_is_declared() -> None:
    body = bodies.bb_event_detail(chain=[], chain_broken_at=f"{1:032x}")
    assert parse_blackbox_event(raw(body)).chain_broken_at == f"{1:032x}"


@pytest.mark.parametrize(
    "body",
    [
        bodies.bb_sessions(sessions=[bodies.bb_session(end_reason="CLEAN_STOP", ended_at=None)]),
        bodies.bb_sessions(
            sessions=[bodies.bb_session(end_reason="UNRECORDED")]
        ),  # fine registrata?
        bodies.bb_sessions(sessions=[bodies.bb_session(ended_at="2026-11-07T13:00:00.000Z")]),
        bodies.bb_sessions(sessions=[bodies.bb_session(first_seq=9, last_seq=1)]),
        bodies.bb_sessions(sessions=[bodies.bb_session(), bodies.bb_session()]),
        bodies.bb_sessions(
            sessions=[
                bodies.bb_session("a", end_reason="RUNNING", ended_at=None),
                bodies.bb_session("b", end_reason="RUNNING", ended_at=None),
            ]
        ),
    ],
)
def test_sessions_rejected(body: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_blackbox_sessions(raw(body))


@pytest.mark.parametrize(
    "body",
    [
        bodies.bb_status(available=False),  # indisponibile senza motivo
        bodies.bb_status(first_seq=None),
        bodies.bb_status(first_seq=10, last_seq=1),
        bodies.bb_status(gaps=[], gaps_truncated=True),
        bodies.bb_status(not_reported=["corrupt_records"]),  # dichiarato ma con valore
        bodies.bb_status(not_reported=["sessions", "sessions"], sessions=None),
        bodies.bb_status(requests_unrecorded=-1),
    ],
)
def test_status_rejected(body: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_blackbox_status(raw(body))


def test_unavailable_register_with_its_reason() -> None:
    body = bodies.bb_status(available=False, last_write_error_code="DISK_FULL")
    assert parse_blackbox_status(raw(body)).last_write_error_code == "DISK_FULL"
