"""Audit strutturato su stderr (JSON per riga), con allowlist dei campi.

stdout è riservato al protocollo MCP. Ogni campo non in allowlist viene scartato:
nessun segreto può finire nel log anche se passato per errore. I valori sono
solo primitivi, troncati e privi di caratteri di controllo.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
from typing import Final

LOGGER_NAME: Final = "pickfair_mcp.audit"
MAX_VALUE_LEN: Final = 160

ALLOWED_EVENTS: Final = frozenset(
    {"server_start", "server_stop", "tool_call", "handshake", "journal", "journal_entry"}
)
ALLOWED_FIELDS: Final = frozenset(
    {
        "request_id",
        "tool",
        "outcome",
        "ok",
        "error_code",
        "handshake_status",
        "epoch",
        "duration_ms",
        "adapter_kind",
        "certified",
        "server_version",
        "contract_version",
        "mutation_exposure",
        "operation_id",
        "correlation_id",
        "journal_writable",
        "pending_ambiguous",
    }
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_logger = logging.getLogger(LOGGER_NAME)


def _clean(value: object) -> object | None:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 3) if value == value and abs(value) != float("inf") else None
    if isinstance(value, str):
        return _CONTROL_RE.sub(" ", value)[:MAX_VALUE_LEN]
    return None


def audit_event(event: str, **fields: object) -> None:
    record: dict[str, object] = {
        "event": event if event in ALLOWED_EVENTS else "unknown_event",
        "ts": round(time.time(), 3),
    }
    for key, value in fields.items():
        if key not in ALLOWED_FIELDS:
            continue
        cleaned = _clean(value)
        if cleaned is not None or value is None:
            record[key] = cleaned
    _logger.info(json.dumps(record, sort_keys=True, ensure_ascii=True))


def configure_stderr_logging() -> None:
    """Instrada su stderr soltanto l'audit; non tocca mai stdout.

    I log dell'SDK MCP e di ogni altra libreria vengono scartati: possono contenere
    l'input grezzo del client (argomenti, righe malformate) e non sono in allowlist.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.handlers[:] = [handler]
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    root = logging.getLogger()
    root.handlers[:] = [logging.NullHandler()]
    root.setLevel(logging.CRITICAL + 1)
    logging.lastResort = None
    logging.captureWarnings(True)  # gli avvisi passano dal logging, quindi scartati
    # Nessun traceback grezzo su stderr: le eccezioni non gestite non vi arrivano.
    sys.excepthook = _silent_excepthook
    sys.unraisablehook = _silent_unraisablehook
    threading.excepthook = _silent_thread_excepthook


def _silent_excepthook(*_: object) -> None:
    return None


def _silent_unraisablehook(_: object) -> None:
    return None


def _silent_thread_excepthook(_: object) -> None:
    return None
