"""stdio grezzo: stdout contiene solo JSON-RPC, stderr solo audit JSON senza input del client.

Regressioni R4/R5 della review indipendente: un client SDK tollera righe spurie su
stdout e i log dell'SDK finivano su stderr con l'input grezzo.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_S = 30


class RawServer:
    def __init__(self) -> None:
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO_ROOT / "src")}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "pickfair_mcp", "serve", "--adapter", "simulated"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

    def send(self, message: dict[str, Any] | str) -> None:
        assert self.proc.stdin is not None
        line = message if isinstance(message, str) else json.dumps(message)
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def read(self) -> dict[str, Any]:
        assert self.proc.stdout is not None
        result: list[str] = []
        reader = threading.Thread(
            target=lambda: result.append(self.proc.stdout.readline()),  # type: ignore[union-attr]
            daemon=True,
        )
        reader.start()
        reader.join(TIMEOUT_S)
        assert result, "nessuna risposta entro il timeout"
        message: dict[str, Any] = json.loads(result[0])
        assert message["jsonrpc"] == "2.0"
        return message

    def close(self) -> tuple[str, str]:
        out, err = self.proc.communicate(timeout=TIMEOUT_S)
        return out, err

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=TIMEOUT_S)


@pytest.fixture
def server() -> Iterator[RawServer]:
    raw = RawServer()
    try:
        yield raw
    finally:
        raw.kill()


INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "raw-test", "version": "0"},
    },
}


def assert_stderr_is_audit_only(err: str) -> list[dict[str, Any]]:
    records = []
    for line in err.splitlines():
        if line.strip():
            records.append(json.loads(line))  # una riga non JSON fa fallire il test
    assert all("event" in r for r in records)
    return records


def test_sigint_shutdown_writes_only_audit_to_stderr(server: RawServer) -> None:
    server.send(INIT)
    assert server.read()["id"] == 1
    server.proc.send_signal(signal.SIGINT)
    out, err = server.close()
    assert out.strip() == "" or all(
        json.loads(x)["jsonrpc"] == "2.0" for x in out.splitlines() if x.strip()
    )
    records = assert_stderr_is_audit_only(err)
    assert records[-1]["event"] == "server_stop"
    assert records[-1]["outcome"] == "interrupted"
    assert server.proc.returncode != 0


def test_closed_stdout_writes_only_audit_to_stderr(server: RawServer) -> None:
    server.send(INIT)
    assert server.read()["id"] == 1
    assert server.proc.stdout is not None
    server.proc.stdout.close()  # il client sparisce: la scrittura successiva fallisce
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert server.proc.stdin is not None
    server.proc.stdin.close()
    server.proc.wait(timeout=TIMEOUT_S)
    assert server.proc.stderr is not None
    assert_stderr_is_audit_only(server.proc.stderr.read())


def test_stdout_is_pure_jsonrpc_and_stderr_has_no_client_input(server: RawServer) -> None:
    server.send(INIT)
    assert server.read()["id"] == 1
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = server.read()
    assert [t["name"] for t in tools["result"]["tools"]] == ["get_meta"]
    server.send(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_meta", "arguments": {"secret_arg": "hunter2-arg"}},
        }
    )
    call = server.read()
    assert call["result"]["isError"] is True
    assert call["result"]["structuredContent"]["error"]["code"] == "INVALID_REQUEST"
    server.send("garbage-not-json password=hunter2-raw")
    server.send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": [1, 2]})
    out, err = server.close()
    for line in out.splitlines():
        if line.strip():
            assert json.loads(line)["jsonrpc"] == "2.0"
    assert_stderr_is_audit_only(err)
    assert "hunter2" not in err
    assert "hunter2" not in out
