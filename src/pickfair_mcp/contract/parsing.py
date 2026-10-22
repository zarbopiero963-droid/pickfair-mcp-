"""Parsing fail-closed delle risposte upstream (Control API o adapter simulato).

Regole: solo bytes UTF-8, dimensione limitata, JSON standard senza NaN/Infinity né
numeri che diventano infiniti, profondità limitata dall'interprete, nessuna chiave
duplicata, oggetto radice, poi validazione strict del modello.
Il messaggio dell'eccezione non riporta mai il contenuto ricevuto.
"""

from __future__ import annotations

import json
import math
from typing import Any, Final

from pydantic import ValidationError

from pickfair_mcp.contract.models import MetaResponse

MAX_UPSTREAM_BYTES: Final = 64 * 1024


class UpstreamInvalidResponse(Exception):
    """La risposta upstream non rispetta il contratto."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _reject_constant(token: str) -> Any:
    raise UpstreamInvalidResponse("NON_FINITE_NUMBER")


def _finite_float(token: str) -> float:
    value = float(token)
    if math.isinf(value):
        raise UpstreamInvalidResponse("NON_FINITE_NUMBER")
    return value


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise UpstreamInvalidResponse("DUPLICATE_KEY")
        result[key] = value
    return result


def parse_json_object(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes | bytearray):
        raise UpstreamInvalidResponse("NOT_BYTES")
    if len(raw) > MAX_UPSTREAM_BYTES:
        raise UpstreamInvalidResponse("TOO_LARGE")
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        raise UpstreamInvalidResponse("NOT_UTF8") from None
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except UpstreamInvalidResponse:
        raise
    except RecursionError:
        raise UpstreamInvalidResponse("TOO_DEEP") from None
    except ValueError:
        raise UpstreamInvalidResponse("NOT_JSON") from None
    if not isinstance(value, dict):
        raise UpstreamInvalidResponse("NOT_OBJECT")
    return value


def parse_meta(raw: bytes) -> MetaResponse:
    obj = parse_json_object(raw)
    capabilities = obj.get("capabilities")
    if isinstance(capabilities, list):
        # Il JSON non ha tuple: la lista diventa tupla prima della validazione strict.
        obj = {**obj, "capabilities": tuple(capabilities)}
    try:
        return MetaResponse.model_validate(obj)
    except ValidationError:
        raise UpstreamInvalidResponse("SCHEMA_VIOLATION") from None
