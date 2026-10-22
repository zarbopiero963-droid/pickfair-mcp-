"""Server MCP completo in-process (stream in memoria), client SDK reale."""

from __future__ import annotations

import itertools
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
import jsonschema
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from pickfair_mcp.adapters.simulated import Scenario, SimulatedControlApiAdapter
from pickfair_mcp.auth import Scope
from pickfair_mcp.cli import LOCAL_STDIO_PRINCIPAL as LOCAL
from pickfair_mcp.contract.models import StrictModel
from pickfair_mcp.contract.version import SUPPORTED_CONTRACT_VERSION, contract_schema_hash
from pickfair_mcp.server import build_server
from pickfair_mcp.tools import build_default_registry
from pickfair_mcp.tools.registry import ToolSpec

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def counter_ids() -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"req_{next(counter):032x}"


@asynccontextmanager
async def session_for(
    adapter: SimulatedControlApiAdapter, **kwargs: Any
) -> AsyncIterator[ClientSession]:
    server = build_server(
        adapter, timeout_s=0.1, principal=LOCAL, request_id_factory=counter_ids(), **kwargs
    )
    with anyio.fail_after(15):  # una regressione non deve bloccare la CI
        async with create_connected_server_and_client_session(server) as session:
            yield session


async def test_list_tools_exposes_only_get_meta_with_strict_schemas() -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        tools = (await session.list_tools()).tools
    assert [t.name for t in tools] == ["get_meta"]
    tool = tools[0]
    assert tool.inputSchema["type"] == "object"
    assert tool.inputSchema.get("additionalProperties") is False
    assert tool.inputSchema.get("properties", {}) == {}
    assert tool.outputSchema is not None
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.openWorldHint is False


async def test_get_meta_success_envelope_matches_output_schema() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        result = await session.call_tool("get_meta", {})
    assert result.isError is False
    payload = result.structuredContent
    assert payload is not None
    jsonschema.validate(payload, tools["get_meta"].outputSchema)
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["tool"] == "get_meta"
    assert payload["request_id"] == f"req_{1:032x}"
    data = payload["data"]
    assert data["contract_version"] == SUPPORTED_CONTRACT_VERSION
    assert data["schema_hash"] == contract_schema_hash()
    assert data["handshake"]["status"] == "COMPATIBLE"
    assert data["handshake"]["epoch"] == adapter.connection_epoch
    assert data["upstream"] == {"kind": "simulated", "certified": False}
    # Il testo non strutturato è lo stesso envelope serializzato.
    assert json.loads(result.content[0].text) == payload  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("scenario", "code", "retryable", "handshake_status"),
    [
        (Scenario.INCOMPATIBLE_MAJOR, "CONTRACT_INCOMPATIBLE", False, "INCOMPATIBLE"),
        (Scenario.UNSUPPORTED_MINOR, "CONTRACT_INCOMPATIBLE", False, "INCOMPATIBLE"),
        (Scenario.SCHEMA_HASH_MISMATCH, "CONTRACT_INCOMPATIBLE", False, "INCOMPATIBLE"),
        (Scenario.MISSING_META_CAPABILITY, "CONTRACT_INCOMPATIBLE", False, "INCOMPATIBLE"),
        (Scenario.UNAPPROVED_CAPABILITY, "CONTRACT_INCOMPATIBLE", False, "INCOMPATIBLE"),
        (Scenario.MALFORMED, "UPSTREAM_INVALID_RESPONSE", False, "INCOMPATIBLE"),
        (Scenario.EXTRA_FIELD, "UPSTREAM_INVALID_RESPONSE", False, "INCOMPATIBLE"),
        (Scenario.TIMEOUT, "UPSTREAM_TIMEOUT", True, "UNAVAILABLE"),
        (Scenario.UNAVAILABLE, "UPSTREAM_UNAVAILABLE", True, "UNAVAILABLE"),
    ],
)
async def test_get_meta_failures_are_structured_and_fail_closed(
    scenario: Scenario, code: str, retryable: bool, handshake_status: str
) -> None:
    async with session_for(SimulatedControlApiAdapter(scenario)) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        result = await session.call_tool("get_meta", {})
    assert result.isError is True
    payload = result.structuredContent
    assert payload is not None
    jsonschema.validate(payload, tools["get_meta"].outputSchema)
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == code
    assert payload["error"]["details"]["reasons"]
    assert payload["error"]["retryable"] is retryable
    assert payload["error"]["details"]["handshake_status"] == handshake_status
    assert payload["tool"] == "get_meta"


@pytest.mark.parametrize(
    "arguments",
    [
        {"x": 1},
        {"contract_version": "1.0.0"},
        {"force": True},
        {"__proto__": {}},
    ],
)
async def test_extra_arguments_are_rejected_without_upstream_call(
    arguments: dict[str, Any],
) -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        result = await session.call_tool("get_meta", arguments)
    assert result.isError is True
    assert result.structuredContent is not None
    assert result.structuredContent["error"]["code"] == "INVALID_REQUEST"
    assert adapter.meta_calls == 0


async def test_unknown_tool_is_rejected_without_upstream_call() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        for name in ("place_order", "sim_place_order", "get_status", "raw_rpc"):
            result = await session.call_tool(name, {})
            assert result.isError is True
            assert result.structuredContent is not None
            assert result.structuredContent["error"]["code"] == "UNKNOWN_TOOL"
            assert result.structuredContent["tool"] is None
    assert adapter.meta_calls == 0


async def test_internal_errors_do_not_leak_exception_text() -> None:
    class NoInput(StrictModel):
        pass

    class NoData(StrictModel):
        pass

    async def boom(_: object) -> NoData:
        raise RuntimeError("password=hunter2 /home/secret/path")

    registry = build_default_registry()
    registry.register(
        ToolSpec(
            name="get_status",
            route="GET /v1/status",
            scope=Scope.READ,
            description="test",
            input_model=NoInput,
            data_model=NoData,
            handler=boom,
        )
    )
    async with session_for(SimulatedControlApiAdapter(), registry=registry) as session:
        result = await session.call_tool("get_status", {})
    assert result.isError is True
    text = json.dumps(result.structuredContent) + "".join(
        getattr(c, "text", "") for c in result.content
    )
    assert "hunter2" not in text
    assert "/home/secret" not in text
    assert result.structuredContent is not None
    assert result.structuredContent["error"]["code"] == "INTERNAL_ERROR"
    assert result.structuredContent["tool"] == "get_status"
    assert result.structuredContent["error"]["details"]["reasons"] == ["INTERNAL"]
    assert result.structuredContent["error"]["retryable"] is False


async def test_request_ids_are_unique_per_call() -> None:
    async with session_for(SimulatedControlApiAdapter()) as session:
        ids = [
            (await session.call_tool("get_meta", {})).structuredContent["request_id"]  # type: ignore[index]
            for _ in range(5)
        ]
    assert len(set(ids)) == 5


async def test_get_meta_rehandshakes_after_reconnect() -> None:
    adapter = SimulatedControlApiAdapter()
    async with session_for(adapter) as session:
        first = await session.call_tool("get_meta", {})
        adapter.reconnect(Scenario.INCOMPATIBLE_MAJOR)
        second = await session.call_tool("get_meta", {})
    assert first.isError is False
    assert second.isError is True
    assert second.structuredContent is not None
    assert second.structuredContent["error"]["code"] == "CONTRACT_INCOMPATIBLE"


async def test_injection_text_from_upstream_is_never_echoed() -> None:
    adapter = SimulatedControlApiAdapter(Scenario.INJECTION_TEXT)
    async with session_for(adapter) as session:
        result = await session.call_tool("get_meta", {})
    text = json.dumps(result.structuredContent)
    assert "IGNORE PREVIOUS INSTRUCTIONS" not in text
    assert result.isError is True
    assert result.structuredContent is not None
    assert result.structuredContent["error"]["code"] == "UPSTREAM_INVALID_RESPONSE"


async def test_output_not_matching_declared_model_becomes_internal_error() -> None:
    class NoInput(StrictModel):
        pass

    class Declared(StrictModel):
        value: int

    class Other(StrictModel):
        text: str

    async def wrong(_: object) -> StrictModel:
        return Other(text="unexpected payload")

    registry = build_default_registry()
    registry.register(
        ToolSpec(
            name="get_status",
            route="GET /v1/status",
            scope=Scope.READ,
            description="test",
            input_model=NoInput,
            data_model=Declared,
            handler=wrong,
        )
    )
    async with session_for(SimulatedControlApiAdapter(), registry=registry) as session:
        result = await session.call_tool("get_status", {})
    assert result.isError is True
    assert result.structuredContent is not None
    assert result.structuredContent["error"]["code"] == "INTERNAL_ERROR"
    assert "unexpected payload" not in json.dumps(result.structuredContent)


def test_default_request_ids_have_the_declared_shape() -> None:
    import re

    from pickfair_mcp.envelope import REQUEST_ID_PATTERN
    from pickfair_mcp.server import new_request_id

    ids = {new_request_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(re.fullmatch(REQUEST_ID_PATTERN, i) for i in ids)
