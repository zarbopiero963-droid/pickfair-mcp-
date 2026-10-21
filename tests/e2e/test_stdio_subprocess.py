"""Evidenza di funzionamento reale su stdio: il server gira come sottoprocesso."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = [pytest.mark.anyio, pytest.mark.e2e]

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def server_params(*extra: str) -> StdioServerParameters:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONUNBUFFERED": "1",
    }
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "pickfair_mcp", "serve", "--adapter", "simulated", *extra],
        env=env,
    )


async def test_stdio_initialize_list_and_call_get_meta(tmp_path: Path) -> None:
    errlog = (tmp_path / "stderr.log").open("w+")
    async with (
        stdio_client(server_params(), errlog=errlog) as (read, write),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        assert init.serverInfo.name == "pickfair-mcp"
        tools = (await session.list_tools()).tools
        assert [t.name for t in tools] == ["get_meta"]
        result = await session.call_tool("get_meta", {})
        assert result.isError is False
        assert result.structuredContent is not None
        jsonschema.validate(result.structuredContent, tools[0].outputSchema)
        assert result.structuredContent["data"]["handshake"]["status"] == "COMPATIBLE"
        assert result.structuredContent["data"]["upstream"]["certified"] is False
    errlog.seek(0)
    stderr_lines = [line for line in errlog.read().splitlines() if line.strip()]
    events = [json.loads(line) for line in stderr_lines]
    assert any(e["event"] == "server_start" for e in events)
    assert any(e["event"] == "tool_call" and e.get("tool") == "get_meta" for e in events)


async def test_stdio_incompatible_contract_is_fail_closed(tmp_path: Path) -> None:
    errlog = (tmp_path / "stderr.log").open("w+")
    async with (
        stdio_client(server_params("--sim-scenario", "incompatible_major"), errlog=errlog) as (
            read,
            write,
        ),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("get_meta", {})
    assert result.isError is True
    assert result.structuredContent is not None
    assert result.structuredContent["error"]["code"] == "CONTRACT_INCOMPATIBLE"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "pickfair_mcp", *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )


def test_http_adapter_is_blocked_core() -> None:
    proc = run_cli("serve", "--adapter", "http")
    assert proc.returncode == 2
    assert "BLOCKED_CORE" in proc.stderr
    assert proc.stdout == ""


@pytest.mark.parametrize(
    "args",
    [
        ("serve", "--sim-scenario", "does_not_exist"),
        ("serve", "--upstream-timeout", "nan"),
        ("serve", "--upstream-timeout", "0"),
        ("serve", "--adapter", "betfair"),
    ],
)
def test_invalid_cli_arguments_exit_non_zero(args: tuple[str, ...]) -> None:
    proc = run_cli(*args)
    assert proc.returncode == 2
    assert proc.stdout == ""


def test_contract_info_prints_version_and_hash() -> None:
    proc = run_cli("contract-info")
    assert proc.returncode == 0
    info = json.loads(proc.stdout)
    assert info["supported_contract_version"] == "1.0.0"
    assert len(info["schema_hash"]) == 64
    assert info["routes"] == 25
    assert info["tools"] == ["get_meta"]
    assert info["mutation_exposure"] == "BLOCKED_UNTIL_CORE_AUTHORITY_READY"
