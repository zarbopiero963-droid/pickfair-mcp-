"""Contratto Control API v1 lato server: versione, capability, schema hash, schemi di risposta.

Legge ``contract_v1.json``, copia identica del descrittore canonico generato dal MCP
(``pickfair-mcp contract-descriptor``). Solo libreria standard: questo package è pensato per
essere eseguito dentro il processo Pickfair senza dipendenze aggiuntive.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

CONTRACT_VERSION: Final = "1.1.0"
DESCRIPTOR_PATH: Final = Path(__file__).with_name("contract_v1.json")

# Route servite in sola lettura. Nessuna route di comando.
ROUTE_SCHEMAS: Final = {
    "/v1/meta": "meta",
    "/v1/status": "status",
    "/v1/reconciliation/status": "reconciliation_status",
}
CAPABILITIES: Final[tuple[str, ...]] = tuple(f"GET {p}" for p in ROUTE_SCHEMAS)
GIT_SHA_RE: Final = re.compile(r"^[0-9a-f]{40}$")


@lru_cache(maxsize=1)
def load_descriptor() -> dict[str, Any]:
    data = json.loads(DESCRIPTOR_PATH.read_text(encoding="ascii"))
    if not isinstance(data, dict) or data.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("descriptor version mismatch")
    return data


def hash_descriptor(descriptor: dict[str, Any]) -> str:
    canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def schema_hash() -> str:
    return hash_descriptor(load_descriptor())


def response_schema(name: str) -> dict[str, Any]:
    schema = load_descriptor()["upstream_schemas"][name]
    if not isinstance(schema, dict):
        raise ValueError("schema missing")
    return schema


def resolve_git_sha(repo_root: Path) -> str:
    """SHA del checkout letto dai file di git, senza sottoprocessi. Errore se non dimostrabile."""
    git = repo_root / ".git"
    if git.is_file():
        line = git.read_text(encoding="utf-8").strip()
        if not line.startswith("gitdir: "):
            raise ValueError("unsupported .git file")
        git = (repo_root / line[len("gitdir: ") :]).resolve()
    head = (git / "HEAD").read_text(encoding="utf-8").strip()
    sha = head
    if head.startswith("ref: "):
        ref = head[len("ref: ") :]
        ref_file = git / ref
        sha = ref_file.read_text(encoding="utf-8").strip() if ref_file.is_file() else ""
        if not sha:
            packed = git / "packed-refs"
            for row in packed.read_text(encoding="utf-8").splitlines() if packed.is_file() else ():
                parts = row.split(" ")
                if len(parts) == 2 and parts[1] == ref:
                    sha = parts[0]
    if not GIT_SHA_RE.fullmatch(sha):
        raise ValueError("git sha not resolvable")
    return sha
