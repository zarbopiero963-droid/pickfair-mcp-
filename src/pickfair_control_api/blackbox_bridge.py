"""MCP-01p/01q: dalla scatola nera del motore (Claude B, `core/blackbox_query`) alla vista del
contratto. Forme del lettore: quelle REALI di BB-1 (fixture di B, sha256 74be0f92…36f6df).

Funzioni pure, solo stdlib. Il ponte del core collega l'interfaccia di lettura di B (pf_blackbox_01
§4-bis):

    status() -> dict
    sessions() -> list[dict]
    query(filters, after_seq, limit, *, external)
        -> {records, next_after_seq, gaps_in_range, as_of_seq}
    get(event_id, chain_depth, *, external)
        -> record | None, con la catena in `causation_chain` (anello mancante: {event_id, missing})
    request_hook(record) -> bool

e ottiene i quattro provider e il `request_hook` del server. Regole (mai inventare):
- record del motore con i nomi di pf_blackbox_01 §3 (`source`, `type`, `pid`, `ts_utc` al µs,
`event_id`
  uuid, `order_ref`, `data`): rinominati, tempo troncato al millisecondo, uuid in 32 hex;
- `order_ref` / `customer_ref` non escono mai; `not_recorded` è quello del motore (BB-1 elenca i
  campi a null) più i campi assenti dal record; un nome sconosciuto o con valore = record non
  mappabile;
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
# Profondità della catena chiesta al motore: il limite di BB-1 (`MAX_CHAIN_DEPTH = 20`,
# confermato da B). Oltre, il lettore risponde con un errore e ogni lettura di un evento
# fallirebbe. La vista ne ammette fino a 32.
MAX_CHAIN: Final = 20
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
    "exchange_ts",
)
# Nomi dei filtri della vista => nomi del motore (pf_blackbox_01 §3).
# BB-1: il tempo si filtra con from_ts/to_ts e un filtro sconosciuto è un errore del lettore.
FILTER_NAMES: Final = {
    "origin": "source", "event_type": "type", "since": "from_ts", "until": "to_ts",
}
# Forma del lettore = BB-1 (core.blackbox_query.BlackBoxReader), normativa per decisione C/B
# del 09/11/2026.
READER_SIGNATURES: Final = {
    "status": (),
    "sessions": (),
    "query": ("filters", "after_seq", "limit"),
    "get": ("event_id", "chain_depth"),
    "request_hook": ("record",),
}

_TS = re.compile(r"\A(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)\Z")
_HEX32 = re.compile(r"\A[0-9a-f]{32}\Z")
_NAME = re.compile(r"\A[a-z][a-z0-9_.]{0,63}\Z")
_UPPER = re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z")
# reason_code: anche il nome di un'eccezione (BB-1: `KeyError` per TASK_EXCEPTION).
_REASON = re.compile(r"\A[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_CATEGORY = re.compile(r"\A[A-Z][A-Z0-9_]{0,31}\Z")
_COMPONENT = re.compile(r"\A[ -~]{1,64}\Z")  # BB-1: anche `thread:<nome del thread>`
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
    """32 hex della vista -> id del motore (in BB-1: 32 hex minuscoli, senza trattini)."""
    return uuid.UUID(hex=hex32).hex


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
    """Intero, o stringa di sole cifre (BB-1 registra table_id e selection_id come stringhe)."""
    value = record.get(name)
    if value is None:
        return None
    if isinstance(value, str) and value.isdigit() and value.isascii():
        value = int(value)
    if type(value) is not int or not low <= value <= high:
        raise Unmappable(name)
    return value


# BB-1 (D1): alias opaco dell'ordine, mai l'id interno (né intero né uuid del DB degradato).
_ORDER_ALIAS = re.compile(r"\Aord_[0-9a-f]{32}\Z")


def _order_id(record: Mapping[str, Any]) -> object:
    return _opt(record, "order_id", _ORDER_ALIAS)


_REF_COLUMNS: Final = frozenset(
    {"table_id", "market_id", "selection_id", "order_id", "bet_id", "strategy"}
)
_NULLABLE_COLUMNS: Final = frozenset(
    {"pid" if n == "process_id" else n for n in RECORDABLE} | _REF_COLUMNS
)


def _engine_not_recorded(record: Mapping[str, Any]) -> frozenset[str]:
    """`not_recorded` di BB-1: campi a null non registrati. Mai un valore dichiarato assente."""
    names = record.get("not_recorded", [])
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise Unmappable("not_recorded")
    for name in names:
        if name not in _NULLABLE_COLUMNS or record.get(name) is not None:
            raise Unmappable("not_recorded")
    return frozenset(names)


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
    engine_not_recorded = _engine_not_recorded(record)
    not_recorded = []
    for name in RECORDABLE:
        source_name = "pid" if name == "process_id" else name
        if source_name not in record or source_name in engine_not_recorded:
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
        elif name == "exchange_ts":  # ora dichiarata dall'exchange (D2), distinta da ts_utc
            view[name] = None if value is None else ts_ms(value)
        elif name == "reason_code":
            view[name] = _opt(record, "reason_code", _REASON)
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
        "order_id": _order_id(record),
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


MAX_WINDOWS: Final = 64


def unrecorded_window(item: object) -> dict[str, Any]:
    """Lacuna per tempo di BB-1 {seq, from_ts, to_ts, outcome, reason_code} -> finestra della vista.

    Il motore non sa cosa sia successo nella finestra: l'esito è UNKNOWN, mai altro."""
    if not isinstance(item, Mapping):
        raise ValueError("window")
    seq, outcome, code = item.get("seq"), item.get("outcome"), item.get("reason_code")
    if type(seq) is not int or seq < 1 or outcome != "UNKNOWN":
        raise ValueError("window")
    if not isinstance(code, str) or not _REASON.fullmatch(code):
        raise ValueError("window")
    lo, hi = ts_ms(item.get("from_ts")), ts_ms(item.get("to_ts"))
    if lo > hi:
        raise ValueError("window")
    return {"seq": seq, "from_ts": lo, "to_ts": hi, "reason_code": code}


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


_TEXT_IDS: Final = frozenset({"table_id", "selection_id", "order_id"})


def engine_filters(filters: Mapping[str, object]) -> tuple[dict[str, object], int, int]:
    """Filtri validati della vista -> (filtri del motore, after_seq, limit)."""
    out: dict[str, object] = {}
    for name, value in filters.items():
        if name in ("after_seq", "limit"):
            continue
        if isinstance(value, datetime):  # già validato dalla whitelist
            value = value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"
        elif name in _TEXT_IDS:
            # BB-1 registra questi id come testo (cifre; per order_id l'alias) e confronta per
            # uguale: un intero non troverebbe nulla, senza errore. Si passa la forma del motore.
            value = str(value)
        out[FILTER_NAMES.get(name, name)] = value
    after_seq, limit = filters.get("after_seq", 0), filters.get("limit", 200)
    after = after_seq if isinstance(after_seq, int) else 0
    return out, after, limit if isinstance(limit, int) else 200


def session_view(raw: Mapping[str, Any], current: object) -> dict[str, Any]:
    """Sessione di BB-1 {session_id, pid, started, last_ts, first_seq, last_seq, clean_shutdown}.

    `clean_shutdown` falso vale sia per la sessione corrente sia per un crash rilevato al riavvio:
    si distinguono solo con `status().session_id`. Senza di esso, nessuna fine «inventata».
    """
    session = raw.get("session_id")
    if not isinstance(session, str) or not _SESSION.fullmatch(session):
        raise ValueError("session_id")
    clean = raw.get("clean_shutdown")
    if clean is True:
        end_reason = "CLEAN_STOP"
    elif clean is False and isinstance(current, str):
        end_reason = "RUNNING" if session == current else "CRASH_DETECTED"
    else:
        raise ValueError("clean_shutdown")
    last_ts = raw.get("last_ts")
    last_event_at = None if last_ts is None else ts_ms(last_ts)
    return {
        "session_id": session,
        "process_id": _opt_int(raw, "pid", 1, 2**31),
        "started_at": ts_ms(raw.get("started")),
        # Fine registrata solo per l'arresto pulito; per un crash l'ora vera non è nota.
        "ended_at": last_event_at if end_reason == "CLEAN_STOP" else None,
        "last_event_at": last_event_at,
        "end_reason": end_reason,
        "first_seq": raw.get("first_seq"),
        "last_seq": raw.get("last_seq"),
    }


# Chiavi di BB-1 che il contratto riporta; una chiave assente diventa `not_reported`.
_STATUS_OPTIONAL: Final = (
    "corrupt_records", "last_durable_write_at", "retention_days", "gaps", "degraded",
    "dropped_non_critical", "last_write_error_code",
)


def status_view(raw: Mapping[str, Any], sessions_raw: object) -> dict[str, Any]:
    """status() di BB-1 {ok, degraded, dropped_non_critical, as_of_seq, session_id, not_reported,
    …} -> stato della vista. Disponibile solo se `ok` è letteralmente True e non degradato."""
    if not isinstance(sessions_raw, list):
        raise ValueError("sessions")
    not_reported = [name for name in _STATUS_OPTIONAL if name not in raw]
    engine_nr = raw.get("not_reported", [])
    if not isinstance(engine_nr, list):
        raise ValueError("not_reported")
    if "last_error_detail" in engine_nr and "last_write_error_code" not in not_reported:
        not_reported.append("last_write_error_code")
    as_of = raw.get("as_of_seq")
    firsts = [s.get("first_seq") for s in sessions_raw if isinstance(s, Mapping)]
    first = min((f for f in firsts if type(f) is int), default=None)
    if type(as_of) is not int or as_of < 0:
        raise ValueError("as_of_seq")
    if as_of == 0:
        first = last = None  # registro vuoto: nessun intervallo, non «non riportato»
    elif type(first) is int:
        last = as_of
    else:
        first = last = None
        not_reported.insert(0, "seq_range")
    gaps = merge_gaps([_gap(g) for g in raw.get("gaps", [])])
    durable = raw.get("last_durable_write_at")
    degraded = raw.get("degraded")
    if degraded is not None and not isinstance(degraded, bool):
        raise ValueError("degraded")
    available = raw.get("ok") is True and degraded is not True
    return {
        "available": available,
        "degraded": degraded,
        "dropped_non_critical": raw.get("dropped_non_critical"),
        "first_seq": first,
        "last_seq": last,
        "retained_from_seq": raw.get("retained_from_seq"),
        "gaps": gaps[:64],
        "gaps_truncated": len(gaps) > 64,
        "corrupt_records": raw.get("corrupt_records"),
        "sessions": len(sessions_raw),
        "current_session_id": raw.get("session_id"),
        "last_write_error_code": raw.get("last_write_error_code"),
        "last_durable_write_at": None if durable is None else ts_ms(durable),
        "retention_days": raw.get("retention_days"),
        "requests_unrecorded": 0,
        "not_reported": not_reported,
    }


def make_providers(
    reader: Any, *, clock: Callable[[], float] = time.time
) -> dict[str, Callable[..., Any]]:
    """I quattro provider della scatola nera sopra l'interfaccia di lettura di B."""

    def envelope(consistency: str) -> dict[str, Any]:
        return {"source": "core", "observed_at": float(clock()), "consistency": consistency}

    def events(filters: Mapping[str, object]) -> dict[str, Any]:
        engine, after_seq, limit = engine_filters(filters)
        page = reader.query(engine, after_seq, limit, external=True)
        records, as_of_seq = page["records"], page["as_of_seq"]
        next_after_seq = page["next_after_seq"]
        raw_windows = page["gaps_in_range"]  # chiave obbligatoria: assente = risposta non valida
        if not isinstance(raw_windows, list) or len(raw_windows) > MAX_WINDOWS:
            raise ValueError("gaps_in_range")  # mai una lacuna nascosta o tagliata
        windows = sorted((unrecorded_window(w) for w in raw_windows), key=lambda w: w["seq"])
        gaps: list[Any] = []
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
            "unrecorded_windows": windows,
            "unavailable": [],
        }

    def event(event_id: str) -> dict[str, Any]:
        got = reader.get(engine_id(event_id), MAX_CHAIN, external=True)
        if got is not None and not isinstance(got, Mapping):
            raise ValueError("get shape")  # BB-1: il record con la catena dentro, oppure None
        record: dict[str, Any] | None = None
        chain: list[Any] = []
        if got is not None:
            raw_chain = got.get("causation_chain")
            if not isinstance(raw_chain, list):
                raise ValueError("get shape")  # mai una catena «vuota» perché non riportata
            chain = raw_chain
            record = {k: v for k, v in got.items() if k != "causation_chain"}
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
        for link in chain:  # un anello {event_id, missing: true} non si mappa: catena interrotta
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
        raw_sessions = reader.sessions()
        current = reader.status().get("session_id")  # BB-1: unico modo di riconoscere la corrente
        items = [session_view(raw, current) for raw in raw_sessions]
        return {
            **envelope("SINGLE_READ_SNAPSHOT"),
            "sessions": items,
            "truncated": False,
            "unavailable": [],
        }

    def status() -> dict[str, Any]:
        raw = reader.status()
        if not isinstance(raw, Mapping):
            raise ValueError("status")
        sessions_raw = reader.sessions()  # BB-1: primo seq e numero di sessioni stanno qui
        return {**envelope("PER_FIELD_NON_ATOMIC"), **status_view(raw, sessions_raw)}

    return {
        "blackbox_status": status,
        "blackbox_sessions": sessions,
        "blackbox_events": events,
        "blackbox_event": event,
    }


def make_request_hook(reader: Any) -> Callable[[dict[str, Any]], bool]:
    """Hook del server: accettato solo se il motore conferma la scrittura con True."""

    def hook(record: dict[str, Any]) -> bool:
        return reader.request_hook(dict(record)) is True

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
