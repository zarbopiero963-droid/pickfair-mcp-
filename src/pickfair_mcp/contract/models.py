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


# ---------------------------------------------------------------------------
# MCP-01f — diagnostica del motore e protezioni (contratto 1.3.0, dentro GET /v1/status)
#
# Importi e quote: stringhe decimali (DecimalStr), mai float. La forma è canonica e senza
# esponente: «12.5», «-3», «0.0000001». Il MCP non fa aritmetica su questi valori.
# ---------------------------------------------------------------------------

# Forma canonica, nello stesso pattern per MCP e Control API: niente esponente, niente «+», niente
# zeri iniziali, niente zero negativo («-0», «-0.00»: un negativo minore di 1 termina con una cifra
# non nulla); al più 15 cifre intere e 28 decimali; nessun lookahead (valido in Rust e Python).
DECIMAL_PATTERN = (
    r"^(?:-?[1-9][0-9]{0,14}(?:\.[0-9]{1,28})?"
    r"|0(?:\.[0-9]{1,28})?"
    r"|-0\.[0-9]{0,27}[1-9])$"
)
DecimalStr = Annotated[str, StringConstraints(pattern=DECIMAL_PATTERN, max_length=48)]
ExecutionMode = Literal["SIM", "LIVE"]
EpochSeconds = Annotated[float, Field(gt=0, lt=1e11)]
BigCount = Annotated[int, Field(ge=0, le=10**15)]


class _ProtectionBase(StrictModel):
    source: Code
    limit: DecimalStr | None
    as_of: EpochSeconds | None


class ActiveProtection(_ProtectionBase):
    """Protezione armata e non scattata: l'unico stato senza motivo."""

    state: Literal["ACTIVE"]
    reason: None


class FlaggedProtection(_ProtectionBase):
    """Ogni altro stato dice perché. Ciò che non è verificabile è UNKNOWN/UNAVAILABLE, mai SAFE."""

    state: Literal["INACTIVE", "TRIGGERED", "UNKNOWN", "UNAVAILABLE"]
    reason: Code


# Unione nello schema condiviso: la regola «solo ACTIVE è senza motivo» la verifica anche la
# Control API prima di rispondere, non solo il MCP.
Protection = ActiveProtection | FlaggedProtection


class ProtectionItems(StrictModel):
    kill_switch: Protection
    emergency_stop: Protection
    runtime_lockdown: Protection
    desk_lockdown: Protection
    drawdown_pct_hard_stop: Protection
    drawdown_abs_hard_stop: Protection
    session_loss: Protection
    daily_loss: Protection
    risk_stop: Protection
    exposure_stop: Protection
    max_open_exposure: Protection
    max_order_exposure: Protection
    max_market_exposure: Protection
    max_event_exposure_abs: Protection
    max_total_exposure_pct: Protection
    max_event_exposure_pct: Protection
    funds_freshness: Protection
    book_guard: Protection
    market_tradability: Protection
    anti_duplication: Protection
    order_circuit_breaker: Protection
    recovery_state: Protection


PROTECTION_NAMES: tuple[str, ...] = tuple(ProtectionItems.model_fields)
ProtectionName = Literal[
    "kill_switch",
    "emergency_stop",
    "runtime_lockdown",
    "desk_lockdown",
    "drawdown_pct_hard_stop",
    "drawdown_abs_hard_stop",
    "session_loss",
    "daily_loss",
    "risk_stop",
    "exposure_stop",
    "max_open_exposure",
    "max_order_exposure",
    "max_market_exposure",
    "max_event_exposure_abs",
    "max_total_exposure_pct",
    "max_event_exposure_pct",
    "funds_freshness",
    "book_guard",
    "market_tradability",
    "anti_duplication",
    "order_circuit_breaker",
    "recovery_state",
]
ProtectionNames = Annotated[
    tuple[ProtectionName, ...],
    Field(max_length=len(PROTECTION_NAMES), json_schema_extra={"uniqueItems": True}),
    AfterValidator(_unique_codes),
]


class Protections(StrictModel):
    items: ProtectionItems
    # Elenchi derivati, controllati: una protezione disattivata o non verificabile non può tacere.
    disabled: ProtectionNames
    unverifiable: ProtectionNames

    @model_validator(mode="after")
    def _derived(self) -> Protections:
        states = {name: item.state for name, item in self.items}
        disabled = sorted(n for n, s in states.items() if s == "INACTIVE")
        unverifiable = sorted(n for n, s in states.items() if s in ("UNKNOWN", "UNAVAILABLE"))
        if list(self.disabled) != disabled or list(self.unverifiable) != unverifiable:
            raise ValueError("derived protection lists disagree with the items")
        return self


EngineState = Literal["READY", "DEGRADED", "NOT_READY"]
ComponentName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]


class EngineComponent(StrictModel):
    name: ComponentName
    state: EngineState
    reason: Code | None


def _unique_components(values: tuple[EngineComponent, ...]) -> tuple[EngineComponent, ...]:
    names = [c.name for c in values]
    if len(set(names)) != len(names):
        raise ValueError("duplicate component")
    return values


class TradingEngineHealth(StrictModel):
    state: EngineState
    # La salute dei componenti è calcolata dal core all'avvio del motore, non a ogni lettura.
    evaluated_at: Literal["ENGINE_START"]
    risk_gate_wired: bool
    components: Annotated[
        tuple[EngineComponent, ...], Field(max_length=32), AfterValidator(_unique_components)
    ]

    @model_validator(mode="after")
    def _coherent(self) -> TradingEngineHealth:
        if self.state == "READY" and any(c.state != "READY" for c in self.components):
            raise ValueError("READY engine with a non-ready component")
        return self


ClientKind = Literal["SIMULATION", "LIVE"]


class Keepalive(StrictModel):
    running: bool
    failure_count: Count
    last_ok_at: EpochSeconds | None
    error_present: bool


class BetfairConnection(StrictModel):
    """Stato della connessione come lo tiene il servizio: nessuna credenziale, nessun testo."""

    connected: bool
    has_client: bool
    client_kind: ClientKind
    error_present: bool
    keepalive: Keepalive


class StreamFeed(StrictModel):
    running: bool
    connected: bool
    degraded: bool
    auth_degraded: bool
    auth_failure_count: Count
    keepalive_failure_count: Count
    error_present: bool
    last_message_at: EpochSeconds | None


class RuntimeIo(StrictModel):
    last_status: Code
    total_count: BigCount
    slow_count: BigCount
    degraded_count: BigCount
    unavailable_count: BigCount
    last_latency_ms: Annotated[float, Field(ge=0, le=1e7)]
    error_present: bool


class EventBusPressure(StrictModel):
    queue_depth: BigCount
    queue_high_watermark: BigCount
    enqueued_total: BigCount
    dequeued_total: BigCount
    running: bool
    accepting: bool
    seconds_since_last_dequeue: Annotated[float, Field(ge=0, le=1e9)] | None


class OperationalQueues(StrictModel):
    cashout_inflight: Count
    cashout_uncertain: Count
    direct_unmatched: Count


class Modes(StrictModel):
    """Configurazione, capacità e cliente effettivo, tenuti distinti (nessuna deduzione)."""

    configured_execution_mode: ExecutionMode
    simulation_flag: bool
    live_enabled: bool
    live_readiness_ok: bool
    client_kind: Literal["SIMULATION", "LIVE", "NONE"]
    # Il core non ha una modalità READ_ONLY: dichiarato, mai inventato.
    read_only_mode: Literal["NOT_IN_CORE"]


EngineField = Literal[
    "trading_engine", "betfair", "stream", "io", "event_bus", "queues", "modes", "last_signal_at"
]
ENGINE_OPTIONAL_FIELDS: tuple[str, ...] = (
    "trading_engine",
    "betfair",
    "stream",
    "io",
    "event_bus",
    "queues",
    "modes",
    "last_signal_at",
)


class EngineDiagnostics(StrictModel):
    trading_engine: TradingEngineHealth | None
    betfair: BetfairConnection | None
    stream: StreamFeed | None
    io: RuntimeIo | None
    event_bus: EventBusPressure | None
    queues: OperationalQueues | None
    modes: Modes | None
    last_signal_at: EpochSeconds | None
    unavailable: Annotated[
        tuple[EngineField, ...],
        Field(max_length=len(ENGINE_OPTIONAL_FIELDS), json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _declared(self) -> EngineDiagnostics:
        values: dict[str, object] = {
            "trading_engine": self.trading_engine,
            "betfair": self.betfair,
            "stream": self.stream,
            "io": self.io,
            "event_bus": self.event_bus,
            "queues": self.queues,
            "modes": self.modes,
            "last_signal_at": self.last_signal_at,
        }
        if tuple(values) != ENGINE_OPTIONAL_FIELDS:
            raise ValueError("optional field list out of sync")
        _check_unavailable(values, self.unavailable)
        return self


StatusField = Literal[
    "runtime_state", "execution_mode", "live_enabled", "readiness", "stop", "engine", "protections"
]
STATUS_OPTIONAL_FIELDS: tuple[str, ...] = (
    "runtime_state",
    "execution_mode",
    "live_enabled",
    "readiness",
    "stop",
    "engine",
    "protections",
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
    engine: EngineDiagnostics | None
    protections: Protections | None
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
            "engine": self.engine,
            "protections": self.protections,
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


# ---------------------------------------------------------------------------
# MCP-01f — GET /v1/positions (contratto 1.3.0)
# ---------------------------------------------------------------------------

PositionField = Literal[
    "open_size", "avg_entry_price", "realized_pnl", "unrealized_pnl", "exposure", "liability"
]
POSITION_OPTIONAL_FIELDS: tuple[str, ...] = (
    "open_size",
    "avg_entry_price",
    "realized_pnl",
    "unrealized_pnl",
    "exposure",
    "liability",
)
MAX_POSITIONS = 512


class Position(StrictModel):
    market_id: Identifier
    selection_id: Identifier
    side: Literal["BACK", "LAY", "FLAT"]
    table_id: Annotated[int, Field(ge=1, le=10_000)] | None
    open_size: DecimalStr | None
    avg_entry_price: DecimalStr | None
    realized_pnl: DecimalStr | None
    unrealized_pnl: DecimalStr | None
    exposure: DecimalStr | None
    liability: DecimalStr | None
    # LEDGER_DECIMAL: valori Decimal del registro di posizione, senza perdita. CORE_FLOAT: posizione
    # senza registro, solo prezzo e size come float del core (resto indisponibile).
    amounts_source: Literal["LEDGER_DECIMAL", "CORE_FLOAT"]
    # Il P&L non realizzato è quello dell'ultimo mark-to-market eseguito dal core, non ricalcolato.
    unrealized_basis: Literal["LAST_MARK"]
    unavailable: Annotated[
        tuple[PositionField, ...],
        Field(max_length=len(POSITION_OPTIONAL_FIELDS), json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _declared(self) -> Position:
        values: dict[str, object] = {
            "open_size": self.open_size,
            "avg_entry_price": self.avg_entry_price,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "exposure": self.exposure,
            "liability": self.liability,
        }
        if tuple(values) != POSITION_OPTIONAL_FIELDS:
            raise ValueError("optional field list out of sync")
        _check_unavailable(values, self.unavailable)
        if self.side == "FLAT" and self.exposure not in (None, "0"):
            raise ValueError("flat position with exposure")
        return self


PositionsField = Literal["positions"]


class PositionsResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    consistency: SectionConsistency
    # Tutte le posizioni in una sola acquisizione del lock del motore P&L.
    positions: Annotated[tuple[Position, ...], Field(max_length=MAX_POSITIONS)] | None
    unavailable: Annotated[
        tuple[PositionsField, ...], Field(max_length=1, json_schema_extra={"uniqueItems": True})
    ]

    @model_validator(mode="after")
    def _declared(self) -> PositionsResponse:
        _check_unavailable({"positions": self.positions}, self.unavailable)
        return self
