"""K3: le bozze di route candidate sono ben formate ma NON attive (mandato owner 05/11/2026, punto 4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from pickfair_control_api.contract import ROUTE_SCHEMAS, load_descriptor
from pickfair_mcp.contract.routes import APPROVED_ROUTES
from pickfair_mcp.tools import build_default_registry
from pickfair_mcp.tools.catalog import APPROVED_TOOL_ROUTES

DRAFTS = Path(__file__).resolve().parents[2] / "docs" / "design" / "k3"
CANDIDATES = {"rc10_signals": "/v1/signals", "rc11_pnl": "/v1/pnl", "rc12_logs": "/v1/logs"}


def drafts() -> dict[str, dict[str, Any]]:
    return {p.name.split(".")[0]: json.loads(p.read_text()) for p in sorted(DRAFTS.glob("*.schema.json"))}


def closed(schema: Any) -> bool:
    if isinstance(schema, dict):
        if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
            return False
        return all(closed(v) for v in schema.values())
    if isinstance(schema, list):
        return all(closed(v) for v in schema)
    return True


def test_every_candidate_has_a_well_formed_closed_draft() -> None:
    found = drafts()
    assert set(found) == set(CANDIDATES)
    for name, schema in found.items():
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["x-status"] == "K3_DRAFT_NOT_RATIFIED_NOT_SERVED", name
        assert closed(schema), name


@pytest.mark.parametrize("path", sorted(CANDIDATES.values()))
def test_candidates_are_not_in_the_contract_or_the_mcp(path: str) -> None:
    assert all(r.path != path for r in APPROVED_ROUTES)
    assert path not in ROUTE_SCHEMAS
    assert all(path not in route for route in APPROVED_TOOL_ROUTES.values())
    assert all(spec.route != f"GET {path}" for spec in build_default_registry().specs())
    descriptor = load_descriptor()
    assert all(r[2] != path for r in descriptor["routes"])
    assert not any(n in descriptor["upstream_schemas"] for n in ("signals", "pnl", "logs"))


def test_draft_examples_validate_but_reject_free_text() -> None:
    schema = drafts()["rc12_logs"]
    ok = {"source": "core", "observed_at": 1.7e9, "consistency": "SINGLE_READ_TRANSACTION",
          "state": "OK", "reason": None, "entries": [{"at": 1.7e9, "kind": "ORDER_EVENT",
          "severity": "INFO", "code": "ORDER_PLACED", "correlation_id": "corr-1"}],
          "redacted": 0, "omitted": 0, "truncated": False, "next_cursor": None}
    jsonschema.validate(ok, schema)
    bad = json.loads(json.dumps(ok))
    bad["entries"][0]["message"] = "password=hunter2"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
    pnl = drafts()["rc11_pnl"]
    row = {"recorded_at": 1.7e9, "outcome": "APPLIED", "table_id": 1, "market_id": "1.2",
           "bet_id": "31415", "pnl": "1.5", "realized_applied": True}
    jsonschema.validate({"source": "core", "observed_at": 1.7e9, "consistency": "SINGLE_READ_TRANSACTION",
                         "state": "OK", "reason": None, "settlements": [row], "omitted": 0,
                         "truncated": False}, pnl)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"source": "core", "observed_at": 1.7e9, "consistency": "SINGLE_READ_TRANSACTION",
                             "state": "OK", "reason": None, "settlements": [{**row, "pnl": 1.5}],
                             "omitted": 0, "truncated": False}, pnl)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"source": "core", "observed_at": 1.7e9, "consistency": "SINGLE_READ_TRANSACTION",
                             "state": "OK", "reason": None,
                             "settlements": [{**row, "customer_ref": "cref"}], "omitted": 0,
                             "truncated": False}, pnl)


@pytest.mark.loopback
@pytest.mark.parametrize("path", sorted(CANDIDATES.values()))
def test_control_api_answers_404_for_candidates(tmp_path: Path, path: str) -> None:
    from tests.control_api.servers import control_api
    from tests.control_api.test_server import request

    with control_api(tmp_path) as (server, _s, token_path, providers):
        status, _h, body = request(server.port, "GET", path, token=token_path.read_text())
    assert (status, body) == (404, {"error": {"code": "NOT_FOUND"}})
    assert providers.calls == 0
