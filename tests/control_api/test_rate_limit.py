"""C-AUD-06: limite di frequenza della Control API (contratto 1.16.0, piano #491 v2 approvato).

Token bucket per token Bearer, controllo e scalata del gettone sotto lo stesso lock, orologio
monotono iniettabile. Valori iniziali di test 2 richieste/s, raffica 5 (decisione owner: valori
di test, il limite operativo resta da validare). Limiti ammessi 0,1–20/s e raffica 1–50: fuori
limite l'avvio è rifiutato, mai un limite «infinito».
"""

from __future__ import annotations

import math
import random
import threading
from collections.abc import Callable
from typing import Any

import pytest

from pickfair_control_api.rate_limit import (
    BURST_MAX,
    BURST_MIN,
    RATE_MAX_PER_S,
    RATE_MIN_PER_S,
    RateLimit,
    RateLimitConfigError,
    RejectionAudit,
    TokenBucket,
)

KEY = b"k" * 32


class Clock:
    """Orologio monotono controllato: fermo finché il test non lo avanza."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def bucket(
    rate: float = 2.0, burst: int = 5, clock: Clock | None = None
) -> tuple[TokenBucket, Clock]:
    clk = clock or Clock()
    return TokenBucket(RateLimit.from_values(rate, burst), clock=clk), clk


# 1. Race con orologio fermo: esattamente `burst` ammissioni, poi il ricarico misurato.


def test_race_with_frozen_clock_admits_exactly_burst_200_times() -> None:
    threads_n = 64
    for _ in range(200):
        tb, clk = bucket()
        barrier = threading.Barrier(threads_n)
        admitted: list[bool] = []
        lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            ok = tb.acquire(KEY) is None
            with lock:
                admitted.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(threads_n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert admitted.count(True) == 5
        assert admitted.count(False) == 59
        assert 0.0 <= tb.tokens(KEY) <= 5.0
    # dopo l'ultima ripetizione: 0,5 s danno esattamente 1 gettone, 10 s al più la raffica
    clk.advance(0.5)
    assert tb.acquire(KEY) is None
    assert tb.acquire(KEY) is not None
    clk.advance(10.0)
    got = sum(tb.acquire(KEY) is None for _ in range(100))
    assert got == 5


# 2. Invariante di capacità, anche con una sequenza casuale (seed fisso).


def test_capacity_invariant_random_sequence() -> None:
    rng = random.Random(20261111)
    tb, clk = bucket(rate=2.0, burst=5)
    start = clk.now
    admitted = 0
    for _ in range(20_000):
        if rng.random() < 0.3:
            clk.advance(rng.choice([0.0, 0.01, 0.1, 0.25, 0.5, 1.0, 3.0]))
        if tb.acquire(KEY) is None:
            admitted += 1
        t = tb.tokens(KEY)
        assert 0.0 <= t <= 5.0
        assert admitted <= 5 + 2.0 * (clk.now - start) + 1e-9


def test_retry_after_is_the_time_to_the_next_token() -> None:
    tb, clk = bucket(rate=2.0, burst=1)
    assert tb.acquire(KEY) is None
    wait = tb.acquire(KEY)
    assert wait is not None and math.isclose(wait, 0.5)
    clk.advance(0.25)
    wait = tb.acquire(KEY)
    assert wait is not None and math.isclose(wait, 0.25)


def test_keys_are_independent_and_bounded() -> None:
    tb, _clk = bucket(rate=2.0, burst=1)
    assert tb.acquire(b"a" * 32) is None
    assert tb.acquire(b"b" * 32) is None  # un altro token non è penalizzato
    for i in range(100):
        tb.acquire(bytes([i]) * 32)
    assert tb.key_count() <= tb.MAX_KEYS


# 7. Configurazione.


@pytest.mark.parametrize(
    ("rate", "burst"),
    [
        (0.0, 5),
        (RATE_MIN_PER_S / 2, 5),
        (RATE_MAX_PER_S * 1.01, 5),
        (math.inf, 5),
        (math.nan, 5),
        (-1.0, 5),
        (2.0, 0),
        (2.0, BURST_MAX + 1),
        (2.0, 2.5),
        (True, 5),
        (2.0, True),
        ("2", 5),
        (2.0, "5"),
        (None, 5),
    ],
)
def test_out_of_range_or_non_numeric_limits_refuse_startup(rate: Any, burst: Any) -> None:
    with pytest.raises(RateLimitConfigError):
        RateLimit.from_values(rate, burst)


def test_bounds_are_accepted() -> None:
    assert RateLimit.from_values(RATE_MIN_PER_S, BURST_MIN).burst == BURST_MIN
    assert RateLimit.from_values(RATE_MAX_PER_S, BURST_MAX).rate_per_s == RATE_MAX_PER_S
    assert RateLimit.from_values(2, 5).rate_per_s == 2.0  # intero ammesso per il ritmo


# 6. Audit verificabile dei rifiuti, aggregato per finestra.


class Sink:
    def __init__(self, ok: Callable[[], bool] = lambda: True) -> None:
        self.records: list[dict[str, Any]] = []
        self.unrecorded = 0
        self._ok = ok

    def write(self, record: dict[str, Any]) -> bool:
        if not self._ok():
            return False
        self.records.append(record)
        return True

    def add_unrecorded(self, n: int) -> None:
        self.unrecorded += n


def utc_from(clk: Clock) -> Callable[[], str]:
    return lambda: f"T{clk.now:.3f}"


def test_window_records_count_every_rejection_and_cover_the_interval() -> None:
    clk = Clock()
    sink = Sink()
    audit = RejectionAudit(
        sink.write, sink.add_unrecorded, clock=clk, utc=utc_from(clk), window_s=1.0
    )
    total = 0
    for step in range(250):
        audit.note()
        total += 1
        clk.advance(0.013 if step % 7 else 0.31)
    audit.flush(force=True)
    assert sum(r["rate_limited"]["rejected_count"] for r in sink.records) + sink.unrecorded == total
    assert sink.unrecorded == 0
    assert all(r["code"] == "RATE_LIMITED" and r["status"] == 429 for r in sink.records)
    assert all(r["phase"] == "RESULT" for r in sink.records)
    # le finestre sono ordinate, non si sovrappongono e ognuna ha inizio <= fine
    spans = [
        (r["rate_limited"]["window_from_ts"], r["rate_limited"]["window_to_ts"])
        for r in sink.records
    ]
    assert all(a <= b for a, b in spans)
    assert all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1))
    assert sink.records[-1]["rate_limited"]["cumulative_rejected"] == total
    assert len(sink.records) < total  # aggregazione reale, non un record per rifiuto


def test_window_is_written_when_it_closes_even_without_new_rejections() -> None:
    clk = Clock()
    sink = Sink()
    audit = RejectionAudit(
        sink.write, sink.add_unrecorded, clock=clk, utc=utc_from(clk), window_s=1.0
    )
    audit.note()
    audit.flush()  # finestra ancora aperta: nulla da scrivere
    assert sink.records == []
    clk.advance(1.0)
    audit.flush()  # chiusura della finestra: scritta senza attendere altri rifiuti
    assert [r["rate_limited"]["rejected_count"] for r in sink.records] == [1]


def test_failed_audit_write_is_never_silent() -> None:
    clk = Clock()
    sink = Sink(ok=lambda: False)
    audit = RejectionAudit(
        sink.write, sink.add_unrecorded, clock=clk, utc=utc_from(clk), window_s=1.0
    )
    for _ in range(7):
        audit.note()
    audit.flush(force=True)
    assert sink.records == [] and sink.unrecorded == 7


def test_raising_audit_write_is_counted_as_unrecorded() -> None:
    clk = Clock()

    def boom(_r: dict[str, Any]) -> bool:
        raise RuntimeError("registro guasto")

    lost: list[int] = []
    audit = RejectionAudit(boom, lost.append, clock=clk, utc=utc_from(clk), window_s=1.0)
    audit.note()
    audit.note()
    audit.flush(force=True)
    assert lost == [2]


# 3–5, 8. Il limite nel server reale (loopback, token reale, orologio controllato).


def _server_with(tmp_path: Any, clock: Clock, rate: float = 2.0, burst: int = 5) -> Any:
    from tests.control_api.servers import control_api

    return control_api(tmp_path, rate_limit=RateLimit.from_values(rate, burst), clock=clock)


def _get(port: int, token: str, path: str = "/v1/status") -> tuple[int, dict[str, str], Any]:
    from tests.control_api.test_server import request

    return request(port, "GET", path, token=token)


@pytest.mark.loopback
def test_saturation_never_reaches_the_core_and_returns_429_with_retry_after(tmp_path: Any) -> None:
    clk = Clock()
    with _server_with(tmp_path, clk) as (server, _s, token_path, prov):
        token = token_path.read_text()
        codes = [_get(server.port, token)[0] for _ in range(5)]
        calls_after_burst = prov.calls
        rejected = [_get(server.port, token) for _ in range(20)]
        assert prov.calls == calls_after_burst == 5  # nessuna lettura del runtime oltre il limite
    assert codes == [200] * 5
    for status, headers, body in rejected:
        assert status == 429
        assert body == {"error": {"code": "RATE_LIMITED"}}
        assert headers["retry-after"] == "1"  # 2/s: 0,5 s arrotondati per eccesso a 1
        assert token not in json_dumps(body) and token not in json_dumps(headers)
    assert server.request_counts()["RATE_LIMITED"] == 20


@pytest.mark.loopback
def test_recovery_follows_the_refill_without_exceeding_the_burst(tmp_path: Any) -> None:
    clk = Clock()
    with _server_with(tmp_path, clk) as (server, _s, token_path, _prov):
        token = token_path.read_text()
        assert [_get(server.port, token)[0] for _ in range(6)] == [200] * 5 + [429]
        clk.advance(1.0)  # 2 gettoni
        assert [_get(server.port, token)[0] for _ in range(3)] == [200, 200, 429]
        clk.advance(60.0)  # mai oltre la raffica
        assert [_get(server.port, token)[0] for _ in range(6)] == [200] * 5 + [429]


@pytest.mark.loopback
def test_unauthenticated_requests_are_refused_before_the_limit(tmp_path: Any) -> None:
    clk = Clock()
    with _server_with(tmp_path, clk) as (server, _s, token_path, _prov):
        token = token_path.read_text()
        for _ in range(10):
            assert _get(server.port, "x" * 43)[0] == 401  # non consuma il secchio del token
        assert [_get(server.port, token)[0] for _ in range(5)] == [200] * 5


@pytest.mark.loopback
def test_rejections_are_recorded_in_windows_and_never_lost(tmp_path: Any) -> None:
    clk = Clock()
    with _server_with(tmp_path, clk) as (server, _s, token_path, prov):
        token = token_path.read_text()
        for _ in range(5):
            _get(server.port, token)
        for _ in range(12):
            assert _get(server.port, token)[0] == 429
    # all'arresto la finestra aperta è scritta
    windows = [r["rate_limited"] for r in prov.records if r.get("code") == "RATE_LIMITED"]
    assert sum(w["rejected_count"] for w in windows) == 12
    assert windows[-1]["cumulative_rejected"] == 12
    # nessun record per singola richiesta rifiutata: solo i record di finestra
    assert [r for r in prov.records if r.get("status") == 429 and "rate_limited" not in r] == []


@pytest.mark.loopback
def test_failed_rejection_audit_is_counted_and_reads_fail_closed(tmp_path: Any) -> None:
    clk = Clock()
    with _server_with(tmp_path, clk) as (server, _s, token_path, prov):
        token = token_path.read_text()
        for _ in range(5):
            _get(server.port, token)
        for _ in range(3):
            assert _get(server.port, token)[0] == 429
        prov.hook_accepts = False  # il registro si guasta
        clk.advance(1.0)  # la finestra si chiude e la sua scrittura fallisce
        server._httpd.app.rejections.flush()
        status, _h, body = _get(server.port, token, "/v1/blackbox/status")
        assert status == 200 and body["requests_unrecorded"] >= 3
        assert _get(server.port, token)[0] == 503  # registro guasto: nessun dato esce


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, default=str)
