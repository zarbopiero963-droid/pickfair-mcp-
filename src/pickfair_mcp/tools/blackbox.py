"""MCP-01o: lettura della scatola nera di Pickfair (PF-BLACKBOX-01), solo lettura.

Quattro strumenti, una route ciascuno: stato del registro, sessioni, eventi filtrati, un evento con
la sua
catena causale. Le «cronologie» di sessione, tavolo e ordine e la ricerca per intervallo di tempo
sono
filtri di `list_blackbox_events`. Il registro è scritto dal motore (Claude B); l'MCP non può
modificarlo,
cancellarlo o falsificarlo: non esiste alcuna route di scrittura. Ogni chiamata è registrata a sua
volta
nella scatola nera dal core (una volta per richiesta, con l'`X-Request-Id` dell'MCP).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints, model_validator

from pickfair_mcp.adapters.base import ControlApiAdapter
from pickfair_mcp.auth import Scope
from pickfair_mcp.contract.models import (
    BetIdText,
    BlackboxCategory,
    BlackboxEventId,
    BlackboxEventResponse,
    BlackboxEventsResponse,
    BlackboxOrigin,
    BlackboxOutcome,
    BlackboxSessionsResponse,
    BlackboxStatusResponse,
    MarketId,
    OrderUuid,
    SessionKey,
    StrategyName,
    StrictModel,
    UpperCode,
)
from pickfair_mcp.contract.parsing import (
    parse_blackbox_event,
    parse_blackbox_events,
    parse_blackbox_sessions,
    parse_blackbox_status,
)
from pickfair_mcp.policy.handshake import HandshakeGuard
from pickfair_mcp.tools.meta import UpstreamInfo
from pickfair_mcp.tools.registry import ToolContext, ToolSpec
from pickfair_mcp.tools.status import (
    MAX_SNAPSHOT_AGE_S,
    SUFFIX,
    NoInput,
    _invalid,
    read_snapshot,
    upstream_info,
)

STATUS_ROUTE: Final = "GET /v1/blackbox/status"
SESSIONS_ROUTE: Final = "GET /v1/blackbox/sessions"
EVENTS_ROUTE: Final = "GET /v1/blackbox/events"
EVENT_ROUTE: Final = "GET /v1/blackbox/events/{event_id}"

_NOTE = (
    " The black box is Pickfair's permanent chronological register, written by the engine; this "
    "tool "
    "only reads it and cannot change it. Never invent missing information: a field the engine did "
    "not "
    "record is null and listed in not_recorded; missing seq numbers are reported as gaps. phase "
    "ATTEMPT "
    "is what Pickfair tried (outcome PENDING), RESULT what actually happened: a request sent is "
    "never a "
    "confirmed operation. outcome UNKNOWN means the exchange outcome is not known (never a "
    "failure). "
    "Times are UTC with milliseconds; convert them to the user's local time when presenting."
)
STATUS_DESCRIPTION = (
    "Read-only. State of Pickfair's black box (GET /v1/blackbox/status): whether it is available, "
    "the "
    "seq range, gaps (lost, corrupt or removed by retention), corrupt records, sessions, last "
    "write "
    "error and last durable write, and how many Control API requests could not be recorded."
    + _NOTE
    + SUFFIX
)
SESSIONS_DESCRIPTION = (
    "Read-only. Start-to-stop sessions recorded in Pickfair's black box (GET "
    "/v1/blackbox/sessions): "
    "session id, process id, start and end time, how it ended (RUNNING, CLEAN_STOP, "
    "CRASH_DETECTED, or "
    "UNRECORDED when no stop was recorded) and its seq range." + _NOTE + SUFFIX
)
EVENTS_DESCRIPTION = (
    "Read-only. Events from Pickfair's black box in seq order (GET /v1/blackbox/events). Filters: "
    "since/until (UTC, YYYY-MM-DDTHH:MM:SS[.mmm]Z, at most 31 days), session_id (a session's "
    "history), "
    "table_id (a table's history), order_id (ledger integer or uuid) or bet_id (an order's "
    "lifecycle), market_id, selection_id, strategy, correlation_id, causation_id, category, "
    "origin (USER, SYSTEM, MCP, CONTROL_API, STRATEGY, EXCHANGE, TELEGRAM, CLI), severity "
    "(exact), phase, event_type, outcome. No free-text search: filter by type, category or "
    "reason_code instead. Pages of up to 500 events: if truncated, "
    "call "
    "again with after_seq = next_after_seq. To answer 'what happened between 15:00 and 17:00', "
    "convert "
    "the local times to UTC and page through the whole range." + _NOTE + SUFFIX
)
EVENT_DESCRIPTION = (
    "Read-only. One event of Pickfair's black box with its causal chain (GET "
    "/v1/blackbox/events/{event_id}): the events that caused it, nearest first, following "
    "causation_id. "
    "Use it to explain why a decision or a rejection happened; chain_broken_at names a cause that "
    "is not "
    "in the register." + _NOTE + SUFFIX
)

Age = Annotated[float, Field(ge=0, le=MAX_SNAPSHOT_AGE_S)]
UtcInput = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{3})?Z$"
    ),
]


def _instant(value: str) -> datetime:
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ"
    return datetime.strptime(value, fmt).replace(tzinfo=UTC)


class ListBlackboxEventsInput(StrictModel):
    since: UtcInput | None = None
    until: UtcInput | None = None
    after_seq: Annotated[int, Field(ge=0, le=10**15)] | None = None
    limit: Annotated[int, Field(ge=1, le=500)] | None = None
    session_id: SessionKey | None = None
    table_id: Annotated[int, Field(ge=1, le=9999)] | None = None
    market_id: MarketId | None = None
    order_id: Annotated[int, Field(ge=1, le=10**15)] | OrderUuid | None = None
    bet_id: BetIdText | None = None
    strategy: StrategyName | None = None
    correlation_id: SessionKey | None = None
    category: BlackboxCategory | None = None
    origin: BlackboxOrigin | None = None
    severity: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
    event_type: UpperCode | None = None
    outcome: BlackboxOutcome | None = None
    selection_id: Annotated[int, Field(ge=1, le=10**12)] | None = None
    phase: Literal["ATTEMPT", "RESULT", "OBSERVATION"] | None = None
    causation_id: BlackboxEventId | None = None

    @model_validator(mode="after")
    def _range(self) -> ListBlackboxEventsInput:
        # Confronto fra istanti, mai fra stringhe: «...00Z» e «...00.500Z» non si ordinano
        # lessicalmente.
        if (
            self.since is not None
            and self.until is not None
            and _instant(self.since) > _instant(self.until)
        ):
            raise ValueError("since after until")
        return self

    def query(self) -> tuple[tuple[str, str], ...]:
        """Coppie nome/valore nell'ordine dei campi; solo i filtri impostati."""
        return tuple(
            (name, str(value)) for name, value in self.model_dump(exclude_none=True).items()
        )


class GetBlackboxEventInput(StrictModel):
    event_id: BlackboxEventId


class BlackboxStatusData(StrictModel):
    blackbox: BlackboxStatusResponse
    age_s: Age
    upstream: UpstreamInfo


class BlackboxSessionsData(StrictModel):
    sessions: BlackboxSessionsResponse
    age_s: Age
    upstream: UpstreamInfo


class BlackboxEventsData(StrictModel):
    events: BlackboxEventsResponse
    age_s: Age
    upstream: UpstreamInfo


class BlackboxEventData(StrictModel):
    event: BlackboxEventResponse
    age_s: Age
    upstream: UpstreamInfo


def make_get_blackbox_status(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(_: ToolContext) -> BlackboxStatusData:
        snapshot, age = await read_snapshot(
            adapter,
            guard,
            route=STATUS_ROUTE,
            read=adapter.get_blackbox_status_raw,
            parse=parse_blackbox_status,
            timeout_s=timeout_s,
            clock=clock,
        )
        return BlackboxStatusData(blackbox=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="get_blackbox_status",
        route=STATUS_ROUTE,
        scope=Scope.READ,
        description=STATUS_DESCRIPTION,
        input_model=NoInput,
        data_model=BlackboxStatusData,
        handler=handler,
    )


def make_list_blackbox_sessions(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(_: ToolContext) -> BlackboxSessionsData:
        snapshot, age = await read_snapshot(
            adapter,
            guard,
            route=SESSIONS_ROUTE,
            read=adapter.get_blackbox_sessions_raw,
            parse=parse_blackbox_sessions,
            timeout_s=timeout_s,
            clock=clock,
        )
        return BlackboxSessionsData(sessions=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="list_blackbox_sessions",
        route=SESSIONS_ROUTE,
        scope=Scope.READ,
        description=SESSIONS_DESCRIPTION,
        input_model=NoInput,
        data_model=BlackboxSessionsData,
        handler=handler,
    )


def make_list_blackbox_events(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(ctx: ToolContext) -> BlackboxEventsData:
        args = ctx.arguments
        if not isinstance(args, ListBlackboxEventsInput):  # il server passa sempre l'input validato
            raise _invalid("INPUT_MISSING")
        query = args.query()
        snapshot, age = await read_snapshot(
            adapter,
            guard,
            route=EVENTS_ROUTE,
            read=lambda: adapter.get_blackbox_events_raw(query),
            parse=parse_blackbox_events,
            timeout_s=timeout_s,
            clock=clock,
        )
        if args.after_seq is not None and any(
            e.seq <= args.after_seq for e in snapshot.events or ()
        ):
            raise _invalid(
                "CURSOR_NOT_RESPECTED"
            )  # il core ha ignorato il cursore: pagina non affidabile
        return BlackboxEventsData(events=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="list_blackbox_events",
        route=EVENTS_ROUTE,
        scope=Scope.READ,
        description=EVENTS_DESCRIPTION,
        input_model=ListBlackboxEventsInput,
        data_model=BlackboxEventsData,
        handler=handler,
    )


def make_get_blackbox_event(
    adapter: ControlApiAdapter,
    guard: HandshakeGuard,
    *,
    timeout_s: float,
    clock: Callable[[], float] = time.time,
) -> ToolSpec:
    async def handler(ctx: ToolContext) -> BlackboxEventData:
        args = ctx.arguments
        if not isinstance(args, GetBlackboxEventInput):
            raise _invalid("INPUT_MISSING")
        event_id = args.event_id
        snapshot, age = await read_snapshot(
            adapter,
            guard,
            route=EVENT_ROUTE,
            read=lambda: adapter.get_blackbox_event_raw(event_id),
            parse=parse_blackbox_event,
            timeout_s=timeout_s,
            clock=clock,
        )
        if snapshot.event_id != event_id:
            raise _invalid("EVENT_ID_MISMATCH")
        return BlackboxEventData(event=snapshot, age_s=age, upstream=upstream_info(adapter))

    return ToolSpec(
        name="get_blackbox_event",
        route=EVENT_ROUTE,
        scope=Scope.READ,
        description=EVENT_DESCRIPTION,
        input_model=GetBlackboxEventInput,
        data_model=BlackboxEventData,
        handler=handler,
    )
