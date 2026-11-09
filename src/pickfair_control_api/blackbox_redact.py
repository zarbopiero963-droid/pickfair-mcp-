"""MCP-01o: seconda redazione delle risposte della scatola nera (PF-BLACKBOX-01, difesa in
profondità).

Il motore registra già redatto. La Control API non si fida: nei dizionari
`values_before`/`values_after`
di ogni evento (lista e catena causale) il valore di un nome sensibile diventa ``[REDACTED]`` e il
campo
`redacted` della risposta conta le sostituzioni. Un valore sensibile non può uscire dalla Control
API
nemmeno se il motore lo avesse scritto per errore. Solo stdlib.
"""

from __future__ import annotations

import re
from typing import Any, Final

REDACTED: Final = "[REDACTED]"
# Copia di pickfair_mcp.contract.models.BLACKBOX_SENSITIVE_FRAGMENTS (verificata da un test).
SENSITIVE_FRAGMENTS: Final = (
    "token", "secret", "password", "passwd", "bearer", "credential", "cookie", "ssoid", "private",
    "api_key", "apikey", "application", "customer_ref", "certificate",
)
# Copia di BLACKBOX_SENSITIVE_SEGMENTS: sensibili solo come segmento intero del nome.
SENSITIVE_SEGMENTS: Final = ("auth", "authorization", "pem", "otp")


def is_sensitive(name: object) -> bool:
    lowered = str(name).lower()
    if any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS):
        return True
    return any(part in SENSITIVE_SEGMENTS for part in re.split(r"[_.\-]", lowered))


def _redact_event(event: Any) -> int:
    count = 0
    if not isinstance(event, dict):
        return 0
    for field in ("values_before", "values_after", "data"):
        values = event.get(field)
        if isinstance(values, dict):
            for name in list(values):
                if is_sensitive(name) and values[name] != REDACTED:
                    values[name] = REDACTED
                    count += 1
    return count


def redact_response(body: Any) -> Any:
    """Copia della risposta con i valori sensibili redatti e `redacted` aggiornato; mai in place."""
    if not isinstance(body, dict):
        return body
    out = {**body}
    events: list[Any] = []
    for key in ("events", "chain"):
        if isinstance(out.get(key), list):
            out[key] = [_copy_event(e) for e in out[key]]
            events.extend(out[key])
    if isinstance(out.get("event"), dict):
        out["event"] = _copy_event(out["event"])
        events.append(out["event"])
    count = sum(_redact_event(e) for e in events)
    if count and type(out.get("redacted")) is int:
        out["redacted"] = out["redacted"] + count
    return out


def _copy_event(event: Any) -> Any:
    if not isinstance(event, dict):
        return event
    copy = {**event}
    for field in ("values_before", "values_after", "data"):
        if isinstance(copy.get(field), dict):
            copy[field] = dict(copy[field])
    return copy
