"""Tool `get_meta`: esegue l'handshake e restituisce i meta solo se compatibili."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.auth import Scope
from pickfair_mcp.contract.models import Capability, StrictModel
from pickfair_mcp.contract.version import (
    GIT_SHA_PATTERN,
    MAX_CAPABILITIES,
    SCHEMA_HASH_PATTERN,
    SEMVER_PATTERN,
    SUPPORTED_CONTRACT_VERSION,
    contract_schema_hash,
)
from pickfair_mcp.errors import ToolError
from pickfair_mcp.policy.handshake import HandshakeGuard, HandshakeStatus
from pickfair_mcp.tools.registry import ToolContext, ToolSpec

DESCRIPTION = (
    "Read-only. Performs the version/capability handshake with the local Pickfair "
    "Control API (GET /v1/meta) and returns contract version, capabilities, git SHA and "
    "schema hash only when the contract is compatible. Any mismatch returns "
    "CONTRACT_INCOMPATIBLE and blocks operations. Never places, cancels or changes anything."
)


class GetMetaInput(StrictModel):
    """Nessun argomento ammesso."""


class HandshakeInfo(StrictModel):
    status: Literal["COMPATIBLE"]
    epoch: Annotated[int, Field(ge=1)]
    supported_contract_version: Annotated[str, StringConstraints(pattern=SEMVER_PATTERN)]
    supported_schema_hash: Annotated[str, StringConstraints(pattern=SCHEMA_HASH_PATTERN)]


class UpstreamInfo(StrictModel):
    kind: Literal["simulated", "http"]
    certified: bool


class GetMetaData(StrictModel):
    contract_version: Annotated[str, StringConstraints(pattern=SEMVER_PATTERN)]
    capabilities: Annotated[
        tuple[Capability, ...], Field(min_length=1, max_length=MAX_CAPABILITIES)
    ]
    git_sha: Annotated[str, StringConstraints(pattern=GIT_SHA_PATTERN)]
    schema_hash: Annotated[str, StringConstraints(pattern=SCHEMA_HASH_PATTERN)]
    handshake: HandshakeInfo
    upstream: UpstreamInfo


def make_get_meta(adapter: ControlApiAdapter, guard: HandshakeGuard) -> ToolSpec:
    async def handler(_: ToolContext) -> GetMetaData:
        result = await guard.perform()
        if result.status is not HandshakeStatus.COMPATIBLE or result.meta is None:
            assert result.error_code is not None
            raise ToolError(
                result.error_code, reasons=result.reasons, handshake_status=result.status.value
            )
        meta = result.meta
        return GetMetaData(
            contract_version=meta.contract_version,
            capabilities=meta.capabilities,
            git_sha=meta.git_sha,
            schema_hash=meta.schema_hash,
            handshake=HandshakeInfo(
                status="COMPATIBLE",
                epoch=result.epoch,
                supported_contract_version=SUPPORTED_CONTRACT_VERSION,
                supported_schema_hash=contract_schema_hash(),
            ),
            upstream=UpstreamInfo(kind=adapter.kind, certified=adapter.certified),
        )

    return ToolSpec(
        name="get_meta",
        route="GET /v1/meta",
        scope=Scope.READ,
        description=DESCRIPTION,
        input_model=GetMetaInput,
        data_model=GetMetaData,
        handler=handler,
    )
