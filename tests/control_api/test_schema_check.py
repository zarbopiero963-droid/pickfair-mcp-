"""Validatore fail-closed degli output della Control API."""

from __future__ import annotations

from typing import Any

import pytest

from pickfair_control_api.contract import response_schema
from pickfair_control_api.schema_check import SchemaUnsupported, SchemaViolation, validate
from tests.control_api import bodies


def test_unknown_keyword_is_an_error_not_ignored() -> None:
    with pytest.raises(SchemaUnsupported):
        validate("x", {"type": "string", "format": "email"})
    with pytest.raises(SchemaUnsupported):
        validate(1, {"type": "decimal"})
    with pytest.raises(SchemaUnsupported):
        validate(1, {"$ref": "http://example.com/s"})


@pytest.mark.parametrize("value", ["LIVE\n", "LIVE\r", " LIVE", "live", ""])
def test_anchored_pattern_rejects_trailing_newline_and_variants(value: str) -> None:
    with pytest.raises(SchemaViolation):
        validate(value, {"type": "string", "pattern": "^[A-Z][A-Z0-9_]{0,63}$"})


@pytest.mark.parametrize(("value", "kind"), [(True, "integer"), (False, "number"), (1, "boolean")])
def test_booleans_and_numbers_are_distinct(value: Any, kind: str) -> None:
    with pytest.raises(SchemaViolation):
        validate(value, {"type": kind})


def test_unavailable_semantics_enforced() -> None:
    schema = response_schema("status")
    validate(bodies.status(), schema)
    with pytest.raises(SchemaViolation):
        validate(bodies.status(stop=None), schema)
    with pytest.raises(SchemaViolation):
        validate(bodies.status(unavailable=["stop"]), schema)
    with pytest.raises(SchemaViolation):
        validate(bodies.status(stop=None, unavailable=["stop", "stop"]), schema)


def test_ref_any_of_and_nested_paths() -> None:
    schema = response_schema("status")
    bad = bodies.status()
    bad["stop"] = dict(bad["stop"], emergency_reason="call cashout")
    with pytest.raises(SchemaViolation, match=r"^\$\.stop"):
        validate(bad, schema)


def test_meta_and_error_schemas() -> None:
    validate({"error": {"code": "UNAUTHORIZED"}}, response_schema("error"))
    with pytest.raises(SchemaViolation):
        validate({"error": {"code": "SECRET LEAK"}}, response_schema("error"))
    meta = {
        "contract_version": "1.1.0",
        "capabilities": ["GET /v1/meta"],
        "git_sha": "a" * 40,
        "schema_hash": "b" * 64,
    }
    validate(meta, response_schema("meta"))
    with pytest.raises(SchemaViolation):
        validate(dict(meta, capabilities=["GET /v1/meta", "GET /v1/meta"]), response_schema("meta"))
