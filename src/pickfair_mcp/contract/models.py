"""Modelli pydantic del contratto Control API v1 (base)."""

from __future__ import annotations

import itertools
import re
from decimal import Decimal
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
NON_NEGATIVE_DECIMAL_PATTERN = r"^(?:[1-9][0-9]{0,14}(?:\.[0-9]{1,28})?|0(?:\.[0-9]{1,28})?)$"
NonNegativeDecimal = Annotated[
    str, StringConstraints(pattern=NON_NEGATIVE_DECIMAL_PATTERN, max_length=48)
]
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
    # MCP-01m (F-18 di Claude D): impostazioni persistite illeggibili => il core nega ogni nuova entrata.
    config_validity: Protection


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
    "config_validity",
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
    # MCP-01h: barriere di cashout attive (una per richiesta di cashout in corso).
    cashout_barriers: Count
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


CheckpointStage = Literal[
    "SETTLEMENT_DETECTED",
    "BANKROLL_SYNC_DONE",
    "MM_DECISION_DONE",
    "NEXT_TRADE_SUBMIT_ATTEMPTED",
    "NEXT_TRADE_SUBMIT_CONFIRMED",
    "CYCLE_BLOCKED",
    "CYCLE_AMBIGUOUS",
    "UNKNOWN",
]


class OutcomeCount(StrictModel):
    outcome: Code
    count: Annotated[int, Field(ge=1, le=10**12)]


class StageCount(StrictModel):
    stage: CheckpointStage
    count: Annotated[int, Field(ge=1, le=10**12)]


class SettlementEffects(StrictModel):
    """Tabella `settlement_effects` (letta in sola lettura): conteggi per esito, mai i payload."""

    held: Annotated[int, Field(ge=0, le=10**12)]
    not_realized: Annotated[int, Field(ge=0, le=10**12)]
    by_outcome: Annotated[tuple[OutcomeCount, ...], Field(max_length=32)]

    @model_validator(mode="after")
    def _coherent(self) -> SettlementEffects:
        outcomes = [o.outcome for o in self.by_outcome]
        if len(set(outcomes)) != len(outcomes):
            raise ValueError("duplicate outcome")
        held = next((o.count for o in self.by_outcome if o.outcome == "HELD"), 0)
        if held != self.held:
            raise ValueError("held count disagrees with the outcome breakdown")
        return self


class CycleCheckpoints(StrictModel):
    """Tabella `cycle_recovery_checkpoints`: checkpoint del ciclo dopo ogni settlement, per fase."""

    by_stage: Annotated[tuple[StageCount, ...], Field(max_length=8)]
    cycle_ambiguous: Annotated[int, Field(ge=0, le=10**12)]
    submit_ambiguous: Annotated[int, Field(ge=0, le=10**12)]

    @model_validator(mode="after")
    def _unique(self) -> CycleCheckpoints:
        stages = [s.stage for s in self.by_stage]
        if len(set(stages)) != len(stages):
            raise ValueError("duplicate stage")
        return self


SettlementField = Literal["effects", "checkpoints", "sim_settlements"]
SETTLEMENT_OPTIONAL_FIELDS: tuple[str, ...] = ("effects", "checkpoints", "sim_settlements")


class SettlementState(StrictModel):
    """MCP-01h: stato dei settlement. Solo conteggi: nessun payload, riferimento o nome evento."""

    # Settlement ricevuti ma non ancora registrati (in memoria, ritentati dal core).
    unrecorded_settlements: Count
    # Lotti Dutching trattenuti in attesa di riconciliazione.
    held_batches: Count
    effects: SettlementEffects | None
    checkpoints: CycleCheckpoints | None
    # Settlement registrati dal broker SIM; null in LIVE (nessun registro in memoria).
    sim_settlements: Count | None
    unavailable: Annotated[
        tuple[SettlementField, ...],
        Field(max_length=len(SETTLEMENT_OPTIONAL_FIELDS), json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _declared(self) -> SettlementState:
        values: dict[str, object] = {
            "effects": self.effects,
            "checkpoints": self.checkpoints,
            "sim_settlements": self.sim_settlements,
        }
        if tuple(values) != SETTLEMENT_OPTIONAL_FIELDS:
            raise ValueError("optional field list out of sync")
        _check_unavailable(values, self.unavailable)
        return self


ReconciliationField = Literal[
    "startup",
    "ambiguities_pending",
    "ghosts",
    "hedge_registry_unreliable",
    "recovery_state",
    "settlement",
]
RECONCILIATION_OPTIONAL_FIELDS: tuple[str, ...] = (
    "startup",
    "ambiguities_pending",
    "ghosts",
    "hedge_registry_unreliable",
    "recovery_state",
    "settlement",
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
    settlement: SettlementState | None
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
            "settlement": self.settlement,
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


class Trailing(StrictModel):
    """Trailing stop del tavolo (MCP-01m, F-03 di Claude D), dal `meta` del tavolo e dal picco persistito.

    NOT_IN_CORE: il core non ha la logica di trailing (prima di F-03): la percentuale, se configurata, non è
    applicata. OFF: percentuale assente o non valida (il core lo tratta come spento). WAITING_PROFIT: attivo, nessun
    profitto garantito ancora (nessun picco). ARMED: picco > 0, soglia calcolata dal core. TRIGGERED: il core ha
    segnato lo scatto del trailing. UNKNOWN: picco persistito illeggibile (il core non decide: fail-closed).
    """

    state: Literal["NOT_IN_CORE", "OFF", "WAITING_PROFIT", "ARMED", "TRIGGERED", "UNKNOWN"]
    pct: NonNegativeDecimal | None
    peak: NonNegativeDecimal | None
    threshold: NonNegativeDecimal | None
    peak_source: Literal["MEMORY", "PERSISTED", "NONE"]

    @model_validator(mode="after")
    def _coherent(self) -> Trailing:
        has_peak = self.peak is not None
        if (self.peak_source == "NONE") == has_peak:
            raise ValueError("peak and peak_source disagree")
        if self.state in ("NOT_IN_CORE", "OFF", "WAITING_PROFIT", "UNKNOWN") and (
            has_peak or self.threshold is not None
        ):
            raise ValueError("peak or threshold without an armed trailing")
        if self.state in ("WAITING_PROFIT", "ARMED", "TRIGGERED") and self.pct is None:
            raise ValueError("active trailing without a percentage")
        if self.state == "OFF" and self.pct is not None:
            raise ValueError("OFF trailing with a valid percentage")
        if self.state == "ARMED" and (not has_peak or self.threshold is None):
            raise ValueError("ARMED trailing without peak and threshold")
        if (
            self.peak is not None
            and self.threshold is not None
            and Decimal(self.threshold) > Decimal(self.peak)
        ):
            raise ValueError("threshold above the peak")
        return self


class SlTp(StrictModel):
    """SL/TP del tavolo (MCP-01h, contratto 1.5.0), letto dal `meta` del tavolo del core.

    NOT_ARMED: nessun importo SL/TP sul tavolo (oggi sempre, sul `main` del core: nessun percorso
    li arma prima di F-02 di Claude D). ARMED: almeno un importo. TRIGGERED: il core ha segnato lo
    scatto di SL o TP (`sl_tp_triggered`). UNKNOWN: valori presenti ma illeggibili. Il trailing ha il suo
    stato in `trailing` (MCP-01m): uno scatto del trailing non cambia lo stato di SL/TP.
    """

    state: Literal["NOT_ARMED", "ARMED", "TRIGGERED", "UNKNOWN"]
    stop_loss: NonNegativeDecimal | None
    take_profit: NonNegativeDecimal | None
    stop_loss_pct: NonNegativeDecimal | None
    take_profit_pct: NonNegativeDecimal | None
    trailing_stop_pct: NonNegativeDecimal | None
    trailing: Trailing

    @model_validator(mode="after")
    def _coherent(self) -> SlTp:
        has_amount = self.stop_loss is not None or self.take_profit is not None
        if self.state == "NOT_ARMED" and has_amount:
            raise ValueError("NOT_ARMED table with SL/TP amounts")
        if self.state in ("ARMED", "TRIGGERED") and not has_amount:
            raise ValueError("ARMED/TRIGGERED table without SL/TP amounts")
        return self


class RoserpinaTable(StrictModel):
    table_id: Annotated[int, Field(ge=1, le=10_000)]
    status: TableStatus
    occupied: bool
    in_recovery: bool
    market_id: Identifier | None
    selection_id: Identifier | None
    current_exposure: Money
    loss_amount: Money
    sl_tp: SlTp


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
# ------------------------------------------------------------------ MCP-01i: chiusura SL/TP (F-04)

CloseState = Literal["CLAIMED", "ROUTED", "NOT_EXECUTED", "UNCERTAIN", "UNKNOWN"]
MAX_CLOSES = 64
MAX_CLOSE_BETS = 32


class ClosePosition(StrictModel):
    """Ordini della posizione nel ledger, con la stessa mappa degli stati di `list_orders`."""

    orders: Count
    partially_matched: Count
    in_reconciliation: Count
    ambiguous: Count
    unreadable: Count

    @model_validator(mode="after")
    def _bounded(self) -> ClosePosition:
        if max(self.partially_matched, self.in_reconciliation, self.ambiguous) > self.orders:
            raise ValueError("position counters exceed the orders read")
        return self


class CloseHedges(StrictModel):
    """Righe d'hedge della chiusura: legate dal record F-04 (`cashout_request_ids`) alla riga del ledger
    (`cashout_request_id`). `not_in_ledger`: richieste pubblicate senza riga d'hedge nel ledger."""

    requests: Count
    pending: Count
    placed: Count
    unmatched: Count
    ambiguous: Count
    failed: Count
    not_in_ledger: Count

    @model_validator(mode="after")
    def _bounded(self) -> CloseHedges:
        if self.not_in_ledger > self.requests:
            raise ValueError("more missing hedge rows than requests")
        if self.requests == 0 and (self.pending or self.placed or self.unmatched or self.ambiguous
                                   or self.failed):
            raise ValueError("hedge rows without a recorded request")
        return self


class SlTpClose(StrictModel):
    """Chiusura SL/TP persistita da F-04 (`risk.sl_tp_close.<customer_ref>`; il riferimento non esce)."""

    table_id: Annotated[int, Field(ge=1, le=10_000)]
    market_id: Identifier
    selection_id: Identifier
    side: Literal["BACK", "LAY"]
    trigger: Literal["STOP_LOSS", "TAKE_PROFIT", "TRAILING_STOP", "UNKNOWN"]
    close_state: CloseState
    # Dal core (`REROUTABLE_STATES`): solo NOT_EXECUTED si ritenta, e solo con un nuovo scatto.
    retryable: bool
    detail: Code | None
    recorded_at: EpochSeconds | None
    bet_ids: Annotated[tuple[Identifier, ...], Field(max_length=MAX_CLOSE_BETS)]
    position: ClosePosition
    # Esposizione del tavolo se il tavolo porta ancora questa posizione; altrimenti null.
    residual_exposure: NonNegativeDecimal | None
    residual_source: Literal["TABLE", "TABLE_RELEASED", "UNAVAILABLE"]
    # null: record senza `cashout_request_ids` (forma precedente di F-04), legame non dimostrabile.
    hedges: CloseHedges | None

    @model_validator(mode="after")
    def _coherent(self) -> SlTpClose:
        if (self.residual_exposure is not None) != (self.residual_source == "TABLE"):
            raise ValueError("residual exposure only from the table that holds the position")
        if self.retryable and self.close_state != "NOT_EXECUTED":
            raise ValueError("only NOT_EXECUTED closes are retryable")
        if self.close_state in ("ROUTED", "CLAIMED", "UNCERTAIN") and not self.bet_ids:
            raise ValueError("a claimed close always has the position bet ids")
        if len(set(self.bet_ids)) != len(self.bet_ids):
            raise ValueError("duplicate bet ids")
        return self


class SlTpClosesRead(StrictModel):
    state: Literal["OK", "PARTIAL"]
    reason: Code | None
    closes: Annotated[tuple[SlTpClose, ...], Field(max_length=MAX_CLOSES)]
    omitted: Count
    truncated: bool

    @model_validator(mode="after")
    def _coherent(self) -> SlTpClosesRead:
        if self.state == "OK" and (self.reason or self.omitted or self.truncated):
            raise ValueError("OK closes with omissions or a reason")
        if self.state == "PARTIAL" and not (self.reason and (self.omitted or self.truncated)):
            raise ValueError("PARTIAL closes must say what is missing")
        return self


class SlTpClosesMissing(StrictModel):
    """UNAVAILABLE (core senza F-04: CORE_PENDING_F04, o DB non leggibile) o UNKNOWN (DB occupato)."""

    state: Literal["UNKNOWN", "UNAVAILABLE"]
    reason: Code


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
    # MCP-01i: chiusure SL/TP persistite dal core (F-04), lette in una transazione di sola lettura.
    sl_tp_closes: SlTpClosesRead | SlTpClosesMissing

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


# ---------------------------------------------------------------------------
# MCP-01g — GET /v1/orders (contratto 1.4.0)
#
# Fonte: il ledger `orders` del core (stato durevole del ciclo di vita dell'ordine), letto in UNA
# transazione di sola lettura. Stati: mappa ESPLICITA dagli stati reali del core; nessuno stato
# inventato. APPROVED, CANCELLED e SETTLED non esistono nel ledger degli ordini: non compaiono.
# ---------------------------------------------------------------------------

_ACCEPTED_FAMILY = ("ACCEPTED", "UNMATCHED", "PARTIALLY_MATCHED", "MATCHED")
# stato del core -> stati di contratto ammessi. Le suddivisioni UNMATCHED / PARTIALLY_MATCHED /
# MATCHED di un ordine accettato si usano solo con quantità abbinata E residua esplicite.
ORDER_STATUS_MAP: dict[str, tuple[str, ...]] = {
    "INFLIGHT": ("PENDING",),
    "HEDGE_PENDING": ("PENDING",),
    "SUBMITTED": _ACCEPTED_FAMILY,
    "ACCEPTED_FOR_PROCESSING": _ACCEPTED_FAMILY,
    "HEDGE_PLACED": _ACCEPTED_FAMILY,
    "HEDGE_UNMATCHED": ("UNMATCHED",),
    "COMPLETED": ("MATCHED",),
    "FAILED": ("FAILED",),
    "HEDGE_FAILED": ("FAILED",),
    "DENIED": ("REJECTED",),
    "DUPLICATE_BLOCKED": ("DUPLICATE_BLOCKED",),
    "AMBIGUOUS": ("AMBIGUOUS",),
    "HEDGE_AMBIGUOUS": ("AMBIGUOUS",),
}
OrderStatus = Literal[
    "PENDING",
    "ACCEPTED",
    "UNMATCHED",
    "PARTIALLY_MATCHED",
    "MATCHED",
    "AMBIGUOUS",
    "REJECTED",
    "FAILED",
    "DUPLICATE_BLOCKED",
    "UNKNOWN",
]
OrderField = Literal[
    "bet_id",
    "market_id",
    "selection_id",
    "side",
    "price",
    "stake",
    "size_matched",
    "avg_price_matched",
    "size_remaining",
    "table_id",
]
ORDER_OPTIONAL_FIELDS: tuple[str, ...] = (
    "bet_id",
    "market_id",
    "selection_id",
    "side",
    "price",
    "stake",
    "size_matched",
    "avg_price_matched",
    "size_remaining",
    "table_id",
)
MAX_ORDERS = 500


# MCP-01k: esito non confermato dal core (AMBIGUOUS, PENDING). Un report conservato nella risposta (es. la
# risposta senza esito del fix P0 di Claude D) non è un dato: importi abbinati e residui sempre null.
UNCONFIRMED_ORDER_STATUSES: frozenset[str] = frozenset({"AMBIGUOUS", "PENDING"})


class OrderReconciliation(StrictModel):
    # Stato non terminale del ledger che la riconciliazione del core considera aperto.
    in_reconciliation: bool
    # Presente nel registro delle ambiguità del ReconciliationEngine (in memoria).
    in_engine_queue: bool
    finalized: bool
    ambiguity_reason: Code | None


class Order(StrictModel):
    local_id: Annotated[int, Field(ge=1, le=10**15)]
    bet_id: Identifier | None
    # ENTRY: ingresso del bot; HEDGE: hedge di un cashout (core/hedge_ref.py); DUTCHING_LEG: gamba
    # di un lotto Dutching.
    role: Literal["ENTRY", "HEDGE", "DUTCHING_LEG"]
    core_status: Code
    status: OrderStatus
    market_id: Identifier | None
    selection_id: Identifier | None
    side: Literal["BACK", "LAY"] | None
    price: DecimalStr | None
    stake: DecimalStr | None
    size_matched: DecimalStr | None
    avg_price_matched: DecimalStr | None
    size_remaining: DecimalStr | None
    table_id: Annotated[int, Field(ge=1, le=10_000)] | None
    created_at: EpochSeconds
    updated_at: EpochSeconds
    reconciliation: OrderReconciliation
    # Confronto col broker SIM (ordini correnti in memoria): PRESENT/ABSENT; in LIVE o senza betId
    # NOT_CHECKED (il core LIVE non tiene ordini in memoria: nessuna chiamata di rete per saperlo).
    broker_view: Literal["PRESENT", "ABSENT", "NOT_CHECKED"]
    unavailable: Annotated[
        tuple[OrderField, ...],
        Field(max_length=len(ORDER_OPTIONAL_FIELDS), json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _coherent(self) -> Order:
        values: dict[str, object] = {
            "bet_id": self.bet_id,
            "market_id": self.market_id,
            "selection_id": self.selection_id,
            "side": self.side,
            "price": self.price,
            "stake": self.stake,
            "size_matched": self.size_matched,
            "avg_price_matched": self.avg_price_matched,
            "size_remaining": self.size_remaining,
            "table_id": self.table_id,
        }
        if tuple(values) != ORDER_OPTIONAL_FIELDS:
            raise ValueError("optional field list out of sync")
        _check_unavailable(values, self.unavailable)
        if self.status not in ORDER_STATUS_MAP.get(self.core_status, ("UNKNOWN",)):
            raise ValueError("status does not follow the core status map")
        if self.status in ("UNMATCHED", "PARTIALLY_MATCHED", "MATCHED") and (
            ORDER_STATUS_MAP.get(self.core_status) == _ACCEPTED_FAMILY
        ):
            if self.size_matched is None or self.size_remaining is None:
                raise ValueError("matched split without explicit sizes")
            matched, remaining = Decimal(self.size_matched), Decimal(self.size_remaining)
            expected = (
                "MATCHED"
                if remaining == 0 and matched > 0
                else "UNMATCHED"
                if matched == 0 and remaining > 0
                else "PARTIALLY_MATCHED"
                if matched > 0 and remaining > 0
                else None
            )
            if self.status != expected:
                raise ValueError("matched split disagrees with the sizes")
        if self.status in UNCONFIRMED_ORDER_STATUSES and (
            self.size_matched is not None
            or self.avg_price_matched is not None
            or self.size_remaining is not None
        ):
            raise ValueError("unconfirmed order with matched or remaining amounts")
        if self.broker_view != "NOT_CHECKED" and self.bet_id is None:
            raise ValueError("broker comparison without a bet id")
        return self


def _unique_orders(values: tuple[Order, ...]) -> tuple[Order, ...]:
    ids = [o.local_id for o in values]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate local_id")
    return values


class OrdersSnapshotRead(StrictModel):
    """Lettura riuscita. OK: completa. PARTIAL: righe illeggibili omesse o elenco troncato.
    STALE: letta, ma la riconciliazione d'avvio del core non è conclusa (può non riflettere
    l'exchange)."""

    state: Literal["OK", "PARTIAL", "STALE"]
    reason: Code | None
    orders: Annotated[
        tuple[Order, ...], Field(max_length=MAX_ORDERS), AfterValidator(_unique_orders)
    ]
    omitted: Count
    truncated: bool

    @model_validator(mode="after")
    def _coherent(self) -> OrdersSnapshotRead:
        if self.state == "OK" and (self.reason or self.omitted or self.truncated):
            raise ValueError("OK snapshot with omissions or a reason")
        if self.state == "PARTIAL" and not (self.reason and (self.omitted or self.truncated)):
            raise ValueError("PARTIAL snapshot must say what is missing")
        if self.state == "STALE" and not self.reason:
            raise ValueError("STALE snapshot must say why")
        return self


class OrdersSnapshotMissing(StrictModel):
    """Lettura non riuscita: UNKNOWN (database occupato) o UNAVAILABLE (non leggibile)."""

    state: Literal["UNKNOWN", "UNAVAILABLE"]
    reason: Code


class OrdersResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    # Tutte le righe da una sola transazione di lettura: nessun ordine a metà fra due stati.
    consistency: Literal["SINGLE_READ_TRANSACTION"]
    snapshot: OrdersSnapshotRead | OrdersSnapshotMissing


# ------------------------------------------------------------------ MCP-01j: get_config

# Allowlist ESPLICITA delle impostazioni operative esposte (campi di `RoserpinaConfig` nel core,
# `core/system_state.py`). Nient'altro della configurazione esce: credenziali Betfair, Telegram,
# certificati e impostazioni persistite non sono mai lette dalla vista. Un campo nuovo del core
# non entra da solo: compare per nome in `unlisted` (mai il valore) finché il contratto non lo
# aggiunge qui.
CONFIG_KEYS: dict[str, str] = {
    "target_profit_cycle_pct": "DECIMAL",
    "max_single_bet_pct": "DECIMAL",
    "max_total_exposure_pct": "DECIMAL",
    "max_event_exposure_pct": "DECIMAL",
    "max_daily_loss": "DECIMAL",
    "max_drawdown_hard_stop_pct": "DECIMAL",
    "max_open_exposure": "DECIMAL",
    "max_order_exposure": "DECIMAL",
    "max_market_exposure": "DECIMAL",
    "max_event_exposure_abs": "DECIMAL",
    "max_drawdown_abs": "DECIMAL",
    "max_session_loss": "DECIMAL",
    "max_exposure_stop": "DECIMAL",
    "max_recovery_chase_abs": "DECIMAL",
    "auto_reset_drawdown_pct": "DECIMAL",
    "defense_drawdown_pct": "DECIMAL",
    "lockdown_drawdown_pct": "DECIMAL",
    "expansion_profit_pct": "DECIMAL",
    "expansion_multiplier": "DECIMAL",
    "defense_multiplier": "DECIMAL",
    "risk_profile": "ENUM",
    "table_count": "INT",
    "max_recovery_tables": "INT",
    "allow_recovery": "BOOL",
    "anti_duplication_enabled": "BOOL",
    "commission_pct": "DECIMAL",
    "min_stake": "DECIMAL",
    "max_stake_abs": "DECIMAL",
    "book_warning": "DECIMAL",
    "book_block": "DECIMAL",
    "liquidity_guard_enabled": "BOOL",
    "liquidity_multiplier": "DECIMAL",
    "min_liquidity_absolute": "DECIMAL",
    "liquidity_warning_only": "BOOL",
    "min_price": "DECIMAL",
    "max_win": "DECIMAL",
    "max_win_warning_only": "BOOL",
    "max_stake_pct": "DECIMAL",
    "profit_epsilon": "DECIMAL",
    "profit_epsilon_enabled": "BOOL",
    "auto_green_delay_enabled": "BOOL",
    "auto_green_delay_sec": "DECIMAL",
    # MCP-01m: percentuali di default della posizione (F-02 di Claude D)
    "stop_loss_pct": "DECIMAL",
    "take_profit_pct": "DECIMAL",
    "trailing_stop_pct": "DECIMAL",
}

# Campi `Optional` del core: `None` = non configurato (limite non attivo o percentuale mancante,
# che il core tratta come blocco). Solo questi possono essere NOT_SET; per gli altri un valore
# assente è INVALID.
OPTIONAL_CONFIG_KEYS: frozenset[str] = frozenset({
    "target_profit_cycle_pct", "max_single_bet_pct", "max_total_exposure_pct",
    "max_event_exposure_pct", "max_daily_loss", "max_drawdown_hard_stop_pct",
    "max_open_exposure", "max_order_exposure", "max_market_exposure", "max_event_exposure_abs",
    "max_drawdown_abs", "max_session_loss", "max_exposure_stop", "max_recovery_chase_abs",
    "max_stake_abs", "max_win", "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
})

# Frammenti che un nome in `unlisted` non può contenere: seconda barriera, oltre al filtro
# `core.redaction.is_sensitive_key` del core, contro la fuga anche solo del NOME di un segreto.
SENSITIVE_NAME_FRAGMENTS: tuple[str, ...] = (
    "token", "secret", "password", "passwd", "auth", "bearer", "key", "session", "api",
    "cert", "cookie", "ssoid", "private", "credential", "hash", "pin",
)

ConfigKey = Literal[tuple(CONFIG_KEYS)]  # type: ignore[valid-type]
SettingState = Literal["SET", "NOT_SET", "INVALID"]
RiskProfile = Literal["CONSERVATIVE", "BALANCED", "AGGRESSIVE"]
FieldName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
MAX_UNLISTED = 64


class _SettingBase(StrictModel):
    key: ConfigKey
    # SET = valore leggibile e restituito; NOT_SET = campo opzionale non configurato;
    # INVALID = valore presente ma illeggibile (tipo errato, NaN/inf): mai convertito in zero.
    state: SettingState

    def _value(self) -> object:
        raise NotImplementedError

    @model_validator(mode="after")
    def _state_matches_value(self) -> _SettingBase:
        if (self.state == "SET") != (self._value() is not None):
            raise ValueError("value present iff state is SET")
        return self


class DecimalSetting(_SettingBase):
    kind: Literal["DECIMAL"]
    value: DecimalStr | None

    def _value(self) -> object:
        return self.value


class BoolSetting(_SettingBase):
    kind: Literal["BOOL"]
    value: bool | None

    def _value(self) -> object:
        return self.value


class IntSetting(_SettingBase):
    kind: Literal["INT"]
    value: Annotated[int, Field(ge=-1_000_000_000, le=1_000_000_000)] | None

    def _value(self) -> object:
        return self.value


class EnumSetting(_SettingBase):
    kind: Literal["ENUM"]
    value: RiskProfile | None

    def _value(self) -> object:
        return self.value


ConfigSetting = DecimalSetting | BoolSetting | IntSetting | EnumSetting


def _check_unlisted(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("duplicate unlisted names")
    for name in values:
        if name in CONFIG_KEYS:
            raise ValueError("listed key reported as unlisted")
        if any(fragment in name for fragment in SENSITIVE_NAME_FRAGMENTS):
            raise ValueError("sensitive field name must be redacted, not listed")
    return values


# Solo impostazioni di Roserpina (`roserpina.<nome>`) o nomi semplici: credenziali Betfair/Telegram escluse per forma.
SettingKeyName = Annotated[
    str, StringConstraints(pattern=r"^(roserpina\.)?[a-z][a-z0-9_]{0,63}$", max_length=80)
]


def _check_invalid_persisted(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("duplicate invalid setting names")
    for name in values:
        bare = name.removeprefix("roserpina.")  # «roserpina» contiene «pin»: si controlla il nome
        if any(fragment in bare for fragment in SENSITIVE_NAME_FRAGMENTS):
            raise ValueError("sensitive setting name must be redacted, not listed")
    return values


class ConfigResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    # Il core sostituisce la configurazione per riferimento (`reload_config`): un solo riferimento
    # letto => tutte le impostazioni appartengono alla stessa versione della configurazione.
    consistency: Literal["SINGLE_REFERENCE_READ"]
    settings: Annotated[tuple[ConfigSetting, ...], Field(max_length=len(CONFIG_KEYS))] | None
    unlisted: Annotated[
        tuple[FieldName, ...], Field(max_length=MAX_UNLISTED), AfterValidator(_check_unlisted)
    ]
    redacted: Count
    # MCP-01m (F-18 di Claude D): chiavi persistite illeggibili o fuori dominio (il core nega ogni nuova
    # entrata finché ce n'è una). null se il core non le registra (prima di F-18).
    invalid_persisted: (
        Annotated[
            tuple[SettingKeyName, ...], Field(max_length=64), AfterValidator(_check_invalid_persisted)
        ]
        | None
    )
    unavailable: Annotated[
        tuple[Literal["settings", "invalid_persisted"], ...],
        Field(max_length=2, json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _complete(self) -> ConfigResponse:
        _check_unavailable(
            {"settings": self.settings, "invalid_persisted": self.invalid_persisted}, self.unavailable
        )
        if self.settings is None:
            return self
        if tuple(s.key for s in self.settings) != tuple(CONFIG_KEYS):
            raise ValueError("settings must list every contract key once, in contract order")
        for s in self.settings:
            if s.kind != CONFIG_KEYS[s.key]:
                raise ValueError("setting kind does not match the contract")
            if s.state == "NOT_SET" and s.key not in OPTIONAL_CONFIG_KEYS:
                raise ValueError("only optional settings can be NOT_SET")
        return self


# ------------------------------------------------------------------ MCP-01l: mercati e book

# Identificativo di mercato Betfair («1.234567»): stretto, mai «.» o «..», usabile in un percorso.
MARKET_ID_PATTERN = r"^[0-9]{1,4}\.[0-9]{1,15}$"
MarketId = Annotated[str, StringConstraints(pattern=MARKET_ID_PATTERN, max_length=20)]
# Stato del mercato COME LO RIPORTA IL BOOK ricevuto (dato Betfair), non un giudizio di negoziabilità del
# core: quello è F-23 (Claude D), la protezione `market_tradability` resta la fonte del giudizio.
BookStatus = Literal["OPEN", "SUSPENDED", "CLOSED", "INACTIVE", "UNKNOWN"]
RunnerStatus = Literal["ACTIVE", "REMOVED", "WINNER", "LOSER", "PLACED", "HIDDEN", "UNKNOWN"]
MAX_MARKETS = 256
MAX_RUNNERS = 64
MAX_LEVELS = 3


class MarketSummary(StrictModel):
    market_id: MarketId
    book_status: BookStatus
    inplay: bool | None
    runners: Annotated[int, Field(ge=0, le=1000)]
    total_matched: NonNegativeDecimal | None
    last_match_time: EpochSeconds | None
    # MCP-01n: età (s) dell'ultimo book ricevuto (istante monotono del tracker, Claude D);
    # null se ignota.
    book_age_s: NonNegativeDecimal | None


def _unique_markets(values: tuple[MarketSummary, ...]) -> tuple[MarketSummary, ...]:
    ids = [m.market_id for m in values]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate market_id")
    if ids != sorted(ids):
        raise ValueError("markets must be sorted by market_id")
    return values


class MarketsResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    # Copia del dizionario dei book del MarketTracker in una sola operazione: ogni book è l'ultimo
    # ricevuto per quel mercato; l'età del book è nota solo se il book riporta `lastMatchTime`.
    consistency: Literal["SINGLE_REFERENCE_READ"]
    markets: (
        Annotated[
            tuple[MarketSummary, ...], Field(max_length=MAX_MARKETS), AfterValidator(_unique_markets)
        ]
        | None
    )
    omitted: Count
    truncated: bool
    unavailable: Annotated[
        tuple[Literal["markets"], ...], Field(max_length=1, json_schema_extra={"uniqueItems": True})
    ]

    @model_validator(mode="after")
    def _declared(self) -> MarketsResponse:
        _check_unavailable({"markets": self.markets}, self.unavailable)
        if self.markets is None and (self.omitted or self.truncated):
            raise ValueError("omissions without a market list")
        return self


class PriceLevel(StrictModel):
    price: NonNegativeDecimal
    size: NonNegativeDecimal


class RunnerBook(StrictModel):
    selection_id: Identifier
    status: RunnerStatus
    last_price_traded: NonNegativeDecimal | None
    total_matched: NonNegativeDecimal | None
    # Migliori livelli disponibili: BACK in ordine di prezzo decrescente, LAY crescente, come nel book.
    back: Annotated[tuple[PriceLevel, ...], Field(max_length=MAX_LEVELS)]
    lay: Annotated[tuple[PriceLevel, ...], Field(max_length=MAX_LEVELS)]

    @model_validator(mode="after")
    def _ordered(self) -> RunnerBook:
        back = [Decimal(level.price) for level in self.back]
        lay = [Decimal(level.price) for level in self.lay]
        if back != sorted(back, reverse=True) or lay != sorted(lay):
            raise ValueError("price ladder out of order")
        return self


class MarketBook(StrictModel):
    book_status: BookStatus
    inplay: bool | None
    total_matched: NonNegativeDecimal | None
    last_match_time: EpochSeconds | None
    runners: Annotated[tuple[RunnerBook, ...], Field(max_length=MAX_RUNNERS)]
    omitted_runners: Count
    book_age_s: NonNegativeDecimal | None

    @model_validator(mode="after")
    def _unique(self) -> MarketBook:
        ids = [r.selection_id for r in self.runners]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate selection_id")
        return self


class MarketBookResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    consistency: Literal["SINGLE_REFERENCE_READ"]
    market_id: MarketId
    # OK: book presente; NOT_TRACKED: Pickfair non ha un book per questo mercato (nessuna chiamata di rete
    # per procurarlo); UNAVAILABLE: book presente ma illeggibile o tracker non raggiungibile.
    state: Literal["OK", "NOT_TRACKED", "UNAVAILABLE"]
    book: MarketBook | None

    @model_validator(mode="after")
    def _coherent(self) -> MarketBookResponse:
        if (self.book is not None) != (self.state == "OK"):
            raise ValueError("book present iff state is OK")
        return self



# ------------------------------------------------- MCP-01o: scatola nera, sola lettura
# (PF-BLACKBOX-01)
#
# Vista di lettura del registro cronologico permanente del motore (architettura e scrittura: Claude
# B).
# Il lettore non inventa nulla: un campo che il motore non ha registrato vale null ed è elencato in
# `not_recorded` (un null fuori elenco vuol dire «non applicabile», es. nessuna causa); un
# tentativo (ATTEMPT) non è mai mostrato come confermato; i valori sensibili escono solo redatti.
# Convenzione del contratto: dove c'è `unavailable`, un campo è null se e solo se è elencato.

BLACKBOX_MAX_EVENTS = 500
BLACKBOX_MAX_GAPS = 64
BLACKBOX_MAX_CHAIN = 32
BLACKBOX_MAX_SESSIONS = 256
BLACKBOX_MAX_VALUES = 32
BLACKBOX_REDACTED = "[REDACTED]"
# Nomi di campo i cui valori non escono mai in chiaro (seconda redazione, difesa in profondità).
BLACKBOX_SENSITIVE_FRAGMENTS: tuple[str, ...] = (
    "token", "secret", "password", "passwd", "bearer", "credential", "cookie", "ssoid", "private",
    "api_key", "apikey", "application", "customer_ref", "certificate",
)
# Frammenti brevi: sensibili solo come segmento intero del nome (separato da _ . -), così
# `auth_header` è redatto e `stake_authorized` (diagnosi di Roserpina, G7) no.
BLACKBOX_SENSITIVE_SEGMENTS: tuple[str, ...] = ("auth", "authorization", "pem", "otp")

BlackboxSeq = Annotated[int, Field(ge=1, le=10**15)]
BlackboxEventId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
_UTC_MILLIS = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$"
UtcMillis = Annotated[str, StringConstraints(pattern=_UTC_MILLIS)]
# Vocabolario del motore (pf_blackbox_01 §3): anche TELEGRAM e CLI; livelli di
# event_journal.LEVELS.
BlackboxOrigin = Literal[
    "USER", "SYSTEM", "MCP", "CONTROL_API", "STRATEGY", "EXCHANGE", "TELEGRAM", "CLI"
]
BlackboxSeverity = Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
BlackboxPhase = Literal["ATTEMPT", "RESULT", "OBSERVATION"]
BlackboxOutcome = Literal["VERIFIED", "PENDING", "UNKNOWN", "REJECTED", "FAILED", "NOT_APPLICABLE"]
UpperCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
# Codice del motivo: anche il nome di un'eccezione (BB-1 registra `KeyError` per TASK_EXCEPTION).
ReasonCode = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")]
BlackboxCategory = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")]
# ASCII stampabile: BB-1 registra anche `thread:<nome del thread>` per le eccezioni dei thread.
BlackboxComponent = Annotated[str, StringConstraints(pattern=r"^[ -~]{1,64}$")]
# Ordine nella scatola nera: alias opaco di BB-1 (HMAC dell'id interno), mai l'id interno.
OrderAlias = Annotated[str, StringConstraints(pattern=r"^ord_[0-9a-f]{32}$")]
SessionKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ValueName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]{0,63}$")]
ShortText = Annotated[str, StringConstraints(max_length=256)]
BlackboxScalar = Annotated[str, StringConstraints(max_length=256)] | bool | Annotated[
    int, Field(ge=-(10**15), le=10**15)
] | None
StrategyName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
BetIdText = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,20}$")]

BlackboxRecordedField = Literal[
    "state_before", "state_after", "values_before", "values_after", "reason", "reason_code",
    "correlation_id", "causation_id", "process_id", "component", "data", "exchange_ts",
]


def _is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    if any(fragment in lowered for fragment in BLACKBOX_SENSITIVE_FRAGMENTS):
        return True
    return any(part in BLACKBOX_SENSITIVE_SEGMENTS for part in re.split(r"[_.\-]", lowered))


def _redacted_values(
    values: dict[str, BlackboxScalar] | None,
) -> dict[str, BlackboxScalar] | None:
    if values is not None:
        for name, value in values.items():
            if _is_sensitive_name(name) and value != BLACKBOX_REDACTED:
                raise ValueError("sensitive value not redacted")
    return values


BlackboxValues = Annotated[
    dict[ValueName, BlackboxScalar],
    Field(max_length=BLACKBOX_MAX_VALUES),
    AfterValidator(_redacted_values),
]


class BlackboxRefs(StrictModel):
    table_id: Annotated[int, Field(ge=1, le=9999)] | None
    market_id: MarketId | None
    selection_id: Annotated[int, Field(ge=1, le=10**12)] | None
    order_id: OrderAlias | None
    bet_id: BetIdText | None
    strategy: StrategyName | None


class BlackboxEvent(StrictModel):
    seq: BlackboxSeq
    event_id: BlackboxEventId
    # Ora osservata da Pickfair; l'ordine fa fede su seq.
    ts_utc: UtcMillis
    # Ora dichiarata dall'exchange, se c'è (mai inventata).
    exchange_ts: UtcMillis | None
    session_id: SessionKey
    process_id: Annotated[int, Field(ge=1, le=2**31)] | None
    component: BlackboxComponent | None
    origin: BlackboxOrigin
    category: BlackboxCategory
    event_type: UpperCode
    severity: BlackboxSeverity
    # ATTEMPT = ciò che Pickfair tenta; RESULT = ciò che risulta davvero; OBSERVATION = un fatto
    # osservato.
    phase: BlackboxPhase
    outcome: BlackboxOutcome
    state_before: Annotated[str, StringConstraints(max_length=64)] | None
    state_after: Annotated[str, StringConstraints(max_length=64)] | None
    values_before: BlackboxValues | None
    values_after: BlackboxValues | None
    reason: ShortText | None
    reason_code: ReasonCode | None
    correlation_id: SessionKey | None
    causation_id: BlackboxEventId | None
    refs: BlackboxRefs
    # Dettagli redatti dell'evento (es. la decisione di stake di Roserpina: bankroll, percentuale
    # MM,
    # stake teorico e autorizzato, riserve, commissioni, valuta), appiattiti con nomi puntati.
    data: BlackboxValues | None
    # Voci di values_before/values_after/data non rappresentabili (liste, valori oltre 256
    # caratteri,
    # oltre 32 voci, nomi fuori pattern): non mostrate e contate qui, mai troncate in silenzio.
    omitted_values: Count
    not_recorded: Annotated[
        tuple[BlackboxRecordedField, ...],
        Field(max_length=12, json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _coherent(self) -> BlackboxEvent:
        if self.phase == "ATTEMPT" and self.outcome != "PENDING":
            raise ValueError("an attempt is never shown as a result")
        if self.causation_id == self.event_id:
            raise ValueError("an event cannot cause itself")
        if len(set(self.not_recorded)) != len(self.not_recorded):
            raise ValueError("not_recorded repeated")
        recorded = {
            "state_before": self.state_before, "state_after": self.state_after,
            "values_before": self.values_before, "values_after": self.values_after,
            "reason": self.reason, "reason_code": self.reason_code,
            "correlation_id": self.correlation_id, "causation_id": self.causation_id,
            "process_id": self.process_id, "component": self.component, "data": self.data,
            "exchange_ts": self.exchange_ts,
        }
        for name in self.not_recorded:
            if recorded[name] is not None:
                raise ValueError("a field declared not recorded carries a value")
        return self


class BlackboxGap(StrictModel):
    from_seq: BlackboxSeq
    to_seq: BlackboxSeq
    # LOST: seq mai trovati; CORRUPT: record illeggibili o con checksum errato; RETENTION: rimossi
    # dalla
    # retention configurata (non una perdita).
    kind: Literal["LOST", "CORRUPT", "RETENTION"]

    @model_validator(mode="after")
    def _ordered(self) -> BlackboxGap:
        if self.from_seq > self.to_seq:
            raise ValueError("gap bounds inverted")
        return self


def _sorted_gaps(values: tuple[BlackboxGap, ...]) -> tuple[BlackboxGap, ...]:
    for a, b in itertools.pairwise(values):
        if b.from_seq <= a.to_seq:
            raise ValueError("gaps not sorted or overlapping")
    return values


BlackboxGaps = Annotated[
    tuple[BlackboxGap, ...], Field(max_length=BLACKBOX_MAX_GAPS), AfterValidator(_sorted_gaps)
]


class BlackboxWindow(StrictModel):
    """Finestra di tempo non registrata (lacuna per tempo di BB-1, es. arresto non pulito).

    Il motore sa solo che in quell'intervallo può essere successo qualcosa che non ha scritto:
    l'esito è sempre sconosciuto, mai «niente è successo»."""

    seq: BlackboxSeq  # record della lacuna (BLACKBOX_GAP) che la descrive
    from_ts: UtcMillis
    to_ts: UtcMillis
    reason_code: ReasonCode

    @model_validator(mode="after")
    def _ordered(self) -> BlackboxWindow:
        if self.from_ts > self.to_ts:
            raise ValueError("window bounds inverted")
        return self


def _strictly_increasing_seq(values: tuple[BlackboxEvent, ...]) -> tuple[BlackboxEvent, ...]:
    for a, b in itertools.pairwise(values):
        if b.seq <= a.seq:
            raise ValueError("events not in strictly increasing seq order")
    if len({e.event_id for e in values}) != len(values):
        raise ValueError("duplicate event_id")
    return values


class BlackboxEventsResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    consistency: Literal["SINGLE_READ_SNAPSHOT"]
    events: (
        Annotated[
            tuple[BlackboxEvent, ...],
            Field(max_length=BLACKBOX_MAX_EVENTS),
            AfterValidator(_strictly_increasing_seq),
        ]
        | None
    )
    # Cursore della pagina successiva: l'ultimo seq restituito; 0 = nessuna pagina successiva.
    next_after_seq: Annotated[int, Field(ge=0, le=10**15)]
    truncated: bool
    # Ultimo seq scritto al momento della lettura (0 = registro vuoto).
    as_of_seq: Annotated[int, Field(ge=0, le=10**15)] | None
    gaps_in_range: BlackboxGaps
    # Finestre di tempo nell'intervallo letto in cui il motore non ha potuto registrare.
    unrecorded_windows: Annotated[
        tuple[BlackboxWindow, ...], Field(max_length=BLACKBOX_MAX_GAPS)
    ]
    redacted: Count
    unavailable: Annotated[
        tuple[Literal["events", "as_of_seq"], ...],
        Field(max_length=2, json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _coherent(self) -> BlackboxEventsResponse:
        _check_unavailable({"events": self.events, "as_of_seq": self.as_of_seq}, self.unavailable)
        if self.events is None:
            no_page = (self.truncated or self.next_after_seq or self.gaps_in_range
                       or self.unrecorded_windows or self.redacted)
            if no_page:
                raise ValueError("pagination or gaps without events")
            return self
        if self.truncated != (self.next_after_seq != 0):
            raise ValueError("truncated iff a next cursor is given")
        # Il cursore è l'ultimo seq letto: almeno l'ultimo evento restituito (può superarlo se gli
        # ultimi
        # record della pagina erano corrotti e sono riportati come lacuna CORRUPT, mai riletti
        # all'infinito).
        if self.next_after_seq and self.events and self.next_after_seq < self.events[-1].seq:
            raise ValueError("the cursor is behind the last returned event")
        beyond = self.as_of_seq is not None and self.next_after_seq > self.as_of_seq
        if self.next_after_seq and beyond:
            raise ValueError("the cursor is beyond the reported write position")
        if self.as_of_seq is not None and self.events and self.events[-1].seq > self.as_of_seq:
            raise ValueError("event beyond the reported write position")
        return self


class BlackboxEventResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    consistency: Literal["SINGLE_READ_SNAPSHOT"]
    event_id: BlackboxEventId
    state: Literal["OK", "NOT_FOUND", "UNAVAILABLE"]
    event: BlackboxEvent | None
    # Catena causale verso l'alto (causation_id), dal più vicino; si ferma a un evento mancante.
    chain: Annotated[tuple[BlackboxEvent, ...], Field(max_length=BLACKBOX_MAX_CHAIN)]
    chain_truncated: bool
    chain_broken_at: BlackboxEventId | None
    redacted: Count

    @model_validator(mode="after")
    def _coherent(self) -> BlackboxEventResponse:
        if (self.event is not None) != (self.state == "OK"):
            raise ValueError("event present iff state is OK")
        if self.event is not None and self.event.event_id != self.event_id:
            raise ValueError("event does not match the requested id")
        has_chain = bool(self.chain or self.chain_truncated or self.chain_broken_at)
        if self.event is None and (has_chain or self.redacted):
            raise ValueError("chain without the event")
        expected = self.event.causation_id if self.event is not None else None
        for link in self.chain:
            if link.event_id != expected:
                raise ValueError("chain does not follow causation_id")
            expected = link.causation_id
        if self.chain_broken_at is not None and self.chain_broken_at != expected:
            raise ValueError("broken link is not the next cause")
        return self


class BlackboxSession(StrictModel):
    session_id: SessionKey
    process_id: Annotated[int, Field(ge=1, le=2**31)] | None
    started_at: UtcMillis
    # Ora dell'arresto registrato: solo per CLEAN_STOP (per un crash l'ora vera non è nota).
    ended_at: UtcMillis | None
    # Ora dell'ultimo evento registrato della sessione (per un crash: limite inferiore della fine).
    last_event_at: UtcMillis | None
    # RUNNING: sessione corrente; CLEAN_STOP: arresto registrato; CRASH_DETECTED: il motore ha
    # rilevato al
    # riavvio un arresto non pulito; UNRECORDED: nessun arresto registrato e nessuna rilevazione.
    end_reason: Literal["RUNNING", "CLEAN_STOP", "CRASH_DETECTED", "UNRECORDED"]
    first_seq: BlackboxSeq | None
    last_seq: BlackboxSeq | None

    @model_validator(mode="after")
    def _coherent(self) -> BlackboxSession:
        if (self.ended_at is None) != (self.end_reason != "CLEAN_STOP"):
            raise ValueError("ended_at present iff a clean stop was recorded")
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("session ends before it starts")
        if self.last_event_at is not None and self.last_event_at < self.started_at:
            raise ValueError("last event before the session start")
        if self.ended_at is not None and self.last_event_at != self.ended_at:
            raise ValueError("a clean stop is the last recorded event")
        if (self.first_seq is None) != (self.last_seq is None):
            raise ValueError("seq range incomplete")
        if (self.first_seq is not None and self.last_seq is not None
                and self.first_seq > self.last_seq):
            raise ValueError("seq range inverted")
        return self


class BlackboxSessionsResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    consistency: Literal["SINGLE_READ_SNAPSHOT"]
    sessions: Annotated[tuple[BlackboxSession, ...], Field(max_length=BLACKBOX_MAX_SESSIONS)] | None
    truncated: bool
    unavailable: Annotated[
        tuple[Literal["sessions"], ...],
        Field(max_length=1, json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _coherent(self) -> BlackboxSessionsResponse:
        _check_unavailable({"sessions": self.sessions}, self.unavailable)
        if self.sessions is None and self.truncated:
            raise ValueError("truncated without sessions")
        if self.sessions is not None:
            if len({s.session_id for s in self.sessions}) != len(self.sessions):
                raise ValueError("duplicate session")
            if sum(1 for s in self.sessions if s.end_reason == "RUNNING") > 1:
                raise ValueError("more than one running session")
        return self


class BlackboxStatusResponse(StrictModel):
    source: Source
    observed_at: ObservedAt
    consistency: Literal["PER_FIELD_NON_ATOMIC"]
    available: bool
    # BB-1: registro degradato (una scrittura non critica fallita) e scritture non critiche perse.
    degraded: bool | None
    dropped_non_critical: Count | None
    first_seq: BlackboxSeq | None
    last_seq: BlackboxSeq | None
    retained_from_seq: BlackboxSeq | None
    gaps: BlackboxGaps
    gaps_truncated: bool
    corrupt_records: Count | None
    sessions: Count | None
    current_session_id: SessionKey | None
    last_write_error_code: UpperCode | None
    last_durable_write_at: UtcMillis | None
    retention_days: Annotated[int, Field(ge=1, le=36500)] | None
    # Richieste Control API servite (o rifiutate) senza un record nella scatola nera: contate in
    # memoria.
    requests_unrecorded: Count
    # Dati che il motore non ha riportato (distinti dai null legittimi: nessun errore, registro
    # vuoto).
    not_reported: Annotated[
        tuple[
            Literal[
                "seq_range", "corrupt_records", "sessions", "last_durable_write_at",
                "retention_days", "gaps", "degraded", "dropped_non_critical",
                "last_write_error_code",
            ],
            ...,
        ],
        Field(max_length=9, json_schema_extra={"uniqueItems": True}),
    ]

    @model_validator(mode="after")
    def _coherent(self) -> BlackboxStatusResponse:
        if len(set(self.not_reported)) != len(self.not_reported):
            raise ValueError("not_reported repeated")
        reported = {
            "corrupt_records": self.corrupt_records, "sessions": self.sessions,
            "last_durable_write_at": self.last_durable_write_at,
            "retention_days": self.retention_days, "degraded": self.degraded,
            "dropped_non_critical": self.dropped_non_critical,
            "last_write_error_code": self.last_write_error_code,
        }
        for name, value in reported.items():
            if name in self.not_reported and value is not None:
                raise ValueError("a field declared not reported carries a value")
        if "seq_range" in self.not_reported and self.first_seq is not None:
            raise ValueError("seq range declared not reported carries a value")
        if (self.first_seq is None) != (self.last_seq is None):
            raise ValueError("seq range incomplete")
        if (self.first_seq is not None and self.last_seq is not None
                and self.first_seq > self.last_seq):
            raise ValueError("seq range inverted")
        if self.gaps_truncated and not self.gaps:
            raise ValueError("gaps truncated without gaps")
        if "gaps" in self.not_reported and self.gaps:
            raise ValueError("gaps declared not reported carry a value")
        if self.available and self.degraded:
            raise ValueError("a degraded register is not available")
        said_why = (
            self.last_write_error_code is not None
            or self.degraded is True
            or "seq_range" in self.not_reported
            or "last_write_error_code" in self.not_reported
        )
        if not self.available and not said_why:
            raise ValueError("an unavailable register must say why")
        return self
