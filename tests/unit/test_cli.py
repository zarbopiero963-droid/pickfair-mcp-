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


def _patch_serve_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from pickfair_mcp import cli

    monkeypatch.setattr(cli, "configure_stderr_logging", lambda: None)
    monkeypatch.setattr(cli.os, "dup2", lambda *_: None)


def test_sigint_is_classified_even_when_the_runtime_loses_the_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso reale: SIGINT registrato, ma anyio termina con BrokenResourceError."""
    import anyio as anyio_module

    from pickfair_mcp import cli

    def fake_run(_serve: object, _adapter: object, _timeout: object, tracker: object) -> None:
        tracker.seen = True  # type: ignore[attr-defined]
        raise BaseExceptionGroup("task group", [anyio_module.BrokenResourceError()])

    monkeypatch.setattr(cli.anyio, "run", fake_run)
    _patch_serve_env(monkeypatch)
    assert main(["serve"]) == 130


def test_interrupt_on_the_normal_exit_path_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    from pickfair_mcp import cli

    def fake_run(_serve: object, _adapter: object, _timeout: object, tracker: object) -> None:
        tracker.seen = True  # type: ignore[attr-defined]

    monkeypatch.setattr(cli.anyio, "run", fake_run)
    _patch_serve_env(monkeypatch)
    assert main(["serve"]) == 130


def test_asyncio_runner_keeps_its_own_sigint_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """F1: il Runner di asyncio gestisce SIGINT solo se trova default_int_handler."""
    import signal as signal_module

    from pickfair_mcp import cli

    seen: list[object] = []

    def fake_run(*_: object) -> None:
        seen.append(signal_module.getsignal(signal_module.SIGINT))

    previous = signal_module.signal(signal_module.SIGINT, signal_module.default_int_handler)
    try:
        monkeypatch.setattr(cli.anyio, "run", fake_run)
        _patch_serve_env(monkeypatch)
        main(["serve"])
    finally:
        signal_module.signal(signal_module.SIGINT, previous)
    assert seen == [signal_module.default_int_handler]


def test_inherited_ignored_sigint_stays_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """F2: se il processo padre ignora SIGINT, il server non deve riattivarlo."""
    import signal as signal_module

    from pickfair_mcp import cli

    seen: list[object] = []

    def fake_run(*_: object) -> None:
        seen.append(signal_module.getsignal(signal_module.SIGINT))

    previous = signal_module.signal(signal_module.SIGINT, signal_module.SIG_IGN)
    try:
        monkeypatch.setattr(cli.anyio, "run", fake_run)
        _patch_serve_env(monkeypatch)
        main(["serve"])
        after = signal_module.getsignal(signal_module.SIGINT)
    finally:
        signal_module.signal(signal_module.SIGINT, previous)
    assert seen == [signal_module.SIG_IGN]
    assert after is signal_module.SIG_IGN


def test_tracker_records_delegates_and_restores() -> None:
    import signal as signal_module

    from pickfair_mcp.cli import InterruptTracker

    calls: list[int] = []

    def runner_handler(signum: int, frame: object) -> None:
        calls.append(signum)

    previous = signal_module.signal(signal_module.SIGINT, runner_handler)
    try:
        tracker = InterruptTracker()
        tracker.install()
        handler = signal_module.getsignal(signal_module.SIGINT)
        assert handler is not runner_handler
        handler(signal_module.SIGINT, None)  # type: ignore[operator]
        assert tracker.seen is True
        assert calls == [signal_module.SIGINT]  # delega al gestore del Runner
        tracker.uninstall()
        assert signal_module.getsignal(signal_module.SIGINT) is runner_handler
    finally:
        signal_module.signal(signal_module.SIGINT, previous)


def test_tracker_leaves_ignored_or_default_disposition_alone() -> None:
    import signal as signal_module

    from pickfair_mcp.cli import InterruptTracker

    for disposition in (signal_module.SIG_IGN, signal_module.SIG_DFL):
        previous = signal_module.signal(signal_module.SIGINT, disposition)
        try:
            tracker = InterruptTracker()
            tracker.install()
            assert signal_module.getsignal(signal_module.SIGINT) is disposition
            tracker.uninstall()
            assert signal_module.getsignal(signal_module.SIGINT) is disposition
        finally:
            signal_module.signal(signal_module.SIGINT, previous)
