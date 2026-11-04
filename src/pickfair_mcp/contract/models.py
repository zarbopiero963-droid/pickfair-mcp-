"""Modelli pydantic del contratto Control API v1 (base)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

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


# ---------------------------------------------------------------------------
# MCP-02a — GET /v1/status e GET /v1/reconciliation/status (PROVISIONAL)
#
# Regole comuni:
# - un campo che il core non possiede vale null ED è elencato in `unavailable`;
#   le due condizioni si implicano a vicenda (mai un default silenzioso);
# - codici e motivi sono token MAIUSCOLI: nessun testo libero dell'upstream;
# - `source` dichiara chi ha prodotto la risposta: «core» o «simulated».
# ---------------------------------------------------------------------------

CODE_PATTERN = r"^[A-Z][A-Z0-9_]{0,63}$"
MAX_CODES = 32

Code = Annotated[str, StringConstraints(pattern=CODE_PATTERN, max_length=64)]
Source = Literal["core", "simulated"]
ObservedAt = Annotated[float, Field(gt=0, lt=1e11)]
Count = Annotated[int, Field(ge=0, le=1_000_000)]


def _unique_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("duplicate codes")
    return values


Codes = Annotated[tuple[Code, ...], Field(max_length=MAX_CODES), AfterValidator(_unique_codes)]


def _check_unavailable(values: dict[str, object], declared: tuple[str, ...]) -> None:
    """`values` contiene esattamente i campi opzionali del modello, letti in modo esplicito."""
    if len(set(declared)) != len(declared):
        raise ValueError("duplicate unavailable entries")
    # I nomi ammessi in `unavailable` sono già vincolati dal tipo Literal del campo.
    for name, value in values.items():
        if (value is None) != (name in declared):
            raise ValueError("null field and unavailable list disagree")


class Readiness(StrictModel):
    level: Literal["READY", "DEGRADED", "NOT_READY"]
    ready: bool
    blockers: Codes
    # Readiness MCP-aware (Telegram non blocker se l'ingresso è MCP) non esiste ancora
    # nel core (PF-API-0): il core lo dichiara esplicitamente.
    mcp_aware: bool

    @model_validator(mode="after")
    def _coherent(self) -> Readiness:
        if self.ready != (self.level == "READY"):
            raise ValueError("ready and level disagree")
        if self.ready and self.blockers:
            raise ValueError("ready with blockers")
        return self


class StopState(StrictModel):
    emergency_stopped: bool
    emergency_reason: Code | None
    risk_stop_reason: Code | None
    daily_loss_pending_stop: bool
    kill_switch_active: bool


StatusField = Literal["runtime_state", "execution_mode", "live_enabled", "readiness", "stop"]
STATUS_OPTIONAL_FIELDS: tuple[str, ...] = (
    "runtime_state",
    "execution_mode",
    "live_enabled",
    "readiness",
    "stop",
)


class StatusResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    runtime_state: Literal["STOPPED", "ACTIVE", "PAUSED", "LOCKDOWN"] | None
    execution_mode: Literal["SIM", "LIVE"] | None
    live_enabled: bool | None
    readiness: Readiness | None
    stop: StopState | None
    unavailable: Annotated[tuple[StatusField, ...], Field(max_length=len(STATUS_OPTIONAL_FIELDS))]

    @model_validator(mode="after")
    def _declared(self) -> StatusResponse:
        values: dict[str, object] = {
            "runtime_state": self.runtime_state,
            "execution_mode": self.execution_mode,
            "live_enabled": self.live_enabled,
            "readiness": self.readiness,
            "stop": self.stop,
        }
        if tuple(values) != STATUS_OPTIONAL_FIELDS:
            raise ValueError("optional field list out of sync")
        _check_unavailable(values, self.unavailable)
        return self


class StartupReconciliation(StrictModel):
    state: Literal["NOT_RUN", "OK", "REQUIRED"]
    reason: Code | None
    recovery_failure: Code | None

    @model_validator(mode="after")
    def _coherent(self) -> StartupReconciliation:
        if self.state == "NOT_RUN" and (
            self.reason is not None or self.recovery_failure is not None
        ):
            raise ValueError("NOT_RUN has no outcome")
        return self


class GhostCounters(StrictModel):
    ghost_orders: Count
    suspected_ghosts: Count
    unconfirmed_inflight: Count


class RecoveryState(StrictModel):
    unreadable: bool
    persist_failed: bool


ReconciliationField = Literal[
    "startup", "ambiguities_pending", "ghosts", "hedge_registry_unreliable", "recovery_state"
]
RECONCILIATION_OPTIONAL_FIELDS: tuple[str, ...] = (
    "startup",
    "ambiguities_pending",
    "ghosts",
    "hedge_registry_unreliable",
    "recovery_state",
)


class ReconciliationStatusResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    startup: StartupReconciliation | None
    ambiguities_pending: Count | None
    ghosts: GhostCounters | None
    hedge_registry_unreliable: bool | None
    recovery_state: RecoveryState | None
    unavailable: Annotated[
        tuple[ReconciliationField, ...], Field(max_length=len(RECONCILIATION_OPTIONAL_FIELDS))
    ]

    @model_validator(mode="after")
    def _declared(self) -> ReconciliationStatusResponse:
        values: dict[str, object] = {
            "startup": self.startup,
            "ambiguities_pending": self.ambiguities_pending,
            "ghosts": self.ghosts,
            "hedge_registry_unreliable": self.hedge_registry_unreliable,
            "recovery_state": self.recovery_state,
        }
        if tuple(values) != RECONCILIATION_OPTIONAL_FIELDS:
            raise ValueError("optional field list out of sync")
        _check_unavailable(values, self.unavailable)
        return self
