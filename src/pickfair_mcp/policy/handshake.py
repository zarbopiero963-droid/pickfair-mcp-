"""Handshake di versione e capability con la Control API (fail-closed).

- `perform()` esegue sempre un nuovo GET /v1/meta e aggiorna lo stato.
- `require_compatible()` è il cancello che ogni futuro tool deve attraversare:
  riusa l'handshake dello stesso epoch, lo ripete dopo una riconnessione,
  resta bloccato su un contratto incompatibile finché l'epoch non cambia.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final

import anyio

from pickfair_mcp.adapters.base import ControlApiAdapter, UpstreamTimeout, UpstreamUnavailable
from pickfair_mcp.contract.models import MetaResponse
from pickfair_mcp.contract.parsing import UpstreamInvalidResponse, parse_meta
from pickfair_mcp.contract.version import APPROVED_CAPABILITIES, COMPAT_MATRIX
from pickfair_mcp.errors import ErrorCode

HANDSHAKE_REQUIRED_CAPABILITIES: Final[frozenset[str]] = frozenset({"GET /v1/meta"})
MIN_TIMEOUT_S: Final = 0.05
MAX_TIMEOUT_S: Final = 30.0


class HandshakeStatus(Enum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class HandshakeResult:
    status: HandshakeStatus
    epoch: int
    meta: MetaResponse | None
    reasons: tuple[str, ...]
    error_code: ErrorCode | None


class HandshakeFailed(Exception):
    def __init__(self, code: ErrorCode, reasons: tuple[str, ...], status: HandshakeStatus):
        super().__init__(code.value)
        self.code = code
        self.reasons = reasons
        self.status = status


def check_compatibility(
    meta: MetaResponse,
    *,
    matrix: Mapping[str, frozenset[str]],
    approved: frozenset[str],
    required: frozenset[str],
) -> tuple[str, ...]:
    """Ragioni di incompatibilità; tupla vuota soltanto se tutto è dimostrato."""
    reasons: list[str] = []
    accepted_hashes = matrix.get(meta.contract_version)
    if accepted_hashes is None:
        reasons.append("VERSION_UNSUPPORTED")
    elif meta.schema_hash not in accepted_hashes:
        reasons.append("SCHEMA_HASH_UNKNOWN")
    advertised = frozenset(meta.capabilities)
    # Il testo delle capability upstream non approvate non viene mai riportato:
    # è un dato non fidato (prompt injection) e non serve per decidere.
    if advertised - approved:
        reasons.append("CAPABILITY_NOT_APPROVED")
    # Le capability richieste vengono dal codice MCP: il loro nome è sicuro.
    reasons.extend(f"CAPABILITY_MISSING:{c}" for c in sorted(required - advertised))
    reasons.extend(f"CAPABILITY_REQUIRED_NOT_APPROVED:{c}" for c in sorted(required - approved))
    return tuple(dict.fromkeys(reasons))


def validate_timeout_s(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("timeout must be a number of seconds")
    seconds = float(value)
    if not math.isfinite(seconds) or not MIN_TIMEOUT_S <= seconds <= MAX_TIMEOUT_S:
        raise ValueError("timeout out of range")
    return seconds


class HandshakeGuard:
    def __init__(
        self,
        adapter: ControlApiAdapter,
        *,
        timeout_s: float,
        matrix: Mapping[str, frozenset[str]] = COMPAT_MATRIX,
        approved: frozenset[str] = APPROVED_CAPABILITIES,
    ) -> None:
        self._adapter = adapter
        self._timeout_s = validate_timeout_s(timeout_s)
        self._matrix = matrix
        self._approved = approved
        self._last: HandshakeResult | None = None
        self._lock = anyio.Lock()

    @property
    def last_result(self) -> HandshakeResult | None:
        return self._last

    async def perform(self) -> HandshakeResult:
        async with self._lock:
            return await self._perform_locked()

    async def _perform_locked(self) -> HandshakeResult:
        # Nessun verdetto precedente sopravvive a un handshake interrotto
        # (cancellazione o errore imprevisto): fail-closed.
        self._last = None
        epoch = self._adapter.connection_epoch
        result = await self._evaluate(epoch)
        self._last = result
        return result

    async def _evaluate(self, epoch: int) -> HandshakeResult:
        try:
            with anyio.fail_after(self._timeout_s):
                raw = await self._adapter.get_meta_raw()
        except TimeoutError:
            return self._failed(epoch, ErrorCode.UPSTREAM_TIMEOUT, ("UPSTREAM_TIMEOUT",))
        except UpstreamTimeout:
            return self._failed(epoch, ErrorCode.UPSTREAM_TIMEOUT, ("UPSTREAM_TIMEOUT",))
        except UpstreamUnavailable:
            return self._failed(epoch, ErrorCode.UPSTREAM_UNAVAILABLE, ("UPSTREAM_UNAVAILABLE",))
        except Exception:  # noqa: BLE001 - qualunque guasto dell'adapter è fail-closed
            return self._failed(epoch, ErrorCode.UPSTREAM_UNAVAILABLE, ("ADAPTER_FAILURE",))
        try:
            meta = parse_meta(raw)
            reasons = check_compatibility(
                meta,
                matrix=self._matrix,
                approved=self._approved,
                required=HANDSHAKE_REQUIRED_CAPABILITIES,
            )
        except UpstreamInvalidResponse as exc:
            return self._invalid(epoch, exc.reason)
        except Exception:  # noqa: BLE001 - qualunque guasto di parsing è fail-closed
            return self._invalid(epoch, "PARSE_FAILURE")
        if reasons:
            return HandshakeResult(
                status=HandshakeStatus.INCOMPATIBLE,
                epoch=epoch,
                meta=None,
                reasons=reasons,
                error_code=ErrorCode.CONTRACT_INCOMPATIBLE,
            )
        return HandshakeResult(
            status=HandshakeStatus.COMPATIBLE,
            epoch=epoch,
            meta=meta,
            reasons=(),
            error_code=None,
        )

    @staticmethod
    def _invalid(epoch: int, reason: str) -> HandshakeResult:
        return HandshakeResult(
            status=HandshakeStatus.INCOMPATIBLE,
            epoch=epoch,
            meta=None,
            reasons=(f"UPSTREAM_INVALID_RESPONSE:{reason}",),
            error_code=ErrorCode.UPSTREAM_INVALID_RESPONSE,
        )

    @staticmethod
    def _failed(epoch: int, code: ErrorCode, reasons: tuple[str, ...]) -> HandshakeResult:
        return HandshakeResult(
            status=HandshakeStatus.UNAVAILABLE,
            epoch=epoch,
            meta=None,
            reasons=reasons,
            error_code=code,
        )

    async def require_compatible(self, capabilities: frozenset[str]) -> MetaResponse:
        """Restituisce i meta compatibili o solleva HandshakeFailed. Mai un default permissivo."""
        async with self._lock:
            result = self._last
            same_epoch = result is not None and result.epoch == self._adapter.connection_epoch
            needs_handshake = (
                result is None or not same_epoch or result.status is HandshakeStatus.UNAVAILABLE
            )
            if needs_handshake:
                result = await self._perform_locked()
        assert result is not None
        if result.status is not HandshakeStatus.COMPATIBLE or result.meta is None:
            code = result.error_code or ErrorCode.CONTRACT_INCOMPATIBLE
            raise HandshakeFailed(code, result.reasons, result.status)
        missing = check_compatibility(
            result.meta, matrix=self._matrix, approved=self._approved, required=capabilities
        )
        if missing:
            raise HandshakeFailed(
                ErrorCode.CONTRACT_INCOMPATIBLE, missing, HandshakeStatus.INCOMPATIBLE
            )
        return result.meta
