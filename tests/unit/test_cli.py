"""CLI in-process: argomenti, BLOCKED_CORE e contract-info."""

from __future__ import annotations

import json

import pytest

from pickfair_mcp import cli as cli_module
from pickfair_mcp.cli import main

REAL_FORCED_EXIT = cli_module._force_interrupted_exit


@pytest.fixture(autouse=True)
def forced_exits(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Nessun test in-process può raggiungere il vero os._exit."""
    calls: list[bool] = []
    monkeypatch.setattr(cli_module, "_force_interrupted_exit", lambda: calls.append(True))
    return calls


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
    tracker = InterruptTracker(lambda: None)
    try:
        tracker.install()
        handler = signal_module.getsignal(signal_module.SIGINT)
        assert handler is not runner_handler
        handler(signal_module.SIGINT, None)  # type: ignore[operator]
        assert tracker.seen is True
        assert calls == [signal_module.SIGINT]  # delega al gestore del Runner
        tracker.uninstall()
        assert signal_module.getsignal(signal_module.SIGINT) is runner_handler
    finally:
        tracker.disarm()
        signal_module.signal(signal_module.SIGINT, previous)


def test_tracker_leaves_ignored_or_default_disposition_alone() -> None:
    import signal as signal_module

    from pickfair_mcp.cli import InterruptTracker

    for disposition in (signal_module.SIG_IGN, signal_module.SIG_DFL):
        previous = signal_module.signal(signal_module.SIGINT, disposition)
        try:
            tracker = InterruptTracker(lambda: None)
            tracker.install()
            assert signal_module.getsignal(signal_module.SIGINT) is disposition
            tracker.uninstall()
            assert signal_module.getsignal(signal_module.SIGINT) is disposition
        finally:
            signal_module.signal(signal_module.SIGINT, previous)


def _fire_sigint(tracker: object) -> None:
    import signal as signal_module

    previous = signal_module.signal(signal_module.SIGINT, lambda *_: None)
    try:
        tracker.install()  # type: ignore[attr-defined]
        signal_module.getsignal(signal_module.SIGINT)(signal_module.SIGINT, None)  # type: ignore[misc,operator]
        tracker.uninstall()  # type: ignore[attr-defined]
    finally:
        signal_module.signal(signal_module.SIGINT, previous)


def test_sigint_watchdog_exits_when_the_runner_never_returns() -> None:
    """F4: con stdin aperto il Runner resta in attesa; il watchdog chiude il processo."""
    import threading

    from pickfair_mcp.cli import InterruptTracker

    expired = threading.Event()
    tracker = InterruptTracker(expired.set, grace_s=0.05)
    _fire_sigint(tracker)
    assert expired.wait(5)


def test_disarmed_watchdog_never_fires() -> None:
    import threading

    from pickfair_mcp.cli import InterruptTracker

    expired = threading.Event()
    tracker = InterruptTracker(expired.set, grace_s=0.2)
    _fire_sigint(tracker)
    tracker.disarm()
    assert not expired.wait(0.6)


def test_watchdog_is_not_armed_without_sigint() -> None:
    import threading

    from pickfair_mcp.cli import InterruptTracker

    expired = threading.Event()
    tracker = InterruptTracker(expired.set, grace_s=0.05)
    tracker.install()
    tracker.uninstall()
    assert not expired.wait(0.3)
    tracker.disarm()  # libera il thread del watchdog
    assert not expired.wait(0.3)


def test_sigint_handler_starts_no_thread() -> None:
    """Il gestore gira tra due bytecode del thread principale: avviare un thread lì
    prende i lock interni di threading e può bloccarsi per sempre."""
    import signal as signal_module
    import threading

    from pickfair_mcp.cli import InterruptTracker

    previous = signal_module.signal(signal_module.SIGINT, lambda *_: None)
    tracker = InterruptTracker(lambda: None, grace_s=30)
    try:
        tracker.install()
        handler = signal_module.getsignal(signal_module.SIGINT)
        before = threading.active_count()
        handler(signal_module.SIGINT, None)  # type: ignore[operator]
        handler(signal_module.SIGINT, None)  # type: ignore[operator]
        assert threading.active_count() == before
        assert tracker.seen is True
        tracker.uninstall()
    finally:
        tracker.disarm()
        signal_module.signal(signal_module.SIGINT, previous)


def test_main_disarms_the_watchdog_on_every_exit_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import anyio as anyio_module

    from pickfair_mcp import cli

    disarmed: list[bool] = []
    monkeypatch.setattr(cli.InterruptTracker, "disarm", lambda self: disarmed.append(True))
    _patch_serve_env(monkeypatch)

    def ok_run(*_: object) -> None:
        return None

    def broken_run(*_: object) -> None:
        raise BaseExceptionGroup("task group", [anyio_module.BrokenResourceError()])

    for fake_run in (ok_run, broken_run):
        monkeypatch.setattr(cli.anyio, "run", fake_run)
        cli.main(["serve"])
    assert disarmed == [True, True]


def test_forced_exit_writes_the_interrupted_audit_and_exits_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    from pickfair_mcp import cli

    stops: list[tuple[str, int]] = []
    exits: list[int] = []

    def fake_stop(outcome: str, code: int) -> int:
        stops.append((outcome, code))
        return code

    monkeypatch.setattr(cli, "_abnormal_stop", fake_stop)
    monkeypatch.setattr(os, "_exit", exits.append)
    REAL_FORCED_EXIT()
    assert stops == [("interrupted", 130)]
    assert exits == [130]


def _interrupted_on_normal_exit(tracker: object) -> None:
    tracker.seen = True  # type: ignore[attr-defined]


def _interrupted_with_exception(tracker: object) -> None:
    tracker.seen = True  # type: ignore[attr-defined]
    raise KeyboardInterrupt


def _interrupt_without_tracker(tracker: object) -> None:
    raise BaseExceptionGroup("task group", [KeyboardInterrupt()])


@pytest.mark.parametrize(
    "outcome",
    [_interrupted_on_normal_exit, _interrupted_with_exception, _interrupt_without_tracker],
)
def test_every_interrupted_exit_goes_through_the_forced_exit_once(
    outcome: object, monkeypatch: pytest.MonkeyPatch, forced_exits: list[bool]
) -> None:
    """B1: dopo un secondo SIGINT anyio.run esce, ma il thread di stdin resta vivo e la
    finalizzazione dell'interprete lo attenderebbe: main non deve tornare normalmente."""
    from pickfair_mcp import cli

    def fake_run(_serve: object, _adapter: object, _timeout: object, tracker: object) -> None:
        outcome(tracker)  # type: ignore[operator]

    monkeypatch.setattr(cli.anyio, "run", fake_run)
    _patch_serve_env(monkeypatch)
    assert main(["serve"]) == 130
    assert forced_exits == [True]


def test_transport_error_does_not_use_the_forced_exit(
    monkeypatch: pytest.MonkeyPatch, forced_exits: list[bool]
) -> None:
    from pickfair_mcp import cli

    def fake_run(*_: object) -> None:
        raise BaseExceptionGroup("task group", [BrokenPipeError()])

    monkeypatch.setattr(cli.anyio, "run", fake_run)
    _patch_serve_env(monkeypatch)
    assert main(["serve"]) == 1
    assert forced_exits == []


def test_stop_interrupted_runs_once_even_with_the_watchdog() -> None:
    import threading

    from pickfair_mcp.cli import InterruptTracker

    calls: list[bool] = []
    tracker = InterruptTracker(lambda: calls.append(True), grace_s=0.05)
    _fire_sigint(tracker)
    tracker.stop_interrupted()
    tracker.stop_interrupted()
    assert not threading.Event().wait(0.3)  # lascia scadere il watchdog
    assert calls == [True]


def test_stop_holds_the_lock_until_the_exit_completes() -> None:
    """Mentre il watchdog sta uscendo, main non può scrivere un'altra chiusura."""
    import threading

    from pickfair_mcp.cli import InterruptTracker

    exiting = threading.Event()
    release = threading.Event()

    def slow_exit() -> None:
        exiting.set()
        release.wait(5)

    tracker = InterruptTracker(slow_exit, grace_s=0.01)
    _fire_sigint(tracker)
    assert exiting.wait(5)
    other = threading.Thread(target=tracker.disarm, daemon=True)
    other.start()
    other.join(0.3)
    assert other.is_alive()  # bloccato sul lock finché l'uscita non termina
    release.set()
    other.join(5)
    assert not other.is_alive()


def test_interrupt_grace_is_short() -> None:
    from pickfair_mcp.cli import INTERRUPT_GRACE_S

    assert 0 < INTERRUPT_GRACE_S <= 5
