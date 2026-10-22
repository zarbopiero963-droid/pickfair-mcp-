"""Modelli pydantic del contratto Control API v1 (base)."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from pickfair_mcp.contract.version import (
    CAPABILITY_PATTERN,
    GIT_SHA_PATTERN,
    MAX_CAPABILITIES,
    SCHEMA_HASH_PATTERN,
    SEMVER_PATTERN,
)


class StrictModel(BaseModel):
    """Base comune: nessun campo extra, nessuna coercizione, immutabile, solo finiti."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
        validate_default=True,
    )


Capability = Annotated[str, StringConstraints(pattern=CAPABILITY_PATTERN, max_length=128)]


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("capabilities duplicate")
    return values


class MetaResponse(StrictModel):
    """Risposta di GET /v1/meta. Campi PROVISIONAL fino a ratifica PF-API-0."""

    contract_version: Annotated[str, StringConstraints(pattern=SEMVER_PATTERN, max_length=16)]
    capabilities: Annotated[
        tuple[Capability, ...],
        Field(min_length=1, max_length=MAX_CAPABILITIES),
        AfterValidator(_unique),
    ]
    git_sha: Annotated[str, StringConstraints(pattern=GIT_SHA_PATTERN)]
    schema_hash: Annotated[str, StringConstraints(pattern=SCHEMA_HASH_PATTERN)]
