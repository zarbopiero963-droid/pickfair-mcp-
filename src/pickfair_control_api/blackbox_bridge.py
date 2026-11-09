"""MCP-01p: dalla scatola nera del motore (Claude B, `core/blackbox_query`) alla vista del
contratto.

Funzioni pure, solo stdlib. Il ponte del core collega l'interfaccia di lettura di B (pf_blackbox_01
§4-bis):

    status() -> dict
    sessions() -> list[dict]
    query(filters, after_seq, limit) -> (records, next_after_seq, gaps_in_range, as_of_seq)
    get(event_id, chain_depth) -> (record | None, chain)
    record_control_api_request(fields) -> bool

e ottiene i quattro provider e il `request_hook` del server. Regole (mai inventare):
- record del motore con i nomi di pf_blackbox_01 §3 (`source`, `type`, `pid`, `ts_utc` al µs,
`event_id`
  uuid, `order_ref`, `data`): rinominati, tempo troncato al millisecondo, uuid in 32 hex;
- `order_ref` / `customer_ref` non escono mai; un campo assente dal record è `null` ed elencato in
  `not_recorded`, un campo presente e nullo è «non applicabile»;
- valori: mappe piatte di scalari; un float finito diventa la sua stringa decimale esatta; liste,
valori
  oltre 256 caratteri, nomi fuori pattern o oltre 32 voci non si mostrano e si contano in
  `omitted_values`;
- un record non mappabile (origine, livello, fase o esito fuori vocabolario, ora non UTC, id non
valido)
  diventa una lacuna CORRUPT per il suo seq: mai un evento «aggiustato», mai un salto silenzioso.
"""

from __future__ import annotations

import inspect
import json
import math
import re
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Final

from pickfair_control_api.blackbox_query import ORIGINS, OUTCOMES, SEVERITIES

PHASES: Final = frozenset({"ATTEMPT", "RESULT", "OBSERVATION"})
GAP_KINDS: Final = frozenset({"LOST", "CORRUPT", "RETENTION"})
END_REASONS: Final = frozenset({"RUNNING", "CLEAN_STOP", "CRASH_DETECTED", "UNRECORDED"})
MAX_CHAIN: Final = 32
MAX_VALUES: Final = 32
MAX_TEXT: Final = 256
# Campi del record che il motore può non aver registrato (assenti => not_recorded).
RECORDABLE: Final = (
    "state_before",
    "state_after",
    "values_before",
    "values_after",
    "reason",
    "reason_code",
    "correlation_id",
    "causation_id",
    "process_id",
    "component",
    "data",
)
# Nomi dei filtri della vista => nomi del motore (pf_blackbox_01 §3).
FILTER_NAMES: Final = {"origin": "source", "event_type": "type"}
READER_SIGNATURES: Final = {
    "status": (),
    "sessions": (),
    "query": ("filters", "after_seq", "limit"),
    "get": ("event_id", "chain_depth"),
    "record_control_api_request": ("fields",),
}

_TS = re.compile(r"\A(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)\Z")
_HEX32 = re.compile(r"\A[0-9a-f]{32}\Z")
_NAME = re.compile(r"\A[a-z][a-z0-9_.]{0,63}\Z")
_UPPER = re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z")
_CATEGORY = re.compile(r"\A[A-Z][A-Z0-9_]{0,31}\Z")
_COMPONENT = re.compile(r"\A[a-z][a-z0-9_.]{0,63}\Z")
_SESSION = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")
_MARKET = re.compile(r"\A[0-9]{1,4}\.[0-9]{1,15}\Z")
_BET = re.compile(r"\A[0-9]{1,20}\Z")
_STRATEGY = re.compile(r"\A[a-z][a-z0-9_]{0,31}\Z")


class Unmappable(ValueError):
    """Record del motore non rappresentabile nel contratto: diventa una lacuna CORRUPT."""


def ts_ms(value: object) -> str:
    """ISO-8601 UTC del motore (fino al ns) -> 'YYYY-MM-DDTHH:MM:SS.mmmZ', troncato."""
    m = _TS.fullmatch(value) if isinstance(value, str) else None
    if not m:
        raise Unmappable("ts")
    return f"{m.group(1)}.{(m.group(2) or '').ljust(3, '0')[:3]}Z"


def hex_id(value: object) -> str:
    """uuid (con o senza trattini) -> 32 hex minuscoli."""
    if isinstance(value, str) and _HEX32.fullmatch(value):
        return value
    try:
        return uuid.UUID(str(value)).hex
    except (ValueError, TypeError, AttributeError):
        raise Unmappable("event_id") from None


def engine_id(hex32: str) -> str:
    """32 hex della vista -> forma uuid con trattini, quella del motore."""
    return str(uuid.UUID(hex=hex32))


def _scalar(value: object) -> tuple[bool, object]:
    if value is None or isinstance(value, bool):
        return True, value
    if isinstance(value, int):
        return (abs(value) <= 10**15, value)
    if isinstance(value, float):
        return (math.isfinite(value), repr(value) if math.isfinite(value) else None)
    if isinstance(value, str):
        return (len(value) <= MAX_TEXT, value)
    return False, None


def flatten(values: object) -> tuple[dict[str, object] | None, int]:
    """Mappa del motore (dict o JSON) -> (mappa piatta con nomi puntati, voci omesse)."""
    if values is None:
        return None, 0
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except ValueError:
            return None, 1
    if not isinstance(values, dict):
        return None, 1
    out: dict[str, object] = {}
    omitted = 0

    def walk(prefix: str, node: Mapping[str, Any]) -> None:
        nonlocal omitted
        for key, value in node.items():
            name = f"{prefix}{key}" if isinstance(key, str) else ""
            if isinstance(value, dict):
                walk(name + ".", value)
                continue
            ok, scalar = _scalar(value)
            if not ok or not _NAME.fullmatch(name) or len(out) >= MAX_VALUES:
                omitted += 1
                continue
            out[name] = scalar

    walk("", values)
    return out, omitted


def _opt(record: Mapping[str, Any], name: str, pattern: re.Pattern[str]) -> object:
    value = record.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise Unmappable(name)
    return value


def _opt_int(record: Mapping[str, Any], name: str, low: int, high: int) -> int | None:
    value = record.get(name)
    if value is None:
        return None
    if type(value) is not int or not low <= value <= high:
        raise Unmappable(name)
    return value


def event_view(record: Mapping[str, Any]) -> dict[str, Any]:
    """Un record del motore -> evento del contratto. Solleva Unmappable se non rappresentabile."""
    if not isinstance(record, Mapping):
        raise Unmappable("record")
    seq = record.get("seq")
    if type(seq) is not int or seq < 1:
        raise Unmappable("seq")
    origin, severity = record.get("source"), record.get("severity")
    phase, outcome = record.get("phase"), record.get("outcome")
    if (
        origin not in ORIGINS
        or severity not in SEVERITIES
        or phase not in PHASES
        or outcome not in OUTCOMES
    ):
        raise Unmappable("vocabulary")
    if phase == "ATTEMPT" and outcome != "PENDING":
        raise Unmappable("attempt_outcome")  # mai un tentativo mostrato come confermato
    category, event_type = record.get("category"), record.get("type")
    if not isinstance(category, str) or not _CATEGORY.fullmatch(category):
        raise Unmappable("category")
    if not isinstance(event_type, str) or not _UPPER.fullmatch(event_type):
        raise Unmappable("type")
    session = record.get("session_id")
    if not isinstance(session, str) or not _SESSION.fullmatch(session):
        raise Unmappable("session_id")
    event_id = hex_id(record.get("event_id"))
    omitted = 0
    view: dict[str, Any] = {
        "seq": seq,
        "event_id": event_id,
        "ts_utc": ts_ms(record.get("ts_utc")),
        "session_id": session,
        "origin": origin,
        "category": category,
        "event_type": event_type,
        "severity": severity,
        "phase": phase,
        "outcome": outcome,
    }
    not_recorded = []
    for name in RECORDABLE:
        source_name = "pid" if name == "process_id" else name
        if source_name not in record:
            view[name] = None
            not_recorded.append(name)
            continue
        value = record[source_name]
        if name in ("values_before", "values_after", "data"):
            view[name], n = flatten(value)
            omitted += n
        elif name == "causation_id":
            view[name] = None if value is None else hex_id(value)
        elif name == "process_id":
            view[name] = _opt_int(record, "pid", 1, 2**31)
        elif name == "component":
            view[name] = _opt(record, "component", _COMPONENT)
        elif name == "reason_code":
            view[name] = _opt(record, "reason_code", _UPPER)
        elif name == "correlation_id":
            view[name] = _opt(record, "correlation_id", _SESSION)
        elif name in ("state_before", "state_after"):
            if value is not None and (not isinstance(value, str) or len(value) > 64):
                raise Unmappable(name)
            view[name] = value
        else:  # reason: oltre MAX_TEXT non si mostra né si tronca, si conta fra le voci omesse
            if value is not None and not isinstance(value, str):
                raise Unmappable(name)
            too_long = value is not None and len(value) > MAX_TEXT
            view[name] = None if too_long else value
            omitted += int(too_long)
    if view["causation_id"] == event_id:
        raise Unmappable("causation_id")
    view["refs"] = {
        "table_id": _opt_int(record, "table_id", 1, 9999),
        "market_id": _opt(record, "market_id", _MARKET),
        "selection_id": _opt_int(record, "selection_id", 1, 10**12),
        "order_id": _opt_int(record, "order_id", 1, 10**15),
        "bet_id": _opt(record, "bet_id", _BET),
        "strategy": _opt(record, "strategy", _STRATEGY),
    }
    view["omitted_values"] = omitted
    view["not_recorded"] = not_recorded
    return view


def _gap(item: object) -> dict[str, Any]:
    if isinstance(item, Mapping):
        lo, hi, kind = item.get("from_seq"), item.get("to_seq"), item.get("kind")
    elif isinstance(item, (tuple, list)) and len(item) == 3:
        lo, hi, kind = item
    else:
        raise ValueError("gap")
    if type(lo) is not int or type(hi) is not int or not 1 <= lo <= hi or kind not in GAP_KINDS:
        raise ValueError("gap")
    return {"from_seq": lo, "to_seq": hi, "kind": kind}


def merge_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordina e unisce lacune contigue dello stesso tipo; una sovrapposizione è un errore."""
    out: list[dict[str, Any]] = []
    for gap in sorted(gaps, key=lambda g: g["from_seq"]):
        if out and gap["from_seq"] <= out[-1]["to_seq"]:
            raise ValueError("overlapping gaps")
        if out and gap["kind"] == out[-1]["kind"] and gap["from_seq"] == out[-1]["to_seq"] + 1:
            out[-1] = {**out[-1], "to_seq": gap["to_seq"]}
        else:
            out.append(gap)
    return out


def engine_filters(filters: Mapping[str, object]) -> tuple[dict[str, object], int, int]:
    """Filtri validati della vista -> (filtri del motore, after_seq, limit)."""
    out: dict[str, object] = {}
    for name, value in filters.items():
        if name in ("after_seq", "limit"):
            continue
        if isinstance(value, datetime):  # già validato dalla whitelist
            value = value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"
        out[FILTER_NAMES.get(name, name)] = value
    after_seq, limit = filters.get("after_seq", 0), filters.get("limit", 200)
    after = after_seq if isinstance(after_seq, int) else 0
    return out, after, limit if isinstance(limit, int) else 200


def make_providers(
    reader: Any, *, clock: Callable[[], float] = time.time
) -> dict[str, Callable[..., Any]]:
    """I quattro provider della scatola nera sopra l'interfaccia di lettura di B."""

    def envelope(consistency: str) -> dict[str, Any]:
        return {"source": "core", "observed_at": float(clock()), "consistency": consistency}

    def events(filters: Mapping[str, object]) -> dict[str, Any]:
        engine, after_seq, limit = engine_filters(filters)
        records, next_after_seq, gaps, as_of_seq = reader.query(engine, after_seq, limit)
        views, corrupt = [], []
        for record in records:
            try:
                views.append(event_view(record))
            except Unmappable:
                seq = record.get("seq") if isinstance(record, Mapping) else None
                if type(seq) is not int or seq < 1:
                    raise  # nemmeno il seq: risposta del motore non attribuibile, fail-closed
                corrupt.append({"from_seq": seq, "to_seq": seq, "kind": "CORRUPT"})
        nxt = int(next_after_seq or 0)
        return {
            **envelope("SINGLE_READ_SNAPSHOT"),
            "events": views,
            "next_after_seq": nxt,
            "truncated": nxt != 0,
            "as_of_seq": int(as_of_seq),
            "redacted": 0,
            "gaps_in_range": merge_gaps([_gap(g) for g in gaps] + corrupt),
            "unavailable": [],
        }

    def event(event_id: str) -> dict[str, Any]:
        record, chain = reader.get(engine_id(event_id), MAX_CHAIN)
        body = {
            **envelope("SINGLE_READ_SNAPSHOT"),
            "event_id": event_id,
            "redacted": 0,
            "chain": [],
            "chain_truncated": False,
            "chain_broken_at": None,
        }
        if record is None:
            return {**body, "state": "NOT_FOUND", "event": None}
        view = event_view(record)  # l'evento richiesto illeggibile: errore, mai uno «aggiustato»
        links, expected = [], view["causation_id"]
        for link in chain or []:
            if expected is None:
                break
            try:
                link_view = event_view(link)
            except Unmappable:
                break
            if link_view["event_id"] != expected:
                break
            links.append(link_view)
            expected = link_view["causation_id"]
        truncated = expected is not None and len(links) == MAX_CHAIN
        return {
            **body,
            "state": "OK",
            "event": view,
            "chain": links,
            "chain_truncated": truncated,
            "chain_broken_at": None if expected is None or truncated else expected,
        }

    def sessions() -> dict[str, Any]:
        items = []
        for raw in reader.sessions():
            end_reason = raw.get("end_reason")
            if end_reason not in END_REASONS:
                raise ValueError("end_reason")
            items.append(
                {
                    "session_id": raw["session_id"],
                    "process_id": raw.get("pid"),
                    "started_at": ts_ms(raw["started_at"]),
                    "ended_at": None if raw.get("ended_at") is None else ts_ms(raw["ended_at"]),
                    "end_reason": end_reason,
                    "first_seq": raw.get("first_seq"),
                    "last_seq": raw.get("last_seq"),
                }
            )
        return {
            **envelope("SINGLE_READ_SNAPSHOT"),
            "sessions": items,
            "truncated": False,
            "unavailable": [],
        }

    def status() -> dict[str, Any]:
        raw = reader.status()
        reportable = ("corrupt_records", "sessions", "last_durable_write_at", "retention_days")
        not_reported = [name for name in reportable if name not in raw]
        if "last_seq" not in raw:
            not_reported.insert(0, "seq_range")
        gaps = merge_gaps([_gap(g) for g in raw.get("gaps", [])])
        durable = raw.get("last_durable_write_at")
        return {
            **envelope("PER_FIELD_NON_ATOMIC"),
            "available": raw.get("available") is True,
            "first_seq": raw.get("first_seq"),
            "last_seq": raw.get("last_seq"),
            "retained_from_seq": raw.get("retained_from_seq"),
            "gaps": gaps[:64],
            "gaps_truncated": len(gaps) > 64,
            "corrupt_records": raw.get("corrupt_records"),
            "sessions": raw.get("sessions"),
            "current_session_id": raw.get("current_session_id"),
            "last_write_error_code": raw.get("last_write_error_code"),
            "last_durable_write_at": None if durable is None else ts_ms(durable),
            "retention_days": raw.get("retention_days"),
            "requests_unrecorded": 0,
            "not_reported": not_reported,
        }

    return {
        "blackbox_status": status,
        "blackbox_sessions": sessions,
        "blackbox_events": events,
        "blackbox_event": event,
    }


def make_request_hook(reader: Any) -> Callable[[dict[str, Any]], bool]:
    """Hook del server: accettato solo se il motore conferma la scrittura con True."""

    def hook(record: dict[str, Any]) -> bool:
        return reader.record_control_api_request(dict(record)) is True

    return hook


def check_reader(reader: Any) -> list[str]:
    """Compatibilità dell'interfaccia di B (metodi e parametri); lista vuota = compatibile."""
    problems = []
    for name, params in READER_SIGNATURES.items():
        method = getattr(reader, name, None)
        if not callable(method):
            problems.append(f"{name}: assente")
            continue
        try:
            found = tuple(
                p for p in inspect.signature(method).parameters if p not in ("self", "cls")
            )
        except (TypeError, ValueError):
            problems.append(f"{name}: firma non leggibile")
            continue
        if found[: len(params)] != params:
            problems.append(f"{name}: parametri {found} invece di {params}")
    for forbidden in ("record", "delete", "update", "write", "purge", "truncate"):
        if callable(getattr(reader, forbidden, None)):
            problems.append(f"{forbidden}: un lettore non espone scritture")
    return problems
