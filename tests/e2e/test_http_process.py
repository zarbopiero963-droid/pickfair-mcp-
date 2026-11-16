"""MCP-01d, prova L3+L4: processo reale `pickfair-mcp serve --adapter http` → Control API reale.

Provider di prova (nessun core): le prove con il RuntimeController reale sono cross-repository
(`tests/crossrepo/`). Il sottoprocesso non è coperto dalla guardia di rete in-process: si
connette solo alla Control API di questo test su 127.0.0.1.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
import jsonschema
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.control_api.servers import control_api

pytestmark = [pytest.mark.anyio, pytest.mark.e2e, pytest.mark.loopback]
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def params(port: int, token_path: Path) -> StdioServerParameters:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONUNBUFFERED": "1",
        # un proxy d'ambiente non deve essere usato dall'adapter
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
            str(port),
            "--control-api-token-file",
            str(token_path),
            "--upstream-timeout",
            "2",
        ],
        env=env,
    )


async def test_real_mcp_process_reads_through_http_adapter(tmp_path: Path) -> None:
    errlog = (tmp_path / "stderr.log").open("w+")
    with control_api(tmp_path) as (server, store, token_path, _p):
        token = token_path.read_text()
        with anyio.fail_after(60):
            async with (
                stdio_client(params(server.port, token_path), errlog=errlog) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                tools = {t.name: t for t in (await session.list_tools()).tools}
                first = await session.call_tool("get_status", {})
                store.rotate(token_path)
                after_rotation = await session.call_tool("get_reconciliation_status", {})
                server.stop()
                down = await session.call_tool("get_status", {})
    assert first.isError is False and after_rotation.isError is False
    payload = first.structuredContent
    assert payload is not None
    jsonschema.validate(payload, tools["get_status"].outputSchema)
    assert payload["data"]["upstream"] == {"kind": "http", "certified": False}
    assert payload["data"]["status"]["source"] == "core"
    assert down.isError is True
    assert down.structuredContent is not None
    assert down.structuredContent["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    errlog.seek(0)
    stderr = errlog.read()
    start = [json.loads(line) for line in stderr.splitlines() if '"server_start"' in line]
    assert start and start[0]["adapter_kind"] == "http" and start[0]["certified"] is False
    assert token not in stderr and token_path.read_text() not in stderr
