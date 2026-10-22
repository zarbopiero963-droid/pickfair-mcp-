"""Configurazione sicura (solo loopback) e audit redatto."""

from __future__ import annotations

import json
import logging
import sys
import threading

import pytest

from pickfair_mcp import audit
from pickfair_mcp.config import ConfigError, validate_control_api_url, validate_timeout


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8770", "http://127.0.0.1:8770/", "http://127.5.6.7:1", "http://[::1]:9000"],
)
def test_loopback_urls_are_accepted(url: str) -> None:
    assert validate_control_api_url(url) == url.rstrip("/")


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://localhost:8770", "CONFIG_HOST_NOT_IP"),  # un nome può risolvere altrove
        ("http://0.0.0.0:8770", "CONFIG_HOST_NOT_LOOPBACK"),
        ("http://192.168.1.10:8770", "CONFIG_HOST_NOT_LOOPBACK"),
        ("http://10.0.0.1:8770", "CONFIG_HOST_NOT_LOOPBACK"),
        ("https://api.betfair.com", "CONFIG_SCHEME"),
        ("http://127.0.0.1", "CONFIG_PORT"),  # porta obbligatoria
        ("http://127.0.0.1:0", "CONFIG_PORT"),
        ("http://127.0.0.1:65536", "CONFIG_URL_INVALID"),
        ("http://127.0.0.1:70000", "CONFIG_URL_INVALID"),
        ("http://user:pw@127.0.0.1:8770", "CONFIG_USERINFO"),
        ("http://user@127.0.0.1:8770", "CONFIG_USERINFO"),
        ("http://:pw@127.0.0.1:8770", "CONFIG_USERINFO"),
        ("http://127.0.0.1:8770/v1", "CONFIG_PATH"),
        ("http://127.0.0.1:8770?x=1", "CONFIG_PATH"),
        ("http://127.0.0.1:8770#f", "CONFIG_PATH"),
        ("ftp://127.0.0.1:21", "CONFIG_SCHEME"),
        ("file:///etc/passwd", "CONFIG_SCHEME"),
        ("http://[::ffff:8.8.8.8]:80", "CONFIG_HOST_NOT_LOOPBACK"),
        ("http://[::ffff:127.0.0.1]:80", "CONFIG_HOST_NOT_LOOPBACK"),
        ("http://127.0.0.1.nip.io:80", "CONFIG_HOST_NOT_IP"),
        ("", "CONFIG_SCHEME"),
        ("http://2130706433:80", "CONFIG_HOST_NOT_IP"),
        ("http://:80", "CONFIG_HOST_NOT_IP"),
        ("http://[::1:80", "CONFIG_URL_INVALID"),
    ],
)
def test_non_loopback_or_malformed_urls_are_rejected(url: str, code: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        validate_control_api_url(url)
    assert excinfo.value.code == code
    assert str(excinfo.value) == code


def test_highest_port_is_accepted() -> None:
    assert validate_control_api_url("http://127.0.0.1:65535") == "http://127.0.0.1:65535"


@pytest.mark.parametrize("value", [0.05, 1, 5.0, 30])
def test_valid_timeouts(value: float) -> None:
    assert validate_timeout(value) == float(value)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (0, "CONFIG_TIMEOUT:timeout out of range"),
        (0.01, "CONFIG_TIMEOUT:timeout out of range"),
        (-1, "CONFIG_TIMEOUT:timeout out of range"),
        (30.01, "CONFIG_TIMEOUT:timeout out of range"),
        (float("nan"), "CONFIG_TIMEOUT:timeout out of range"),
        (float("inf"), "CONFIG_TIMEOUT:timeout out of range"),
        (True, "CONFIG_TIMEOUT:timeout must be a number of seconds"),
        ("5", "CONFIG_TIMEOUT:timeout must be a number of seconds"),
    ],
)
def test_invalid_timeouts(value: object, code: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        validate_timeout(value)
    assert excinfo.value.code == code


def test_audit_keeps_only_allowlisted_fields(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=audit.LOGGER_NAME)
    audit.audit_event(
        "tool_call",
        request_id="req_x",
        tool="get_meta",
        outcome="ok",
        token="super-secret-token",
        password="pw-123",
        app_key="AK-999",
        payload={"nested": "secret"},
    )
    line = caplog.records[-1].getMessage()
    record = json.loads(line)
    assert record["event"] == "tool_call"
    assert record["request_id"] == "req_x"
    for secret in ("super-secret-token", "pw-123", "AK-999", "nested"):
        assert secret not in line
    assert set(record) <= {"event", "ts", *audit.ALLOWED_FIELDS}


def test_audit_truncates_and_sanitizes_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=audit.LOGGER_NAME)
    audit.audit_event("tool_call", tool="x" * 1000, outcome="ok\nINJECT")
    record = json.loads(caplog.records[-1].getMessage())
    assert len(record["tool"]) <= audit.MAX_VALUE_LEN
    assert "\n" not in record["outcome"]


def test_audit_drops_non_primitive_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=audit.LOGGER_NAME)
    audit.audit_event("tool_call", tool=["a"], outcome={"b": 1}, epoch=3, ok=True)
    record = json.loads(caplog.records[-1].getMessage())
    assert "tool" not in record
    assert "outcome" not in record
    assert record["epoch"] == 3
    assert record["ok"] is True


def test_audit_rejects_unknown_event_names(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=audit.LOGGER_NAME)
    audit.audit_event("rm -rf /", tool="get_meta")
    record = json.loads(caplog.records[-1].getMessage())
    assert record["event"] == "unknown_event"


def test_serve_logging_keeps_only_audit_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    audit_logger = logging.getLogger(audit.LOGGER_NAME)
    saved = (
        list(root.handlers),
        root.level,
        logging.lastResort,
        list(audit_logger.handlers),
        audit_logger.level,
        audit_logger.propagate,
        sys.excepthook,
        sys.unraisablehook,
        threading.excepthook,
    )
    try:
        # Configurazione «rumorosa» preesistente, come quella di una libreria.
        root.handlers[:] = [logging.StreamHandler(sys.stderr)]
        root.setLevel(logging.DEBUG)
        audit.configure_stderr_logging()
        logging.getLogger("mcp.server.lowlevel.server").error("input_value='hunter2-sdk'")
        logging.getLogger("anything").critical("hunter2-lib")
        audit.audit_event("tool_call", tool="get_meta")
        err = capsys.readouterr().err
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])
        logging.lastResort = saved[2]
        audit_logger.handlers[:] = saved[3]
        audit_logger.setLevel(saved[4])
        audit_logger.propagate = saved[5]
        sys.excepthook = saved[6]
        sys.unraisablehook = saved[7]
        threading.excepthook = saved[8]
        logging.captureWarnings(False)
    assert "hunter2" not in err
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["tool"] == "get_meta"


def test_reasons_are_bounded_with_explicit_marker() -> None:
    from pickfair_mcp.envelope import MAX_REASONS, failure
    from pickfair_mcp.errors import ErrorCode, ToolError

    many = tuple(f"CAPABILITY_MISSING:GET /v1/x{i}" for i in range(40))
    body = failure(
        "req_" + "0" * 32, "get_meta", ToolError(ErrorCode.CONTRACT_INCOMPATIBLE, reasons=many)
    )
    reasons = body["error"].details.reasons
    assert len(reasons) == MAX_REASONS
    assert reasons[0] == many[0]
    assert reasons[-1] == "REASONS_TRUNCATED"
    exact = many[:MAX_REASONS]
    body = failure(
        "req_" + "0" * 32, "get_meta", ToolError(ErrorCode.CONTRACT_INCOMPATIBLE, reasons=exact)
    )
    assert body["error"].details.reasons == exact
