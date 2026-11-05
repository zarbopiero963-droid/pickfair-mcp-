"""Versione del contratto, descrittore canonico, schema hash e compat matrix.

Politica (fail-closed): l'adapter è compatibile solo se la coppia
(contract_version, schema_hash) dichiarata dal core è presente nella compat matrix.
Una versione o un hash sconosciuti, anche se «vicini», producono
CONTRACT_INCOMPATIBLE. La tolleranza semver sulle minor è un'alternativa
documentata in docs/contract_v1.md, non adottata.

Nomi e forma dei campi di /v1/meta sono PROVISIONAL finché PF-API-0 non li ratifica.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from pickfair_mcp.contract.routes import APPROVED_ROUTES, route_key

CONTRACT_NAME: Final = "pickfair-control-api"
SUPPORTED_CONTRACT_VERSION: Final = "1.6.0"
DESCRIPTOR_PATH: Final = Path(__file__).with_name("descriptor_v1.json")

SEMVER_PATTERN: Final = r"^(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})$"
GIT_SHA_PATTERN: Final = r"^[0-9a-f]{40}$"
SCHEMA_HASH_PATTERN: Final = r"^[0-9a-f]{64}$"
CAPABILITY_PATTERN: Final = r"^(GET|POST|PATCH) /v1/[A-Za-z0-9_{}/?=.-]{1,120}$"
MAX_CAPABILITIES: Final = 64

# Schema canonico della risposta di GET /v1/meta (sorgente di verità del contratto
# lato MCP; il modello pydantic viene verificato contro questo schema dai test).
META_RESPONSE_SCHEMA: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["contract_version", "capabilities", "git_sha", "schema_hash"],
        "properties": {
            "contract_version": {"type": "string", "pattern": SEMVER_PATTERN},
            "capabilities": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_CAPABILITIES,
                "uniqueItems": True,
                "items": {"type": "string", "pattern": CAPABILITY_PATTERN},
            },
            "git_sha": {"type": "string", "pattern": GIT_SHA_PATTERN},
            "schema_hash": {"type": "string", "pattern": SCHEMA_HASH_PATTERN},
        },
    }
)

APPROVED_CAPABILITIES: Final[frozenset[str]] = frozenset(route_key(r) for r in APPROVED_ROUTES)


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [thaw(v) for v in value]
    return value


def load_contract_descriptor() -> dict[str, Any]:
    """Descrittore canonico salvato (generato da `contract/descriptor.py`)."""
    data = json.loads(DESCRIPTOR_PATH.read_text(encoding="ascii"))
    if not isinstance(data, dict) or data.get("contract_version") != SUPPORTED_CONTRACT_VERSION:
        raise ValueError("descriptor version mismatch")
    return data


def hash_descriptor(descriptor: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        thaw(descriptor), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def contract_schema_hash() -> str:
    return hash_descriptor(load_contract_descriptor())


COMPAT_MATRIX: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {SUPPORTED_CONTRACT_VERSION: frozenset({contract_schema_hash()})}
)
