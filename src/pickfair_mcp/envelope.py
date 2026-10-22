"""Envelope unico dei risultati dei tool, valido sia per il successo sia per l'errore.

Lo stesso schema copre entrambi i casi, così un client che valida
`structuredContent` contro `outputSchema` lo può fare anche sugli errori.
"""

from __future__ import annotations

from typing import Annotated, Any, Generic, TypeVar

from pydantic import Field, StringConstraints, model_validator

from pickfair_mcp.contract.models import StrictModel
from pickfair_mcp.errors import MESSAGES, RETRYABLE_FOR_READS, ErrorCode, ToolError

REQUEST_ID_PATTERN = r"^req_[0-9a-f]{32}$"
REASON_PATTERN = r"^[A-Z_]+(:[A-Za-z0-9_{}/?=. -]{1,140})?$"
MAX_REASONS = 32

DataT = TypeVar("DataT", bound=StrictModel)

Reason = Annotated[str, StringConstraints(pattern=REASON_PATTERN, max_length=160)]


class ErrorDetails(StrictModel):
    reasons: Annotated[tuple[Reason, ...], Field(max_length=MAX_REASONS)]
    handshake_status: Annotated[str, StringConstraints(pattern=r"^[A-Z_]{1,32}$")] | None


class ErrorBody(StrictModel):
    code: ErrorCode
    message: Annotated[str, StringConstraints(max_length=200)]
    retryable: bool
    details: ErrorDetails


class Envelope(StrictModel, Generic[DataT]):
    ok: bool
    request_id: Annotated[str, StringConstraints(pattern=REQUEST_ID_PATTERN)]
    tool: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,47}$")] | None
    data: DataT | None
    error: ErrorBody | None

    @model_validator(mode="after")
    def _consistent(self) -> Envelope[DataT]:
        if self.ok != (self.data is not None) or self.ok == (self.error is not None):
            raise ValueError("envelope incoerente: ok, data ed error non concordano")
        return self


def success(request_id: str, tool: str, data: StrictModel) -> dict[str, Any]:
    return {"ok": True, "request_id": request_id, "tool": tool, "data": data, "error": None}


def failure(request_id: str, tool: str | None, err: ToolError) -> dict[str, Any]:
    body = ErrorBody(
        code=err.code,
        message=MESSAGES[err.code],
        retryable=err.code in RETRYABLE_FOR_READS,
        details=ErrorDetails(reasons=_bounded(err.reasons), handshake_status=err.handshake_status),
    )
    return {"ok": False, "request_id": request_id, "tool": tool, "data": None, "error": body}


def _bounded(reasons: tuple[str, ...]) -> tuple[str, ...]:
    """Al massimo MAX_REASONS motivi; se troncati, l'ultimo lo dichiara."""
    if len(reasons) <= MAX_REASONS:
        return reasons
    return (*reasons[: MAX_REASONS - 1], "REASONS_TRUNCATED")


def internal_error(request_id: str, tool: str | None) -> dict[str, Any]:
    return failure(request_id, tool, ToolError(ErrorCode.INTERNAL_ERROR, reasons=("INTERNAL",)))
