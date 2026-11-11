"""MCP-01j: contratto 1.6.0 — `ConfigResponse` (GET /v1/config), regole solo-MCP e schema.

Barriere contro le fughe: allowlist chiusa delle chiavi, nessun campo extra, nomi sensibili mai
accettati in `unlisted`, valore presente solo se SET, NOT_SET solo per i campi opzionali.
"""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest

from pickfair_control_api.contract import response_schema
from pickfair_control_api.schema_check import validate as server_validate
from pickfair_mcp.contract.models import CONFIG_KEYS, OPTIONAL_CONFIG_KEYS, SENSITIVE_NAME_FRAGMENTS
from pickfair_mcp.contract.parsing import UpstreamInvalidResponse, parse_config
from tests.control_api import bodies


def raw(body: dict[str, Any]) -> bytes:
    return json.dumps(body).encode()


def with_setting(key: str, **overrides: Any) -> dict[str, Any]:
    body = bodies.config()
    body["settings"] = [
        bodies.setting(k, **overrides) if k == key else s
        for k, s in zip(CONFIG_KEYS, body["settings"], strict=True)
    ]
    return body


def rejected(body: dict[str, Any]) -> None:
    with pytest.raises(UpstreamInvalidResponse):
        parse_config(raw(body))


def test_valid_body_is_accepted_by_both_sides() -> None:
    body = bodies.config(unlisted=["future_field_pct"], redacted=2)
    parsed = parse_config(raw(body))
    assert [s.key for s in parsed.settings or ()] == list(CONFIG_KEYS)
    server_validate(body, response_schema("config"))
    jsonschema.validate(body, response_schema("config"))


def test_allowlist_shape() -> None:
    assert len(CONFIG_KEYS) == 45 and OPTIONAL_CONFIG_KEYS < set(CONFIG_KEYS)
    assert set(CONFIG_KEYS.values()) == {"DECIMAL", "BOOL", "INT", "ENUM"}
    for key in CONFIG_KEYS:  # nessuna chiave dell'allowlist ha un nome da segreto
        assert not any(f in key for f in ("token", "secret", "password", "cert", "app_key"))


def test_unavailable_settings() -> None:
    parse_config(raw(bodies.config(settings=None, unavailable=["settings"])))
    rejected(bodies.config(settings=None, unavailable=[]))
    rejected(bodies.config(unavailable=["settings"]))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda b: b["settings"].pop(), id="missing-key"),
        pytest.param(lambda b: b["settings"].append(b["settings"][0]), id="duplicate-key"),
        pytest.param(lambda b: b["settings"].reverse(), id="wrong-order"),
        pytest.param(lambda b: b["settings"][0].update(key="app_key"), id="foreign-key"),
        pytest.param(lambda b: b["settings"][0].update(raw="x"), id="extra-field"),
        pytest.param(lambda b: b.update(password="x"), id="extra-top-level"),
        pytest.param(lambda b: b.update(consistency="PER_FIELD_NON_ATOMIC"), id="consistency"),
        pytest.param(lambda b: b.update(redacted=-1), id="negative-redacted"),
    ],
)
def test_structure_is_closed(mutate: Any) -> None:
    body = bodies.config()
    mutate(body)
    rejected(body)


@pytest.mark.parametrize(
    ("key", "overrides"),
    [
        ("table_count", {"kind": "DECIMAL", "value": "5"}),  # tipo diverso dal contratto
        ("max_daily_loss", {"state": "SET", "value": None}),  # SET senza valore
        ("max_daily_loss", {"state": "NOT_SET", "value": "0"}),  # NOT_SET con un valore
        ("max_daily_loss", {"state": "INVALID", "value": "0"}),  # INVALID mai convertito in 0
        ("commission_pct", {"state": "NOT_SET", "value": None}),  # non opzionale
        ("commission_pct", {"value": 4.5}),  # float, non stringa decimale
        ("commission_pct", {"value": "NaN"}),
        ("table_count", {"value": True}),  # bool non è un intero
        ("table_count", {"value": "5"}),
        ("allow_recovery", {"value": 1}),
        ("risk_profile", {"value": "YOLO"}),
    ],
)
def test_setting_rules(key: str, overrides: dict[str, Any]) -> None:
    rejected(with_setting(key, **overrides))


def test_invalid_and_not_set_are_accepted_without_value() -> None:
    parse_config(raw(with_setting("max_daily_loss", state="INVALID", value=None)))
    parse_config(raw(with_setting("commission_pct", state="INVALID", value=None)))
    parse_config(raw(with_setting("max_win", state="SET", value="250.5")))
    parse_config(raw(with_setting("max_recovery_chase_abs", state="SET", value="-1")))


@pytest.mark.parametrize(
    "name",
    [
        "betfair_app_key",
        "telegram_bot_token",
        "client_secret",
        "password_hash",
        "session_id",
        "api_url",
        "certfile",
        "auth_mode",
        "cookie_jar",
        "ssoid",
        "private_note",
        "pin_code",
        "credentials_path",
    ],
)
def test_sensitive_names_never_accepted_in_unlisted(name: str) -> None:
    assert any(f in name for f in SENSITIVE_NAME_FRAGMENTS)
    rejected(bodies.config(unlisted=[name]))


@pytest.mark.parametrize(
    "unlisted",
    [["future_field_pct", "future_field_pct"], ["table_count"], ["Stop"], ["x" * 65], ["a"] * 65],
)
def test_unlisted_rules(unlisted: list[str]) -> None:
    rejected(bodies.config(unlisted=unlisted))


def test_invalid_persisted_f18() -> None:
    """MCP-01m: chiavi persistite illeggibili (F-18) per nome; nomi sensibili mai elencati; null
    dichiarato."""
    parse_config(raw(bodies.config(invalid_persisted=["roserpina.profit_epsilon"])))
    parse_config(raw(bodies.config(invalid_persisted=None, unavailable=["invalid_persisted"])))
    parse_config(raw(bodies.config(invalid_persisted=["max_win", "roserpina.trailing_stop_pct"])))
    for bad in (
        ["roserpina.profit_epsilon", "roserpina.profit_epsilon"],
        ["telegram.bot_token"],
        ["betfair.app_key"],
        ["Roserpina.X"],
        ["a" * 70],
        ["roserpina.pin_code"],
        ["roserpina.api_secret"],
        ["other.max_win"],
    ):
        rejected(bodies.config(invalid_persisted=bad))
    rejected(bodies.config(invalid_persisted=None, unavailable=[]))
