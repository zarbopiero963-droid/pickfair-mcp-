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


@pytest.mark.parametrize(
    "raised",
    [
        KeyboardInterrupt(),
        BaseExceptionGroup("task group", [KeyboardInterrupt()]),
        BaseExceptionGroup("outer", [BaseExceptionGroup("inner", [KeyboardInterrupt()])]),
        BaseExceptionGroup("mixed", [BrokenPipeError(), KeyboardInterrupt()]),
    ],
)
def test_interrupt_is_classified_even_inside_exception_groups(
    raised: BaseException, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SIGINT durante l'elaborazione arriva avvolto in un BaseExceptionGroup di anyio."""
    from pickfair_mcp import cli

    def fake_run(*_: object) -> None:
        raise raised

    monkeypatch.setattr(cli.anyio, "run", fake_run)
    monkeypatch.setattr(cli, "configure_stderr_logging", lambda: None)
    monkeypatch.setattr(cli.os, "dup2", lambda *_: None)
    assert main(["serve"]) == 130


def test_transport_failure_is_not_reported_as_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pickfair_mcp import cli

    def fake_run(*_: object) -> None:
        raise BaseExceptionGroup("task group", [BrokenPipeError()])

    monkeypatch.setattr(cli.anyio, "run", fake_run)
    monkeypatch.setattr(cli, "configure_stderr_logging", lambda: None)
    monkeypatch.setattr(cli.os, "dup2", lambda *_: None)
    assert main(["serve"]) == 1


def test_sigint_is_classified_even_when_the_runtime_loses_the_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Riproduce il caso reale: SIGINT arriva, ma anyio termina con BrokenResourceError."""
    import signal as signal_module

    import anyio as anyio_module

    from pickfair_mcp import cli

    def fake_run(*_: object) -> None:
        handler = signal_module.getsignal(signal_module.SIGINT)
        assert callable(handler)
        try:
            handler(signal_module.SIGINT, None)  # consegna di SIGINT al processo
        except KeyboardInterrupt:
            pass  # il runtime la assorbe durante la chiusura dei task
        raise BaseExceptionGroup("task group", [anyio_module.BrokenResourceError()])

    before = signal_module.getsignal(signal_module.SIGINT)
    monkeypatch.setattr(cli.anyio, "run", fake_run)
    monkeypatch.setattr(cli, "configure_stderr_logging", lambda: None)
    monkeypatch.setattr(cli.os, "dup2", lambda *_: None)
    assert main(["serve"]) == 130
    assert signal_module.getsignal(signal_module.SIGINT) is before  # gestore ripristinato
