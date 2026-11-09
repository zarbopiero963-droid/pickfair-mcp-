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

CONTRACT_VERSION: Final = "1.14.0"
DESCRIPTOR_PATH: Final = Path(__file__).with_name("contract_v1.json")

# Route servite in sola lettura. Nessuna route di comando.
ROUTE_SCHEMAS: Final = {
    "/v1/meta": "meta",
    "/v1/status": "status",
    "/v1/reconciliation/status": "reconciliation_status",
    "/v1/account": "account",
    "/v1/exposure": "exposure",
    "/v1/positions": "positions",
    "/v1/orders": "orders",
    "/v1/config": "config",
    "/v1/markets": "markets",
    # PF-BLACKBOX-01: lettura della scatola nera.
    "/v1/blackbox/status": "blackbox_status",
    "/v1/blackbox/sessions": "blackbox_sessions",
}
# MCP-01o: l'UNICA route con query string, filtri in whitelist chiusa
# (blackbox_query.parse_events_query).
QUERY_ROUTE_SCHEMAS: Final = {"/v1/blackbox/events": "blackbox_events"}
BLACKBOX_STATUS_ROUTE: Final = "/v1/blackbox/status"
# Servite anche se la richiesta non si può registrare (il mancato record è contato): lo stato del
# registro
# serve a vedere il guasto, e /v1/meta (solo versione e capacità, nessun dato) è l'handshake senza
# cui
# l'MCP non arriverebbe nemmeno allo stato.
UNRECORDED_ALLOWED_ROUTES: Final = frozenset({BLACKBOX_STATUS_ROUTE, "/v1/meta"})
# MCP-01l: route servite con UN parametro di percorso. Il parametro deve rispettare il proprio pattern
# (mai «.» o «..»); fuori pattern la route risponde 404. Il provider riceve il valore validato.
MARKET_ID_RE: Final = re.compile(r"[0-9]{1,4}\.[0-9]{1,15}")
PARAM_ROUTE_SCHEMAS: Final = {
    "/v1/markets/{id}/book": "market_book",
    "/v1/blackbox/events/{event_id}": "blackbox_event",
}
PARAM_ROUTE_PATTERNS: Final = {
    "/v1/markets/{id}/book": re.compile(r"\A/v1/markets/(?P<id>[0-9]{1,4}\.[0-9]{1,15})/book\Z"),
    "/v1/blackbox/events/{event_id}": re.compile(r"\A/v1/blackbox/events/(?P<id>[0-9a-f]{32})\Z"),
}
# Provider che il core deve fornire: uno per ogni route servita tranne /v1/meta.
PROVIDER_NAMES: Final = frozenset(
    [name for name in ROUTE_SCHEMAS.values() if name != "meta"]
    + list(PARAM_ROUTE_SCHEMAS.values())
    + list(QUERY_ROUTE_SCHEMAS.values())
)
CAPABILITIES: Final[tuple[str, ...]] = tuple(
    [f"GET {p}" for p in ROUTE_SCHEMAS]
    + [f"GET {p}" for p in PARAM_ROUTE_SCHEMAS]
    + [f"GET {p}" for p in QUERY_ROUTE_SCHEMAS]
)
_TEMPLATE_RE: Final = re.compile(r"\{[a-z_]+\}")
_SEGMENT: Final = "[A-Za-z0-9_-][A-Za-z0-9._-]{0,63}"  # mai «.» o «..» come segmento


@lru_cache(maxsize=1)
def unserved_read_routes() -> tuple[re.Pattern[str], ...]:
    """Route di LETTURA approvate dal contratto ma non servite: rispondono 501 NOT_IMPLEMENTED.

    Un segmento parametrico (``{id}``) accetta solo un identificatore; la query, se presente nella
    route approvata, deve coincidere esattamente. Le route di comando non sono mai elencate qui.
    """
    patterns = []
    for kind, method, path in load_descriptor()["routes"]:
        if (kind != "read" or method != "GET" or path in ROUTE_SCHEMAS or path in PARAM_ROUTE_SCHEMAS
                or path in QUERY_ROUTE_SCHEMAS):
            continue
        parts = _TEMPLATE_RE.split(path)
        body = _SEGMENT.join(re.escape(part) for part in parts)
        patterns.append(re.compile(rf"\A{body}\Z"))
    return tuple(patterns)


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
    # git worktree: HEAD è nella directory del worktree, i ref dei branch nella directory comune.
    common = git
    commondir = git / "commondir"
    if commondir.is_file():
        common = (git / commondir.read_text(encoding="utf-8").strip()).resolve()
    sha = head
    if head.startswith("ref: "):
        ref = head[len("ref: ") :]
        ref_file = git / ref if (git / ref).is_file() else common / ref
        sha = ref_file.read_text(encoding="utf-8").strip() if ref_file.is_file() else ""
        if not sha:
            packed = common / "packed-refs"
            for row in packed.read_text(encoding="utf-8").splitlines() if packed.is_file() else ():
                parts = row.split(" ")
                if len(parts) == 2 and parts[1] == ref:
                    sha = parts[0]
    if not GIT_SHA_RE.fullmatch(sha):
        raise ValueError("git sha not resolvable")
    return sha
