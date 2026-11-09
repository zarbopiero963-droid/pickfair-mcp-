"""MCP-01o: parametri di GET /v1/blackbox/events (PF-BLACKBOX-01), l'unica route con una query
string.

Whitelist chiusa: ogni parametro ha il suo pattern stretto. Parametro sconosciuto o ripetuto, valore
fuori
pattern, carattere fuori ASCII stampabile, intervallo invertito o più lungo di MAX_RANGE_DAYS:
rifiuto con un
codice fisso, senza che il provider del core venga mai chiamato e senza mai rimandare indietro
l'input.
Il risultato contiene solo valori già validati: il provider non vede mai la stringa grezza.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final

MAX_QUERY_CHARS: Final = 1024
MAX_RANGE_DAYS: Final = 31
DEFAULT_LIMIT: Final = 200
MAX_LIMIT: Final = 500

ORIGINS: Final = frozenset(
    {"USER", "SYSTEM", "MCP", "CONTROL_API", "STRATEGY", "EXCHANGE", "TELEGRAM", "CLI"}
)
SEVERITIES: Final = ("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
OUTCOMES: Final = frozenset(
    {"VERIFIED", "PENDING", "UNKNOWN", "REJECTED", "FAILED", "NOT_APPLICABLE"}
)

_TS = re.compile(r"\A(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?Z\Z")
# uuid canonico, minuscolo e con trattini: la forma di str(uuid4()), confrontata per uguale.
_UUID: Final = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_PATTERNS: Final = {
    "after_seq": re.compile(r"\A(0|[1-9][0-9]{0,15})\Z"),
    "limit": re.compile(r"\A[1-9][0-9]{0,2}\Z"),
    "session_id": re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z"),
    "table_id": re.compile(r"\A[1-9][0-9]{0,3}\Z"),
    "market_id": re.compile(r"\A[0-9]{1,4}\.[0-9]{1,15}\Z"),
    # Id del ledger (intero) oppure uuid (con il DB degradato il motore usa str(uuid4())).
    "order_id": re.compile(r"\A(?:[1-9][0-9]{0,15}|" + _UUID + r")\Z"),
    "selection_id": re.compile(r"\A[1-9][0-9]{0,11}\Z"),
    "causation_id": re.compile(r"\A[0-9a-f]{32}\Z"),
    "bet_id": re.compile(r"\A[0-9]{1,20}\Z"),
    "strategy": re.compile(r"\A[a-z][a-z0-9_]{0,31}\Z"),
    "correlation_id": re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z"),
    "category": re.compile(r"\A[A-Z][A-Z0-9_]{0,31}\Z"),
    "event_type": re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z"),
}
# 1.15.0: filtri di BB-1 (Claude B). severity_min e q non esistono nel lettore del motore: tolti.
PHASES: Final = frozenset({"ATTEMPT", "RESULT", "OBSERVATION"})
_ENUMS: Final = {
    "origin": ORIGINS, "severity": frozenset(SEVERITIES), "outcome": OUTCOMES, "phase": PHASES,
}
ALLOWED: Final = frozenset({"since", "until", *_PATTERNS, *_ENUMS})
_PRINTABLE = re.compile(r"\A[\x21-\x7e]*\Z")
_UNRESERVED = re.compile(r"%(?![0-9A-Fa-f]{2})")


class QueryRejected(ValueError):
    """Query non ammessa: il messaggio è un codice fisso, mai un pezzo dell'input."""


def _unquote(value: str) -> str:
    """Decodifica percent-encoding e '+' come spazio; ogni byte non ASCII stampabile è rifiutato."""
    if _UNRESERVED.search(value):
        raise QueryRejected("QUERY_ENCODING")
    out = bytearray()
    i = 0
    raw = value.replace("+", " ")
    while i < len(raw):
        if raw[i] == "%":
            out.append(int(raw[i + 1 : i + 3], 16))
            i += 3
        else:
            out.append(ord(raw[i]))
            i += 1
    if any(b < 0x20 or b > 0x7E for b in out):
        raise QueryRejected("QUERY_ENCODING")
    return out.decode("ascii")


def _timestamp(value: str) -> datetime:
    m = _TS.fullmatch(value)
    if not m:
        raise QueryRejected("QUERY_VALUE")
    y, mo, d, h, mi, s, ms = m.groups()
    try:
        return datetime(
            int(y),
            int(mo),
            int(d),
            int(h),
            int(mi),
            int(s),
            int(ms or 0) * 1000,
            tzinfo=UTC,
        )
    except ValueError:
        raise QueryRejected("QUERY_VALUE") from None


def parse_events_query(raw: str) -> dict[str, object]:
    """Query grezza (dopo il '?') -> filtri validati. Solleva QueryRejected con un codice fisso."""
    if len(raw) > MAX_QUERY_CHARS or not _PRINTABLE.fullmatch(raw):
        raise QueryRejected("QUERY_TOO_LONG" if len(raw) > MAX_QUERY_CHARS else "QUERY_ENCODING")
    seen: dict[str, str] = {}
    for part in raw.split("&") if raw else []:
        name, sep, value = part.partition("=")
        if not sep or name not in ALLOWED:
            raise QueryRejected("QUERY_PARAM")
        if name in seen:
            raise QueryRejected("QUERY_PARAM_REPEATED")
        seen[name] = _unquote(value)
    filters: dict[str, object] = {}
    for name, value in seen.items():
        if name in ("since", "until"):
            filters[name] = _timestamp(value)
        elif name in _ENUMS:
            if value not in _ENUMS[name]:
                raise QueryRejected("QUERY_VALUE")
            filters[name] = value
        elif not _PATTERNS[name].fullmatch(value):
            raise QueryRejected("QUERY_VALUE")
        elif name in ("after_seq", "limit", "table_id", "selection_id") or (
            name == "order_id" and value.isdigit()
        ):
            filters[name] = int(value)
        else:
            filters[name] = value
    limit = filters.setdefault("limit", DEFAULT_LIMIT)
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise QueryRejected("QUERY_VALUE")
    since, until = filters.get("since"), filters.get("until")
    if isinstance(since, datetime) and isinstance(until, datetime):
        if since > until:
            raise QueryRejected("QUERY_RANGE")
        if (until - since).total_seconds() > MAX_RANGE_DAYS * 86400:
            raise QueryRejected("QUERY_RANGE")
    return filters
