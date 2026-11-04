"""Retry ammesso solo per letture idempotenti. Le mutazioni non passano mai di qui."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import anyio

from pickfair_mcp.adapters.base import (
    UpstreamNotImplemented,
    UpstreamProtocolError,
    UpstreamTimeout,
    UpstreamUnauthorized,
    UpstreamUnavailable,
)
from pickfair_mcp.errors import ErrorCode, ToolError

T = TypeVar("T")
MAX_READ_ATTEMPTS = 5


async def read_with_retry(
    read: Callable[[], Awaitable[T]], *, attempts: int, timeout_s: float
) -> T:
    if not 1 <= attempts <= MAX_READ_ATTEMPTS:
        raise ValueError
    last = ErrorCode.UPSTREAM_UNAVAILABLE
    for _ in range(attempts):
        try:
            with anyio.fail_after(timeout_s):
                return await read()
        except (TimeoutError, UpstreamTimeout):
            last = ErrorCode.UPSTREAM_TIMEOUT
        except UpstreamUnavailable:
            last = ErrorCode.UPSTREAM_UNAVAILABLE
        except UpstreamUnauthorized:
            # Credenziali rifiutate: ripetere non serve e non è mai sicuro.
            raise ToolError(
                ErrorCode.UPSTREAM_UNAUTHORIZED, reasons=("UPSTREAM_UNAUTHORIZED",)
            ) from None
        except UpstreamNotImplemented:
            # Capacità assente nel core: ripetere non la fa comparire.
            raise ToolError(
                ErrorCode.UPSTREAM_NOT_IMPLEMENTED, reasons=("UPSTREAM_NOT_IMPLEMENTED",)
            ) from None
        except UpstreamProtocolError as exc:
            raise ToolError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                reasons=(f"UPSTREAM_INVALID_RESPONSE:{exc.reason}",),
            ) from None
    raise ToolError(last, reasons=("READ_RETRY_EXHAUSTED",))
