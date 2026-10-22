"""Retry ammesso solo per letture idempotenti. Le mutazioni non passano mai di qui."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import anyio

from pickfair_mcp.adapters.base import UpstreamTimeout, UpstreamUnavailable
from pickfair_mcp.errors import ErrorCode, ToolError

T = TypeVar("T")
MAX_READ_ATTEMPTS = 5


async def read_with_retry(
    read: Callable[[], Awaitable[T]], *, attempts: int, timeout_s: float
) -> T:
    if not 1 <= attempts <= MAX_READ_ATTEMPTS:
        raise ValueError("attempts")
    last = ErrorCode.UPSTREAM_UNAVAILABLE
    for _ in range(attempts):
        try:
            with anyio.fail_after(timeout_s):
                return await read()
        except (TimeoutError, UpstreamTimeout):
            last = ErrorCode.UPSTREAM_TIMEOUT
        except UpstreamUnavailable:
            last = ErrorCode.UPSTREAM_UNAVAILABLE
    raise ToolError(last, reasons=("READ_RETRY_EXHAUSTED",))
