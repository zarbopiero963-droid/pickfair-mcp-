"""MCP-01o: whitelist dei parametri di GET /v1/blackbox/events (PF-BLACKBOX-01)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pickfair_control_api.blackbox_query import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    QueryRejected,
    parse_events_query,
)


def test_empty_query_gets_only_the_default_limit() -> None:
    assert parse_events_query("") == {"limit": DEFAULT_LIMIT}


def test_the_owner_question_from_15_to_17() -> None:
    f = parse_events_query("since=2026-11-07T15:00:00Z&until=2026-11-07T17:00:00.000Z&limit=500")
    assert f["since"] == datetime(2026, 11, 7, 15, tzinfo=UTC)
    assert f["until"] == datetime(2026, 11, 7, 17, tzinfo=UTC)
    assert f["limit"] == MAX_LIMIT


def test_every_filter_is_validated_and_typed() -> None:
    f = parse_events_query(
        "after_seq=0&session_id=s-1&table_id=3&market_id=1.234567&order_id=42&bet_id=31415"
        "&strategy=roserpina&correlation_id=c_9&category=ORDER&event_type=ORDER_PLACED"
        "&origin=MCP&severity=WARNING&outcome=UNKNOWN&phase=RESULT&selection_id=47972"
        "&causation_id=0123456789abcdef0123456789abcdef"
    )
    assert (f["after_seq"], f["table_id"], f["order_id"], f["selection_id"]) == (0, 3, 42, 47972)
    assert (f["origin"], f["severity"], f["outcome"], f["phase"]) == (
        "MCP", "WARNING", "UNKNOWN", "RESULT"
    )
    assert f["causation_id"] == "0123456789abcdef0123456789abcdef"


def test_order_id_is_a_ledger_integer_or_the_engine_uuid() -> None:
    """BB-1: id del ledger, oppure str(uuid4()) del motore col DB degradato (resta stringa)."""
    uid = "0f8fad5b-d9cb-469f-a165-70867728950e"
    assert parse_events_query("order_id=" + uid)["order_id"] == uid
    assert parse_events_query("order_id=7")["order_id"] == 7


@pytest.mark.parametrize(
    ("query", "code"),
    [
        ("foo=1", "QUERY_PARAM"),  # parametro sconosciuto
        ("limit", "QUERY_PARAM"),  # senza valore
        ("limit=1&limit=2", "QUERY_PARAM_REPEATED"),
        ("limit=0", "QUERY_VALUE"),
        ("limit=501", "QUERY_VALUE"),
        ("limit=01", "QUERY_VALUE"),
        ("after_seq=-1", "QUERY_VALUE"),
        ("table_id=0", "QUERY_VALUE"),
        ("market_id=1.2/../x", "QUERY_VALUE"),  # risalita: fuori pattern
        ("market_id=..%2Fx", "QUERY_VALUE"),
        ("origin=mcp", "QUERY_VALUE"),  # vocabolario chiuso, maiuscolo
        ("severity=FATAL", "QUERY_VALUE"),
        ("severity_min=WARNING", "QUERY_PARAM"),  # non esiste nel lettore di BB-1
        ("q=risk", "QUERY_PARAM"),  # idem: nessuna ricerca testuale
        ("phase=DONE", "QUERY_VALUE"),
        ("selection_id=0", "QUERY_VALUE"),
        ("causation_id=0123456789ABCDEF0123456789ABCDEF", "QUERY_VALUE"),  # minuscolo
        # 32 hex, senza trattini
        ("causation_id=01234567-89ab-cdef-0123-456789abcdef", "QUERY_VALUE"),
        ("order_id=0f8fad5bd9cb469fa16570867728950e", "QUERY_VALUE"),  # uuid senza trattini
        ("order_id=0F8FAD5B-D9CB-469F-A165-70867728950E", "QUERY_VALUE"),  # maiuscolo
        ("outcome=FAILED_OR_NOT", "QUERY_VALUE"),
        ("since=2026-11-07 15:00:00Z", "QUERY_ENCODING"),  # spazio letterale
        ("since=2026-11-07T15:00:00", "QUERY_VALUE"),  # senza Z: mai un'ora locale ambigua
        ("since=2026-11-07T15:00:00%2B01:00", "QUERY_VALUE"),
        ("since=2026-02-30T00:00:00Z", "QUERY_VALUE"),
        ("since=2026-11-07T17:00:00Z&until=2026-11-07T15:00:00Z", "QUERY_RANGE"),
        ("since=2026-01-01T00:00:00Z&until=2026-03-01T00:00:00Z", "QUERY_RANGE"),
        ("strategy=%00x", "QUERY_ENCODING"),  # byte di controllo
        ("strategy=%C3%A8", "QUERY_ENCODING"),  # fuori ASCII
        ("strategy=a%2", "QUERY_ENCODING"),  # percent incompleto
        ("strategy=" + "a" * 33, "QUERY_VALUE"),
        ("strategy=a;b", "QUERY_VALUE"),
        ("strategy=" + "a" * 1100, "QUERY_TOO_LONG"),
        ("strategy=Roserpina", "QUERY_VALUE"),
        ("customer_ref=abc", "QUERY_PARAM"),  # mai un filtro su dati sensibili
    ],
)
def test_rejections_carry_a_fixed_code_never_the_input(query: str, code: str) -> None:
    with pytest.raises(QueryRejected) as exc:
        parse_events_query(query)
    assert str(exc.value) == code
    assert query not in str(exc.value)


def test_range_of_exactly_31_days_is_allowed() -> None:
    f = parse_events_query("since=2026-01-01T00:00:00Z&until=2026-02-01T00:00:00Z")
    assert (f["until"] - f["since"]).days == 31
