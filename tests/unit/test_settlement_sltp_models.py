"""MCP-01h: contratto 1.5.0 — SL/TP per tavolo (get_exposure), settlement
(get_reconciliation_status), barriere di cashout (get_status). PASS e BLOCK per ogni regola.

SL/TP: sul `main` del core nessun percorso arma SL/TP (F-02 di Claude D non è ancora integrato),
quindi oggi lo stato reale è NOT_ARMED; il contratto è già compatibile con gli importi di F-02.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from pickfair_mcp.contract.parsing import (
    UpstreamInvalidResponse,
    parse_exposure,
    parse_reconciliation_status,
    parse_status,
)
from tests.control_api import bodies


def raw(body: dict[str, Any]) -> bytes:
    return json.dumps(body).encode()


def table_with(sl_tp: dict[str, Any]) -> dict[str, Any]:
    return bodies.exposure(tables=[bodies.table(1, sl_tp=sl_tp)])


ARMED = {
    "state": "ARMED",
    "stop_loss": "2.5",
    "take_profit": "5",
    "stop_loss_pct": "25",
    "take_profit_pct": "50",
    "trailing_stop_pct": None,
}


def test_default_table_is_not_armed() -> None:
    t = parse_exposure(raw(bodies.exposure())).tables[0]  # type: ignore[index]
    assert t.sl_tp.state == "NOT_ARMED" and t.sl_tp.stop_loss is None


def test_armed_table_parses_with_decimal_amounts() -> None:
    t = parse_exposure(raw(table_with(ARMED))).tables[0]  # type: ignore[index]
    assert (t.sl_tp.stop_loss, t.sl_tp.take_profit) == ("2.5", "5")


@pytest.mark.parametrize(
    "sl_tp",
    [
        {**ARMED, "state": "NOT_ARMED"},  # importi presenti ma «non armato»
        {**ARMED, "stop_loss": None, "take_profit": None},  # armato senza importi
        {**ARMED, "state": "SAFE"},
        {**ARMED, "stop_loss": 2.5},  # float
        {**ARMED, "stop_loss": "-1"},  # importo negativo
        {**ARMED, "stop_loss_pct": "1e2"},
        {**ARMED, "trailing": "ACTIVE"},  # campo inventato: il core non applica il trailing
        {**ARMED, "state": "TRIGGERED", "stop_loss": None, "take_profit": None},
    ],
)
def test_incoherent_sl_tp_is_rejected(sl_tp: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_exposure(raw(table_with(sl_tp)))


def test_unknown_sl_tp_may_carry_no_amounts() -> None:
    sl_tp = {
        "state": "UNKNOWN",
        "stop_loss": None,
        "take_profit": None,
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "trailing_stop_pct": None,
    }
    assert parse_exposure(raw(table_with(sl_tp))).tables[0].sl_tp.state == "UNKNOWN"  # type: ignore[index]


SETTLEMENT = bodies.settlement()


def test_settlement_section_parses() -> None:
    r = parse_reconciliation_status(raw(bodies.reconciliation()))
    assert r.settlement is not None and r.settlement.unrecorded_settlements == 0


@pytest.mark.parametrize(
    "override",
    [
        {"unrecorded_settlements": -1},
        {"held_batches": True},
        {
            "effects": {
                "held": 1,
                "not_realized": 0,
                "by_outcome": [{"outcome": "held", "count": 1}],
            }
        },
        {
            "effects": {
                "held": 1,
                "not_realized": 0,
                "by_outcome": [{"outcome": "HELD", "count": 1}, {"outcome": "HELD", "count": 2}],
            }
        },
        {
            "checkpoints": {
                "by_stage": [{"stage": "DONE", "count": 1}],
                "cycle_ambiguous": 0,
                "submit_ambiguous": 0,
            }
        },
        {"payload": {}},  # payload grezzo del settlement: mai esposto
        {"customer_refs": ["a"]},
        {"sim_settlements": None},  # null non dichiarato
    ],
)
def test_incoherent_settlement_is_rejected(override: dict[str, Any]) -> None:
    body = bodies.reconciliation(settlement={**SETTLEMENT, **override})
    with pytest.raises(UpstreamInvalidResponse):
        parse_reconciliation_status(raw(body))


def test_held_count_must_match_the_outcome_breakdown() -> None:
    eff = {"held": 2, "not_realized": 2, "by_outcome": [{"outcome": "HELD", "count": 1}]}
    with pytest.raises(UpstreamInvalidResponse):
        parse_reconciliation_status(
            raw(bodies.reconciliation(settlement={**SETTLEMENT, "effects": eff}))
        )


def test_unavailable_settlement_parts_are_declared() -> None:
    s = {
        **SETTLEMENT,
        "effects": None,
        "checkpoints": None,
        "sim_settlements": None,
        "unavailable": ["effects", "checkpoints", "sim_settlements"],
    }
    r = parse_reconciliation_status(raw(bodies.reconciliation(settlement=s)))
    assert r.settlement.effects is None  # type: ignore[union-attr]


def test_cashout_barriers_are_counted_in_status() -> None:
    eng = bodies.engine()
    eng["queues"] = {**eng["queues"], "cashout_barriers": 2}
    s = parse_status(raw(bodies.status(engine=eng)))
    assert s.engine.queues.cashout_barriers == 2  # type: ignore[union-attr]
    eng["queues"]["cashout_barriers"] = -1
    with pytest.raises(UpstreamInvalidResponse):
        parse_status(raw(bodies.status(engine=eng)))
