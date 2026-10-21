"""Riga di comando: `serve` (server MCP su stdio) e `contract-info`.

`serve` scrive su stdout soltanto il protocollo MCP; diagnostica e audit vanno su stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from types import FrameType
from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from pickfair_mcp import __version__
from pickfair_mcp.adapters.simulated import Scenario, SimulatedControlApiAdapter
from pickfair_mcp.audit import audit_event, configure_stderr_logging
from pickfair_mcp.config import BLOCKED_CORE_MESSAGE, ConfigError, validate_timeout
from pickfair_mcp.contract.routes import APPROVED_ROUTES
from pickfair_mcp.contract.version import SUPPORTED_CONTRACT_VERSION, contract_schema_hash
from pickfair_mcp.policy.exposure import LIVE_COMMANDS, MUTATION_EXPOSURE
from pickfair_mcp.server import build_server
from pickfair_mcp.tools import build_default_registry

EXIT_USAGE = 2
EXIT_INTERRUPTED = 130
EXIT_TRANSPORT = 1
STDOUT_FD = 1
INTERRUPT_GRACE_S = 2.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pickfair-mcp", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="avvia il server MCP su stdio")
    serve.add_argument("--adapter", choices=("simulated", "http"), default="simulated")
    serve.add_argument(
        "--sim-scenario",
        choices=[s.value for s in Scenario],
        default=Scenario.COMPATIBLE.value,
        help="solo adapter simulato: scenario deterministico",
    )
    serve.add_argument("--upstream-timeout", type=float, default=5.0)
    sub.add_parser("contract-info", help="stampa versione e schema hash del contratto supportato")
    return parser


class InterruptTracker:
    """Registra SIGINT senza sostituire la gestione del Runner di asyncio.

    Il Runner installa il proprio gestore solo se trova ``default_int_handler`` e lo
    rimuove solo se lo ritrova al suo posto: per questo il tracker si installa dentro
    il loop, avvolge il gestore corrente e lo ripristina prima che il Runner chiuda.
    Una disposizione ignorata o di default (SIG_IGN, SIG_DFL) resta invariata.

    SIGINT arma anche un watchdog: l'SDK legge stdin in un thread non cancellabile e
    non daemon, quindi a riposo, con stdin aperto, né il Runner né la finalizzazione
    dell'interprete terminano prima della riga successiva o di EOF. Ogni chiusura
    «interrupted» passa quindi da ``stop_interrupted``, una sola volta e sotto lock: la
    chiama ``main`` oppure, se ``main`` non arriva entro ``grace_s``, il watchdog. Il thread
    del watchdog parte con ``install``: il gestore del segnale non avvia thread e non
    prende lock propri, si limita a un solo ``Event.set``.
    """

    def __init__(self, on_expire: Callable[[], None], grace_s: float = INTERRUPT_GRACE_S) -> None:
        self.seen = False
        self._previous: Callable[[int, FrameType | None], Any] | None = None
        self._on_expire = on_expire
        self._grace_s = grace_s
        self._signalled = threading.Event()
        self._finished = threading.Event()
        self._lock = threading.Lock()

    def install(self) -> None:
        current = signal.getsignal(signal.SIGINT)
        if not callable(current):
            return
        self._previous = current

        def _record_and_delegate(signum: int, frame: FrameType | None) -> Any:
            if not self.seen:  # un secondo SIGINT non rientra in Event.set
                self.seen = True
                self._signalled.set()
            return current(signum, frame)

        threading.Thread(target=self._watch, name="sigint-watchdog", daemon=True).start()
        signal.signal(signal.SIGINT, _record_and_delegate)

    def uninstall(self) -> None:
        if self._previous is not None:
            signal.signal(signal.SIGINT, self._previous)
            self._previous = None

    def _watch(self) -> None:
        self._signalled.wait()
        if not self._finished.wait(self._grace_s):
            self.stop_interrupted()

    def stop_interrupted(self) -> None:
        """Esegue ``on_expire`` al più una volta; il lock resta tenuto fino all'uscita."""
        with self._lock:
            if not self._finished.is_set():
                self._finished.set()
                self._on_expire()

    def disarm(self) -> None:
        with self._lock:
            self._finished.set()
        self._signalled.set()  # libera il watchdog anche se SIGINT non è mai arrivato


async def _serve(
    adapter: SimulatedControlApiAdapter, timeout_s: float, tracker: InterruptTracker
) -> None:
    server = build_server(adapter, timeout_s=timeout_s)
    tracker.install()
    try:
        await _run_stdio(server)
    finally:
        tracker.uninstall()


async def _run_stdio(server: Server[Any, Any]) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def _contract_info() -> int:
    info = {
        "server_version": __version__,
        "supported_contract_version": SUPPORTED_CONTRACT_VERSION,
        "schema_hash": contract_schema_hash(),
        "routes": len(APPROVED_ROUTES),
        "tools": list(build_default_registry().names()),
        "mutation_exposure": MUTATION_EXPOSURE,
        "live_commands": LIVE_COMMANDS,
    }
    print(json.dumps(info, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "contract-info":
        return _contract_info()
    try:
        timeout_s = validate_timeout(args.upstream_timeout)
    except ConfigError as exc:
        parser.error(f"--upstream-timeout: {exc}")
    if args.adapter == "http":
        print(BLOCKED_CORE_MESSAGE, file=sys.stderr)
        return EXIT_USAGE
    configure_stderr_logging()
    adapter = SimulatedControlApiAdapter(Scenario(args.sim_scenario))
    audit_event(
        "server_start",
        server_version=__version__,
        adapter_kind=adapter.kind,
        certified=adapter.certified,
        contract_version=SUPPORTED_CONTRACT_VERSION,
        mutation_exposure=MUTATION_EXPOSURE,
    )
    tracker = InterruptTracker(_force_interrupted_exit)
    try:
        anyio.run(_serve, adapter, timeout_s, tracker)
    except BaseException as exc:  # noqa: BLE001 - es. pipe chiusa dal client: niente traceback
        if tracker.seen or _is_interrupt(exc):
            tracker.stop_interrupted()  # non ritorna: il thread di stdin può essere ancora vivo
            return EXIT_INTERRUPTED
        tracker.disarm()
        return _abnormal_stop("transport_error", EXIT_TRANSPORT)
    if tracker.seen:
        tracker.stop_interrupted()
        return EXIT_INTERRUPTED
    tracker.disarm()
    audit_event("server_stop", server_version=__version__, outcome="ok")
    return 0


def _is_interrupt(exc: BaseException) -> bool:
    """SIGINT può arrivare avvolto (anche più volte) in un BaseExceptionGroup di anyio."""
    if isinstance(exc, KeyboardInterrupt):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_interrupt(inner) for inner in exc.exceptions)
    return False


def _abnormal_stop(outcome: str, code: int) -> int:
    """Chiusura anomala: solo una riga di audit su stderr, stdout scollegato."""
    audit_event("server_stop", server_version=__version__, outcome=outcome)
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, STDOUT_FD)  # evita errori di flush a fine processo
    except (OSError, ValueError):
        pass
    return code


def _force_interrupted_exit() -> None:
    """Chiusura dopo SIGINT: una riga di audit e uscita senza attendere il thread di stdin."""
    os._exit(_abnormal_stop("interrupted", EXIT_INTERRUPTED))
