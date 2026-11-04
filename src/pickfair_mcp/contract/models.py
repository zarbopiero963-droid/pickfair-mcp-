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
# I campi di uno snapshot sono letti uno alla volta, senza un'unica sezione critica del runtime:
# ciascuno è coerente in sé, due campi possono riflettere istanti vicini (dichiarato, mai nascosto).
Consistency = Literal["PER_FIELD_NON_ATOMIC"]
ObservedAt = Annotated[float, Field(gt=0, lt=1e11)]
Count = Annotated[int, Field(ge=0, le=1_000_000)]


def _unique_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("duplicate codes")
    return values


# uniqueItems rende la regola visibile anche nello schema condiviso con la Control API
# (divergenza trovata dalla prova differenziale di tests/unit/test_contract_descriptor.py).
Codes = Annotated[
    tuple[Code, ...],
    Field(max_length=MAX_CODES, json_schema_extra={"uniqueItems": True}),
    AfterValidator(_unique_codes),
]


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
    consistency: Consistency
    runtime_state: Literal["STOPPED", "ACTIVE", "PAUSED", "LOCKDOWN"] | None
    execution_mode: Literal["SIM", "LIVE"] | None
    live_enabled: bool | None
    readiness: Readiness | None
    stop: StopState | None
    unavailable: Annotated[
        tuple[StatusField, ...],
        Field(max_length=len(STATUS_OPTIONAL_FIELDS), json_schema_extra={"uniqueItems": True}),
    ]

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
    consistency: Consistency
    startup: StartupReconciliation | None
    ambiguities_pending: Count | None
    ghosts: GhostCounters | None
    hedge_registry_unreliable: bool | None
    recovery_state: RecoveryState | None
    unavailable: Annotated[
        tuple[ReconciliationField, ...],
        Field(
            max_length=len(RECONCILIATION_OPTIONAL_FIELDS), json_schema_extra={"uniqueItems": True}
        ),
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


# ---------------------------------------------------------------------------
# MCP-01e — GET /v1/account e GET /v1/exposure (contratto 1.2.0)
#
# Valori monetari: float finiti in EUR come li tiene il core (nessuna conversione, nessun
# arrotondamento). `execution_mode` dichiara la base del denaro: «SIM» = saldo fittizio del
# broker simulato, mai denaro reale.
#
# Consistenza PER_SECTION_LOCKED: ogni sezione è prodotta da UNA chiamata del core sotto il lock
# del componente che la possiede (RiskDesk, TableManager) oppure è la lettura di un solo valore
# sostituito per intero (snapshot dei fondi). Due sezioni possono riflettere istanti vicini.
# ---------------------------------------------------------------------------

MONEY_LIMIT = 1_000_000_000.0
Money = Annotated[float, Field(ge=-MONEY_LIMIT, le=MONEY_LIMIT)]
NonNegativeMoney = Annotated[float, Field(ge=0, le=MONEY_LIMIT)]
Percent = Annotated[float, Field(ge=0, le=100)]
SectionConsistency = Literal["PER_SECTION_LOCKED"]
ExecutionMode = Literal["SIM", "LIVE"]
# Identificativi di mercato/selezione: mai testo libero (niente nomi di eventi).
IDENTIFIER_PATTERN = r"^[0-9A-Za-z._-]{1,32}$"
Identifier = Annotated[str, StringConstraints(pattern=IDENTIFIER_PATTERN, max_length=32)]
MAX_TABLES = 256
FundsAge = Annotated[float, Field(ge=0, le=31_536_000)]


class Bankroll(StrictModel):
    """`RiskDesk.debug_snapshot()`: una sola lettura sotto il lock del RiskDesk."""

    bankroll_start: Money
    bankroll_current: Money
    equity_peak: Money
    equity_current: Money
    realized_pnl: Money
    unrealized_pnl: Money
    drawdown_pct: Percent


class CashBasis(StrictModel):
    """`RiskDesk.cash_basis()`: cassa e impegnato della STESSA lettura del conto."""

    verified: bool
    cash_equity: NonNegativeMoney | None
    committed_exposure: NonNegativeMoney
    unverified_reason: Code | None

    @model_validator(mode="after")
    def _coherent(self) -> CashBasis:
        if self.verified != (self.cash_equity is not None):
            raise ValueError("verified and cash_equity disagree")
        if self.verified and self.unverified_reason is not None:
            raise ValueError("verified cash with a reason")
        return self


class ExchangeFunds(StrictModel):
    """Ultimo snapshot dei fondi registrato dal runtime (nessuna nuova lettura dell'exchange)."""

    ok: bool
    available: NonNegativeMoney
    committed: NonNegativeMoney
    cash_equity: NonNegativeMoney
    reason: Code | None
    source: Code
    age_s: FundsAge | None

    @model_validator(mode="after")
    def _coherent(self) -> ExchangeFunds:
        if self.ok == (self.reason is not None):
            raise ValueError("ok and reason disagree")
        return self


DeskMode = Literal["NORMAL", "EXPANSION", "DEFENSE", "LOCKDOWN"]
AccountField = Literal["execution_mode", "bankroll", "cash", "exchange_funds", "desk_mode"]
ACCOUNT_OPTIONAL_FIELDS: tuple[str, ...] = (
    "execution_mode",
    "bankroll",
    "cash",
    "exchange_funds",
    "desk_mode",
)


class AccountResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    consistency: SectionConsistency
    execution_mode: ExecutionMode | None
    bankroll: Bankroll | None
    cash: CashBasis | None
    exchange_funds: ExchangeFunds | None
    # Stessa regola di `get_status` del core (bankroll corrente rispetto al picco), calcolata sui
    # valori della sezione `bankroll`. Le decisioni del Money Management per il singolo ordine
    # considerano anche perdita giornaliera e crescita del ciclo: questo valore non le sostituisce.
    desk_mode: DeskMode | None
    unavailable: Annotated[
        tuple[AccountField, ...],
        Field(max_length=len(ACCOUNT_OPTIONAL_FIELDS), json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _declared(self) -> AccountResponse:
        values: dict[str, object] = {
            "execution_mode": self.execution_mode,
            "bankroll": self.bankroll,
            "cash": self.cash,
            "exchange_funds": self.exchange_funds,
            "desk_mode": self.desk_mode,
        }
        if tuple(values) != ACCOUNT_OPTIONAL_FIELDS:
            raise ValueError("optional field list out of sync")
        _check_unavailable(values, self.unavailable)
        if self.desk_mode is not None and self.bankroll is None:
            raise ValueError("desk_mode without bankroll")
        return self


TableStatus = Literal["FREE", "ACTIVE", "RECOVERY", "LOCKED"]


class RoserpinaTable(StrictModel):
    table_id: Annotated[int, Field(ge=1, le=10_000)]
    status: TableStatus
    occupied: bool
    in_recovery: bool
    market_id: Identifier | None
    selection_id: Identifier | None
    current_exposure: Money
    loss_amount: Money


def _unique_tables(values: tuple[RoserpinaTable, ...]) -> tuple[RoserpinaTable, ...]:
    ids = [t.table_id for t in values]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate table_id")
    return values


class RecoveryCapacity(StrictModel):
    # `RuntimeController._active_recovery_count()`: stato di recovery illeggibile => capacità
    # considerata esaurita (fail-closed del core, riportato com'è).
    active_count: Count
    max_recovery_tables: Count
    allow_recovery: bool


ExposureField = Literal["tables", "total_exposure", "recovery"]
EXPOSURE_OPTIONAL_FIELDS: tuple[str, ...] = ("tables", "total_exposure", "recovery")


class ExposureResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    consistency: SectionConsistency
    # `TableManager.snapshot()`: tutti i tavoli in una sola lettura sotto il lock dei tavoli.
    tables: (
        Annotated[
            tuple[RoserpinaTable, ...], Field(max_length=MAX_TABLES), AfterValidator(_unique_tables)
        ]
        | None
    )
    # `TableManager.total_exposure()`: valore che alimenta il cap `max_open_exposure`; un valore
    # non finito nel core (stato corrotto) rende il campo indisponibile, mai zero.
    total_exposure: NonNegativeMoney | None
    recovery: RecoveryCapacity | None
    unavailable: Annotated[
        tuple[ExposureField, ...],
        Field(max_length=len(EXPOSURE_OPTIONAL_FIELDS), json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _declared(self) -> ExposureResponse:
        values: dict[str, object] = {
            "tables": self.tables,
            "total_exposure": self.total_exposure,
            "recovery": self.recovery,
        }
        if tuple(values) != EXPOSURE_OPTIONAL_FIELDS:
            raise ValueError("optional field list out of sync")
        _check_unavailable(values, self.unavailable)
        return self
