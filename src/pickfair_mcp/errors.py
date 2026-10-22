"""Codici di errore strutturati restituiti dai tool MCP."""

from __future__ import annotations

from enum import Enum
from typing import Final


class ErrorCode(Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    CONTRACT_INCOMPATIBLE = "CONTRACT_INCOMPATIBLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_INVALID_RESPONSE = "UPSTREAM_INVALID_RESPONSE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    JOURNAL_UNAVAILABLE = "JOURNAL_UNAVAILABLE"
    FORBIDDEN = "FORBIDDEN"


# Messaggi fissi: nessun testo proveniente da eccezioni o dall'upstream.
MESSAGES: Final[dict[ErrorCode, str]] = {
    ErrorCode.INVALID_REQUEST: "Arguments do not match the tool input schema.",
    ErrorCode.UNKNOWN_TOOL: "Tool not available in this server.",
    ErrorCode.CONTRACT_INCOMPATIBLE: (
        "Control API contract is not compatible with this adapter; operations are blocked."
    ),
    ErrorCode.UPSTREAM_TIMEOUT: "Control API did not answer within the configured timeout.",
    ErrorCode.UPSTREAM_UNAVAILABLE: "Control API is not reachable.",
    ErrorCode.UPSTREAM_INVALID_RESPONSE: "Control API answer violates the contract.",
    ErrorCode.INTERNAL_ERROR: "Internal adapter error; no operation was performed.",
    ErrorCode.JOURNAL_UNAVAILABLE: (
        "Request journal unavailable; mutations are blocked, reads are still allowed."
    ),
    ErrorCode.FORBIDDEN: "Caller is not authorized for this tool; nothing was performed.",
}

# Solo letture idempotenti possono essere ripetute dal client. I comandi
# (non esposti in MCP-01a) non saranno mai retryable lato MCP.
RETRYABLE_FOR_READS: Final[frozenset[ErrorCode]] = frozenset(
    {ErrorCode.UPSTREAM_TIMEOUT, ErrorCode.UPSTREAM_UNAVAILABLE}
)


class ToolError(Exception):
    """Errore atteso di un tool: diventa un envelope strutturato con isError."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        reasons: tuple[str, ...] = (),
        handshake_status: str | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.reasons = reasons
        self.handshake_status = handshake_status
