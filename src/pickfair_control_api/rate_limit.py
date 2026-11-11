"""Limite di frequenza della Control API (C-AUD-06, contratto 1.16.0).

Piano #491 v2, approvato dall'owner (D01; precisazioni del 10/11/2026):

- token bucket per token Bearer, applicato **dopo** l'autenticazione e **prima** di qualsiasi
  provider: una richiesta rifiutata non tocca il runtime;
- controllo e scalata del gettone in **un'unica operazione sotto lo stesso lock**: due richieste
  simultanee non consumano lo stesso gettone; orologio monotono iniettabile;
- limiti ammessi ``RATE_MIN_PER_S``-``RATE_MAX_PER_S`` richieste/s e raffica
  ``BURST_MIN``-``BURST_MAX``: un valore fuori limite o non numerico rifiuta l'avvio (fail-closed),
  mai un limite «infinito». Nessun valore predefinito: il chiamante (launcher del core) lo
  dichiara sempre;
- ogni rifiuto è contato e registrato nella scatola nera in record RESULT ``RATE_LIMITED``
  aggregati per finestra, con numero dei rifiuti, intervallo (primo e ultimo istante UTC) e
  totale dall'avvio. Il record di una finestra si scrive alla chiusura della finestra (al primo
  rifiuto successivo o dal controllo periodico del server, e comunque all'arresto): nessuna
  finestra resta solo in memoria. Se la scrittura fallisce, i rifiuti della finestra entrano in
  ``requests_unrecorded``: nessuna perdita silenziosa.

Solo libreria standard.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

RATE_MIN_PER_S: Final = 0.1
RATE_MAX_PER_S: Final = 20.0
BURST_MIN: Final = 1
BURST_MAX: Final = 50
REJECTION_WINDOW_S: Final = 1.0
RATE_LIMITED_CODE: Final = "RATE_LIMITED"
RATE_LIMITED_STATUS: Final = 429


class RateLimitConfigError(Exception):
    """Limiti non validi: il server non parte."""


@dataclass(frozen=True)
class RateLimit:
    rate_per_s: float
    burst: int

    @classmethod
    def from_values(cls, rate_per_s: object, burst: object) -> RateLimit:
        if isinstance(rate_per_s, bool) or not isinstance(rate_per_s, (int, float)):
            raise RateLimitConfigError("RATE_LIMIT_INVALID")
        rate = float(rate_per_s)
        if not math.isfinite(rate) or not RATE_MIN_PER_S <= rate <= RATE_MAX_PER_S:
            raise RateLimitConfigError("RATE_LIMIT_INVALID")
        if type(burst) is not int or not BURST_MIN <= burst <= BURST_MAX:
            raise RateLimitConfigError("RATE_LIMIT_INVALID")
        return cls(rate, burst)


class TokenBucket:
    """Un secchio per chiave (digest del token); controllo e scalata atomici."""

    MAX_KEYS: Final = 8  # pochi token validi alla volta (rotazione): memoria limitata

    def __init__(self, limit: RateLimit, clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(limit, RateLimit):
            raise RateLimitConfigError("RATE_LIMIT_INVALID")
        self._rate = limit.rate_per_s
        self._burst = float(limit.burst)
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: OrderedDict[bytes, tuple[float, float]] = OrderedDict()

    def acquire(self, key: bytes) -> float | None:
        """None se la richiesta è ammessa; altrimenti i secondi al prossimo gettone."""
        with self._lock:
            now = self._clock()
            tokens, at = self._buckets.get(key, (self._burst, now))
            tokens = min(self._burst, tokens + max(0.0, now - at) * self._rate)
            if tokens >= 1.0:
                self._store(key, tokens - 1.0, now)
                return None
            self._store(key, tokens, now)
            return (1.0 - tokens) / self._rate

    def _store(self, key: bytes, tokens: float, at: float) -> None:
        self._buckets[key] = (tokens, at)
        self._buckets.move_to_end(key)
        while len(self._buckets) > self.MAX_KEYS:
            self._buckets.popitem(last=False)

    def tokens(self, key: bytes) -> float:
        """Gettoni disponibili ora (per i test dell'invariante)."""
        with self._lock:
            now = self._clock()
            tokens, at = self._buckets.get(key, (self._burst, now))
            return min(self._burst, tokens + max(0.0, now - at) * self._rate)

    def key_count(self) -> int:
        with self._lock:
            return len(self._buckets)


def _utc_now() -> str:
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t * 1000) % 1000:03d}Z"


class RejectionAudit:
    """Aggrega i rifiuti per finestra e li scrive nella scatola nera; mai una perdita silenziosa."""

    def __init__(
        self,
        write: Callable[[dict[str, Any]], bool],
        add_unrecorded: Callable[[int], None],
        *,
        clock: Callable[[], float] = time.monotonic,
        utc: Callable[[], str] = _utc_now,
        window_s: float = REJECTION_WINDOW_S,
    ) -> None:
        self._write = write
        self._add_unrecorded = add_unrecorded
        self._clock = clock
        self._utc = utc
        self._window_s = window_s
        self._lock = threading.Lock()
        self._opened_at: float | None = None
        self._count = 0
        self._from_ts = ""
        self._to_ts = ""
        self._cumulative = 0

    def note(self) -> None:
        """Conta un rifiuto; una finestra già chiusa viene scritta prima di aprirne una nuova."""
        with self._lock:
            now = self._clock()
            closed = self._close_if(now, force=False)
            stamp = self._utc()
            if self._opened_at is None:
                self._opened_at, self._count, self._from_ts = now, 0, stamp
            self._count += 1
            self._to_ts = stamp
            self._cumulative += 1
        if closed is not None:
            self._emit(closed)

    def flush(self, *, force: bool = False) -> None:
        """Scrive la finestra se è chiusa (o sempre, con ``force``: arresto del server)."""
        with self._lock:
            closed = self._close_if(self._clock(), force=force)
        if closed is not None:
            self._emit(closed)

    def _close_if(self, now: float, *, force: bool) -> dict[str, Any] | None:
        if self._opened_at is None:
            return None
        if not force and now - self._opened_at < self._window_s:
            return None
        window = {
            "rejected_count": self._count,
            "window_from_ts": self._from_ts,
            "window_to_ts": self._to_ts,
            "cumulative_rejected": self._cumulative,
        }
        self._opened_at, self._count = None, 0
        return window

    def _emit(self, window: dict[str, Any]) -> None:
        record = {
            "phase": "RESULT",
            "route": None,
            "params": None,
            "request_id": None,
            "status": RATE_LIMITED_STATUS,
            "code": RATE_LIMITED_CODE,
            "duration_ms": None,
            "returned": None,
            "coalesced_before": 0,
            "rate_limited": window,
        }
        try:
            ok = self._write(record) is True
        except Exception:  # noqa: BLE001 - un registro guasto non fa cadere il server
            ok = False
        if not ok:
            self._add_unrecorded(int(window["rejected_count"]))
