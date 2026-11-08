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
        "&origin=MCP&severity_min=WARNING&outcome=UNKNOWN&q=MCP+SETTINGS%3Arisk"
    )
    assert (f["after_seq"], f["table_id"], f["order_id"]) == (0, 3, 42)
    assert f["q"] == "MCP SETTINGS:risk" and f["origin"] == "MCP" and f["outcome"] == "UNKNOWN"


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
        ("severity_min=FATAL", "QUERY_VALUE"),
        ("outcome=FAILED_OR_NOT", "QUERY_VALUE"),
        ("since=2026-11-07 15:00:00Z", "QUERY_ENCODING"),  # spazio letterale
        ("since=2026-11-07T15:00:00", "QUERY_VALUE"),  # senza Z: mai un'ora locale ambigua
        ("since=2026-11-07T15:00:00%2B01:00", "QUERY_VALUE"),
        ("since=2026-02-30T00:00:00Z", "QUERY_VALUE"),
        ("since=2026-11-07T17:00:00Z&until=2026-11-07T15:00:00Z", "QUERY_RANGE"),
        ("since=2026-01-01T00:00:00Z&until=2026-03-01T00:00:00Z", "QUERY_RANGE"),
        ("q=%00x", "QUERY_ENCODING"),  # byte di controllo
        ("q=%C3%A8", "QUERY_ENCODING"),  # fuori ASCII
        ("q=a%2", "QUERY_ENCODING"),  # percent incompleto
        ("q=" + "a" * 65, "QUERY_VALUE"),
        ("q=a;b", "QUERY_VALUE"),
        ("q=" + "a" * 1100, "QUERY_TOO_LONG"),
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
