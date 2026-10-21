"""CLI in-process: argomenti, BLOCKED_CORE e contract-info."""

from __future__ import annotations

import json

import pytest

from pickfair_mcp.cli import main


def test_contract_info(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["contract-info"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["tools"] == ["get_meta"]
    assert info["live_commands"] == "DISABLED"


def test_http_adapter_is_blocked_core(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["serve", "--adapter", "http"]) == 2
    captured = capsys.readouterr()
    assert "BLOCKED_CORE" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("value", ["nan", "inf", "0", "31", "-1"])
def test_invalid_timeout_exits_with_usage_error(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["serve", "--upstream-timeout", value])
    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""
