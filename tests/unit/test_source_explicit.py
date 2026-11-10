"""C-AUD-10 (PF-OWNER-MCP-SOURCE-EXPLICIT-20261110): la sorgente dati è sempre esplicita.

Senza `--adapter` il server non parte: nessun default simulato, nessuna sorgente dedotta dalle
altre opzioni o dall'ambiente, nessun adapter costruito, nessun trasporto avviato. Vale a ogni
avvio, quindi anche dopo un riavvio. Sorgente invalida → errore di argomenti (exit 2).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pickfair_mcp import cli
from pickfair_mcp.cli import EXIT_USAGE, main

SOURCE_REQUIRED = "CONFIG_ERROR: SOURCE_REQUIRED"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def no_transport(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[object]]:
    """Registra ogni tentativo di costruire un adapter o di avviare il trasporto."""
    attempts: list[object] = []

    def fake_run(*args: object) -> None:
        attempts.append(("anyio.run", args))

    def fake_sim(*args: object, **kwargs: object) -> object:
        attempts.append(("simulated", args, kwargs))
        return object()  # un adapter qualsiasi: il trasporto è finto

    def fake_http(*args: object, **kwargs: object) -> object:
        attempts.append(("http", args, kwargs))
        return object()

    monkeypatch.setattr(cli.anyio, "run", fake_run)
    monkeypatch.setattr(cli, "SimulatedControlApiAdapter", fake_sim)
    monkeypatch.setattr(cli, "HttpControlApiAdapter", fake_http)
    monkeypatch.setattr(cli, "configure_stderr_logging", lambda: None)
    yield attempts


@pytest.mark.parametrize(
    "args",
    [
        ["serve"],
        ["serve", "--sim-scenario", "compatible"],
        ["serve", "--sim-status-scenario", "sim_ready"],
        ["serve", "--upstream-timeout", "2"],
        # le opzioni http non implicano la sorgente CONTROL_API
        ["serve", "--control-api-port", "8765", "--control-api-token-file", "/nonexistent/t"],
    ],
)
def test_missing_source_refuses_startup(
    args: list[str],
    no_transport: list[object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(args) == EXIT_USAGE
    captured = capsys.readouterr()
    assert captured.err.strip() == SOURCE_REQUIRED
    assert captured.out == ""
    assert no_transport == []  # nessun adapter, nessun trasporto: mai dati simulati


def test_environment_never_selects_the_source(
    monkeypatch: pytest.MonkeyPatch,
    no_transport: list[object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("PICKFAIR_MCP_ADAPTER", "PICKFAIR_MCP_SOURCE", "PICKFAIR_ADAPTER", "ADAPTER"):
        monkeypatch.setenv(name, "simulated")
    assert main(["serve"]) == EXIT_USAGE
    assert capsys.readouterr().err.strip() == SOURCE_REQUIRED
    assert no_transport == []


def test_every_start_requires_the_source_again(
    no_transport: list[object], capsys: pytest.CaptureFixture[str]
) -> None:
    """Un avvio esplicito riuscito non lascia uno stato che renda implicito il successivo."""
    assert main(["serve", "--adapter", "simulated"]) == 0
    assert [a[0] for a in no_transport] == ["simulated", "anyio.run"]
    capsys.readouterr()
    no_transport.clear()
    assert main(["serve"]) == EXIT_USAGE
    assert capsys.readouterr().err.strip() == SOURCE_REQUIRED
    assert no_transport == []


@pytest.mark.parametrize("value", ["betfair", "SIMULATED ", "", "core", "auto"])
def test_invalid_source_is_rejected(
    value: str, no_transport: list[object], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["serve", "--adapter", value])
    assert exc.value.code == EXIT_USAGE
    assert no_transport == []
    assert capsys.readouterr().out == ""


def test_explicit_sources_are_still_accepted(
    no_transport: list[object], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["serve", "--adapter", "simulated"]) == 0
    assert no_transport[0][0] == "simulated"
    # http esplicito arriva alla propria validazione (porta e token), mai al simulato
    assert main(["serve", "--adapter", "http"]) == EXIT_USAGE
    assert capsys.readouterr().err.strip().endswith("HTTP_ADAPTER_REQUIRES_PORT_AND_TOKEN_FILE")
    assert [a[0] for a in no_transport] == ["simulated", "anyio.run"]


def test_real_process_without_source_exits_and_prints_only_the_code(tmp_path: Path) -> None:
    """Processo reale (ogni riavvio è un processo nuovo): nessuna riga JSON-RPC su stdout."""
    proc = subprocess.run(
        [sys.executable, "-m", "pickfair_mcp", "serve"],
        input="",
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO_ROOT / "src")},
        check=False,
    )
    assert proc.returncode == EXIT_USAGE
    assert proc.stderr.strip() == SOURCE_REQUIRED
    assert proc.stdout == ""
