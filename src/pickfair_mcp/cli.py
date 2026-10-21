"""Riga di comando: `serve` (server MCP su stdio) e `contract-info`.

`serve` scrive su stdout soltanto il protocollo MCP; diagnostica e audit vanno su stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from collections.abc import Sequence
from types import FrameType

import anyio
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


async def _serve(adapter: SimulatedControlApiAdapter, timeout_s: float) -> None:
    server = build_server(adapter, timeout_s=timeout_s)
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
    # Se SIGINT arriva mentre il thread di lettura di stdin si chiude, il runtime può
    # terminare con BrokenResourceError e perdere il KeyboardInterrupt: lo registriamo
    # qui e deleghiamo al comportamento standard di Python.
    interrupted = False
    previous_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum: int, frame: FrameType | None) -> None:
        nonlocal interrupted
        interrupted = True
        signal.default_int_handler(signum, frame)

    signal.signal(signal.SIGINT, _on_sigint)
    try:
        anyio.run(_serve, adapter, timeout_s)
    except BaseException as exc:  # noqa: BLE001 - es. pipe chiusa dal client: niente traceback
        if interrupted or _is_interrupt(exc):
            return _abnormal_stop("interrupted", EXIT_INTERRUPTED)
        return _abnormal_stop("transport_error", EXIT_TRANSPORT)
    finally:
        signal.signal(signal.SIGINT, previous_handler)
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
