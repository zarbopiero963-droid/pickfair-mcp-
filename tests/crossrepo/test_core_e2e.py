"""Fase E — end-to-end REALE fra processi: MCP di prodotto → Control API → Pickfair SIM.

Processi:
1. `pickfair-mcp serve --adapter http` (processo MCP reale, adapter HTTP di prodotto);
2. processo «core» (`core_runtime_server.py`) con RuntimeController reale avviato in SIM
   (SimulationBroker, SQLite temporaneo, EventBus) e Control API tramite il ponte del core.

Richiede un checkout di Pickfair-nogui con il ponte (`docs/handoff/`) e il suo Python:
    PICKFAIR_CORE_PATH=/percorso/Pickfair-nogui  PICKFAIR_CORE_PYTHON=/percorso/python
Senza queste variabili il modulo è SKIPPED: esito NOT_RUN, mai PASS.
Nessun Betfair LIVE, nessun denaro reale, nessuna rete oltre 127.0.0.1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import jsonschema
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CORE_PATH = os.environ.get("PICKFAIR_CORE_PATH")
CORE_PYTHON = os.environ.get("PICKFAIR_CORE_PYTHON")
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.e2e,
    pytest.mark.loopback,
    pytest.mark.skipif(not (CORE_PATH and CORE_PYTHON), reason="NOT_RUN: core non configurato"),
]
REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name("core_runtime_server.py")
READ_TOOLS = (
    "get_status",
    "get_reconciliation_status",
    "get_account",
    "get_exposure",
    "list_positions",
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Core:
    """Processo core comandato via stdin; ogni comando restituisce una riga JSON."""

    def __init__(self, tmp_path: Path) -> None:
        import socket

        self.token_dir = tmp_path / "secure"
        self.token_dir.mkdir(mode=0o700)
        self.token_path = self.token_dir / "control_api.token"
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        self.port = int(s.getsockname()[1])
        s.close()
        work = tmp_path / "core-work"
        work.mkdir()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(tmp_path),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
        }
        self.proc = subprocess.Popen(
            [
                str(CORE_PYTHON),
                str(HELPER),
                str(CORE_PATH),
                str(work),
                str(self.port),
                str(self.token_path),
            ],
            cwd=work,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.ready = self._read()
        assert self.ready["event"] == "READY" and self.ready["started"] is True, self.ready

    def _read(self) -> dict[str, Any]:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        assert line, self.proc.stderr.read() if self.proc.stderr else "core terminato"
        result: dict[str, Any] = json.loads(line)
        return result

    def send(self, command: str) -> dict[str, Any]:
        assert self.proc.stdin is not None
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()
        return self._read()

    def close(self) -> str:
        if self.proc.poll() is None:
            self.send("QUIT")
        _out, err = self.proc.communicate(timeout=30)
        return err


@pytest.fixture
def core(tmp_path: Path) -> Iterator[Core]:
    c = Core(tmp_path)
    try:
        yield c
    finally:
        c.close()


def mcp_params(
    core: Core, *, token_file: Path | None = None, timeout_s: float = 2.0
) -> StdioServerParameters:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONUNBUFFERED": "1",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
    }
    return StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "pickfair_mcp",
            "serve",
            "--adapter",
            "http",
            "--control-api-port",
            str(core.port),
            "--control-api-token-file",
            str(token_file or core.token_path),
            "--upstream-timeout",
            str(timeout_s),
        ],
        env=env,
    )


@asynccontextmanager
async def mcp(core: Core, errlog: Any, **kwargs: Any) -> AsyncIterator[ClientSession]:
    with anyio.fail_after(90):
        async with (
            stdio_client(mcp_params(core, **kwargs), errlog=errlog) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield session


async def call(session: ClientSession, name: str) -> tuple[bool, dict[str, Any]]:
    result = await session.call_tool(name, {})
    assert result.structuredContent is not None
    return bool(result.isError), result.structuredContent


async def test_e2e_normal_start_reconciliation_and_emergency_stop(
    core: Core, tmp_path: Path
) -> None:
    errlog = (tmp_path / "mcp.err").open("w+")
    before = core.send("DIGEST")
    async with mcp(core, errlog) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        meta = await call(s, "get_meta")
        status = await call(s, "get_status")
        recon = await call(s, "get_reconciliation_status")
        reads_done = core.send("DIGEST")
        core.send("EMERGENCY")  # comando impartito al CORE, non alla Control API
        baseline = core.send("DIGEST")  # nuova linea di base: gli effetti di emergency_stop()
        after_stop = await call(s, "get_status")
    for name, (is_error, payload) in (
        ("get_meta", meta),
        ("get_status", status),
        ("get_reconciliation_status", recon),
    ):
        assert is_error is False, payload
        jsonschema.validate(payload, tools[name].outputSchema)
    assert meta[1]["data"]["handshake"]["status"] == "COMPATIBLE"
    assert meta[1]["data"]["git_sha"] == core.ready["sha"]
    st = status[1]["data"]
    assert st["upstream"] == {"kind": "http", "certified": False}
    assert st["status"]["source"] == "core" and st["status"]["runtime_state"] == "ACTIVE"
    assert st["status"]["execution_mode"] == "SIM"
    assert st["status"]["consistency"] == "PER_FIELD_NON_ATOMIC"
    assert recon[1]["data"]["reconciliation"]["startup"]["state"] == "OK"
    stop = after_stop[1]["data"]["status"]["stop"]
    assert stop["emergency_stopped"] is True and stop["emergency_reason"] == "DAILY_LOSS_BREACH"
    assert "soglia" not in json.dumps(after_stop)
    after = core.send("DIGEST")
    # Il runtime avviato chiama una volta `broker.list_events` all'avvio (sync del catalogo in
    # background, prima di ogni lettura): si confrontano le chiamate NUOVE in ciascuna finestra
    # di sole letture. Le chiamate fatte da emergency_stop() stanno fra le due finestre.
    assert reads_done["calls"] == before["calls"]
    assert after["calls"] == baseline["calls"]
    assert len(baseline["calls"]) > len(before["calls"])  # il comando nel core ha agito davvero
    for key in ("db", "state"):
        assert reads_done[key] == before[key] and after[key] == baseline[key], key
    assert after["balance"] == after["balance_at_start"]


async def test_e2e_reads_have_no_side_effects_on_the_core(core: Core, tmp_path: Path) -> None:
    errlog = (tmp_path / "mcp.err").open("w+")
    before = core.send("DIGEST")
    async with mcp(core, errlog) as s:
        results: list[bool] = []

        async def one(name: str) -> None:
            results.append((await call(s, name))[0])

        async with anyio.create_task_group() as tg:  # letture concorrenti
            for i in range(30):
                tg.start_soon(one, READ_TOOLS[i % len(READ_TOOLS)])
    after = core.send("DIGEST")
    assert results == [False] * 30
    assert after["counts"]["OK"] == 31  # un handshake + 30 letture
    for key in ("db", "bus", "state", "balance"):
        assert after[key] == before[key], key
    assert after["calls"] == before["calls"]  # nessuna chiamata nuova a Betfair/broker/monitor


async def test_e2e_invalid_token_is_unauthorized(core: Core, tmp_path: Path) -> None:
    from pickfair_control_api.tokens import issue_token_file

    other = core.token_dir / "other.token"
    issue_token_file(other)
    errlog = (tmp_path / "mcp.err").open("w+")
    async with mcp(core, errlog, token_file=other) as s:
        is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["code"] == "UPSTREAM_UNAUTHORIZED"
    assert payload["data"] is None
    assert core.send("DIGEST")["counts"] == {"UNAUTHORIZED": 2}


async def test_e2e_unauthorized_principal_never_reaches_the_core(core: Core) -> None:
    from mcp.shared.memory import create_connected_server_and_client_session

    from pickfair_mcp.adapters.http import HttpControlApiAdapter
    from pickfair_mcp.auth import Principal, Scope
    from pickfair_mcp.auth.token_file import LocalTokenFile
    from pickfair_mcp.server import build_server

    adapter = HttpControlApiAdapter(
        port=core.port, token_file=LocalTokenFile(core.token_path), timeout_s=2.0
    )
    writer = Principal(principal_id="writer", scopes=frozenset({Scope.WRITE}))
    server = build_server(adapter, timeout_s=2.0, principal=writer)
    async with create_connected_server_and_client_session(server) as s:
        is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["code"] == "FORBIDDEN"
    assert core.send("DIGEST")["counts"] == {}


async def test_e2e_core_down_restart_timeout_incompatible_and_stale(
    core: Core, tmp_path: Path
) -> None:
    errlog = (tmp_path / "mcp.err").open("w+")
    async with mcp(core, errlog, timeout_s=1.0) as s:
        ok = await call(s, "get_status")
        core.send("STOP_API")
        down = await call(s, "get_status")
        core.send("START_API")  # riavvio: token nuovo, nuovo handshake
        restarted = await call(s, "get_status")
        core.send("HANG 3")
        timeout = await call(s, "get_status")
        core.send("HANG 0")
        core.send("INCOMPATIBLE")
        incompatible = await call(s, "get_status")
    assert ok[0] is False
    assert (
        down[0]
        and down[1]["error"]["code"] == "UPSTREAM_UNAVAILABLE"
        and down[1]["error"]["retryable"]
    )
    assert restarted[0] is False, restarted
    assert timeout[0] and timeout[1]["error"]["code"] == "UPSTREAM_TIMEOUT"
    assert incompatible[0] and incompatible[1]["error"]["code"] == "CONTRACT_INCOMPATIBLE"
    for _, payload in (down, timeout, incompatible):
        assert payload["data"] is None and "simulated" not in json.dumps(payload)


async def test_e2e_stale_core_snapshot_is_rejected(core: Core, tmp_path: Path) -> None:
    errlog = (tmp_path / "mcp.err").open("w+")
    core.send("CLOCK_SKEW -3600")
    async with mcp(core, errlog) as s:
        is_error, payload = await call(s, "get_status")
    assert is_error and payload["error"]["details"]["reasons"] == [
        "UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT"
    ]


async def test_e2e_no_secret_leaks(core: Core, tmp_path: Path) -> None:
    errlog = (tmp_path / "mcp.err").open("w+")
    async with mcp(core, errlog) as s:
        payloads = [
            await call(s, n) for n in ("get_meta", "get_status", "get_reconciliation_status")
        ]
    token = core.token_path.read_text()
    core_err = core.close()
    errlog.seek(0)
    mcp_err = errlog.read()
    for text in (json.dumps(payloads), mcp_err, core_err):
        assert token not in text
    assert str(core.token_path) not in json.dumps(payloads)


async def test_e2e_account_and_exposure_report_the_core_values(core: Core, tmp_path: Path) -> None:
    """MCP-01e: get_account e get_exposure dal RuntimeController reale avviato in SIM."""
    errlog = (tmp_path / "mcp.err").open("w+")
    before = core.send("DIGEST")
    async with mcp(core, errlog) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        account = await call(s, "get_account")
        exposure = await call(s, "get_exposure")
        reads_done = core.send("DIGEST")
        expected = core.send("FINANCE")
        activated = core.send("ACTIVATE")  # comando al CORE: occupa un tavolo
        baseline = core.send("DIGEST")
        exposure_after = await call(s, "get_exposure")
        after = core.send("DIGEST")
    for name, (is_error, payload) in (("get_account", account), ("get_exposure", exposure)):
        assert is_error is False, payload
        jsonschema.validate(payload, tools[name].outputSchema)
        assert payload["data"]["upstream"] == {"kind": "http", "certified": False}
    a = account[1]["data"]["account"]
    assert a["source"] == "core" and a["consistency"] == "PER_SECTION_LOCKED"
    assert a["execution_mode"] == "SIM"
    assert a["bankroll"] == {k: float(expected["bankroll"][k]) for k in a["bankroll"]}
    assert a["desk_mode"] == expected["desk_mode"]
    assert a["cash"]["committed_exposure"] == expected["cash"][1]
    assert a["cash"]["verified"] is (expected["cash"][0] is not None)
    funds = a["exchange_funds"]
    assert funds["ok"] is expected["funds"]["ok"] and funds["source"] == "START"
    assert funds["available"] == expected["funds"]["available"]
    e = exposure[1]["data"]["exposure"]
    assert len(e["tables"]) == expected["tables"]
    assert e["total_exposure"] == expected["total_exposure"]
    assert e["recovery"]["active_count"] == expected["recovery_active"]
    # dopo il comando al core il tavolo risulta occupato; nome evento e meta non escono
    e2 = exposure_after[1]["data"]["exposure"]
    table = next(t for t in e2["tables"] if t["table_id"] == 1)
    assert table["occupied"] is True and table["status"] == "ACTIVE"
    assert table["market_id"] == "1.234567" and table["selection_id"] == "47972"
    assert e2["total_exposure"] == activated["total"] == 12.5
    text = json.dumps(exposure_after)
    assert "Juventus" not in text and "IGNORE" not in text and "cref-secret" not in text
    # finestre di sole letture: nessun effetto sul core
    assert reads_done["calls"] == before["calls"] and after["calls"] == baseline["calls"]
    for key in ("db", "bus", "balance"):
        assert reads_done[key] == before[key] and after[key] == baseline[key], key


async def test_e2e_unserved_reads_are_not_implemented(core: Core) -> None:
    """Route approvate ma assenti nel core: 501 tipizzato dal server reale, mai un dato."""
    from pickfair_mcp.adapters.http import _LoopbackConnection  # niente DNS: socket IPv4 diretto

    token = core.token_path.read_text()
    for path in ("/v1/orders", "/v1/config", "/v1/markets/1.2/book"):
        conn = _LoopbackConnection(core.port, 5.0)
        conn.request("GET", path, headers={"Authorization": f"Bearer {token}"})
        resp = conn.getresponse()
        assert (resp.status, json.loads(resp.read())) == (
            501,
            {"error": {"code": "NOT_IMPLEMENTED"}},
        )
        conn.close()
    for method in ("POST", "PATCH"):
        conn = _LoopbackConnection(core.port, 5.0)
        conn.request(method, "/v1/orders", body=b"{}", headers={"Authorization": f"Bearer {token}"})
        assert conn.getresponse().status == 405  # nessun comando servito
        conn.close()


async def test_e2e_diagnostics_protections_and_positions(core: Core, tmp_path: Path) -> None:
    """MCP-01f: diagnostica, protezioni e posizioni dal RuntimeController reale avviato in SIM."""
    from decimal import Decimal

    errlog = (tmp_path / "mcp.err").open("w+")
    async with mcp(core, errlog) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        status = await call(s, "get_status")
        empty = await call(s, "list_positions")
        filled = core.send("FILL")  # comando al CORE, non alla Control API
        positions = await call(s, "list_positions")
        core.send("EMERGENCY")
        after_stop = await call(s, "get_status")
    for name, (is_error, payload) in (("get_status", status), ("list_positions", positions)):
        assert is_error is False, payload
        jsonschema.validate(payload, tools[name].outputSchema)
    st = status[1]["data"]["status"]
    prot = st["protections"]
    assert len(prot["items"]) == 22
    assert prot["items"]["market_tradability"]["state"] == "UNAVAILABLE"
    assert set(prot["unverifiable"]) == {
        k for k, v in prot["items"].items() if v["state"] in ("UNKNOWN", "UNAVAILABLE")
    }
    assert all((v["state"] == "ACTIVE") == (v["reason"] is None) for v in prot["items"].values())
    assert st["engine"]["betfair"]["client_kind"] == "SIMULATION"
    assert st["engine"]["modes"]["read_only_mode"] == "NOT_IN_CORE"
    assert empty[1]["data"]["positions"]["positions"] == []
    pos = positions[1]["data"]["positions"]["positions"][0]
    assert pos["side"] == "LAY" and pos["amounts_source"] == "LEDGER_DECIMAL"
    assert Decimal(pos["open_size"]) == Decimal(filled["open_size"])
    assert Decimal(pos["avg_entry_price"]) == Decimal(filled["avg"])
    assert Decimal(pos["exposure"]) == Decimal(filled["exposure"])
    text = json.dumps(positions)
    assert "Juventus" not in text and "cref-secret" not in text
    em = after_stop[1]["data"]["status"]["protections"]["items"]["emergency_stop"]
    assert em["state"] == "TRIGGERED" and em["reason"] == "DAILY_LOSS_BREACH"
    assert em["as_of"] is not None
