"""MCP-01c L3: processo reale su stdio con principal diversi."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = [pytest.mark.anyio, pytest.mark.e2e]

REPO_ROOT = Path(__file__).resolve().parents[2]

SCRIPT = """
import sys, anyio
from mcp.server.stdio import stdio_server
from pickfair_mcp.adapters.simulated import SimulatedControlApiAdapter
from pickfair_mcp.auth import parse_principal, PrincipalInvalid
from pickfair_mcp.server import build_server
import json
raw = json.loads(sys.argv[1])
try:
    principal = parse_principal(raw)
except PrincipalInvalid:
    principal = None
server = build_server(SimulatedControlApiAdapter(), timeout_s=1.0, principal=principal)
async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())
anyio.run(main)
"""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _call_get_meta(principal_json: str, tmp: Path) -> tuple[dict[str, object], str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONUNBUFFERED": "1",
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-c", SCRIPT, principal_json], env=env
    )
    errlog = tmp / "stderr.log"
    with errlog.open("w") as err, anyio.fail_after(30):
        async with stdio_client(params, errlog=err) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                res = await session.call_tool("get_meta", {})
    stderr = errlog.read_text()
    assert res.structuredContent is not None
    return res.structuredContent, stderr


@pytest.mark.parametrize(
    ("principal_json", "expected"),
    [
        ('{"id": "reader", "scopes": ["read"]}', None),
        ('{"id": "writer", "scopes": ["write"]}', "FORBIDDEN"),
        ('{"id": "boss", "scopes": ["owner", "admin"]}', "FORBIDDEN"),
        ('{"id": "x", "scopes": ["read"], "token": "s3cr3t-tok"}', "FORBIDDEN"),
        ("null", "FORBIDDEN"),
    ],
)
async def test_real_process_enforces_scopes(
    principal_json: str, expected: str | None, tmp_path: Path
) -> None:
    out, stderr = await _call_get_meta(principal_json, tmp_path)
    if expected is None:
        assert out["ok"] is True
    else:
        assert out["error"]["code"] == expected  # type: ignore[index]
    assert "s3cr3t" not in stderr and "s3cr3t" not in str(out)
