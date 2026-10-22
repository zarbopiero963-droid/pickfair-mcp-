"""Segreti, governance documentale e scope dichiarato dei file."""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from pickfair_mcp.contract.routes import APPROVED_ROUTES, route_key
from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.guard

# Stessi pattern di SECRET_CONTENT_RE in Pickfair-nogui, scritti in modo da non
# corrispondere al proprio sorgente.
SECRET_CONTENT_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{36,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{40,}"
    r"|\bxox[abprs]-[A-Za-z0-9-]{10,}"
    r"|\bsk-[A-Za-z0-9_-]{32,}"
    r"|\bxai-[A-Za-z0-9]{40,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\b[0-9]{8,10}:AA[A-Za-z0-9_-]{33}\b"
)
SECRET_FILE_RE = re.compile(r"(?i)(\.pem|\.key|\.p12|\.pfx|\.env|id_rsa|\.crt)$")


def repo_files() -> list[str]:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("non è un checkout git (es. copia di mutation testing)")
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git non disponibile: scope verificabile solo da un checkout")
    files = sorted({line for line in out.splitlines() if line})
    assert files
    return files


def test_no_secret_shaped_content() -> None:
    hits = []
    for name in repo_files():
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_CONTENT_RE.search(text):
            hits.append(name)  # solo il path, mai il valore
    assert hits == []


def test_no_secret_shaped_files() -> None:
    assert [n for n in repo_files() if SECRET_FILE_RE.search(n)] == []


def test_every_file_is_inside_a_declared_task_scope() -> None:
    scope = json.loads((REPO_ROOT / ".guardrails" / "allowed_scope.json").read_text())
    declared = {f for task in scope["tasks"].values() for f in task["files"]}
    undeclared = [f for f in repo_files() if f not in declared]
    assert undeclared == []


AGENTS_REQUIRED = [
    "partire da Pickfair-nogui #491",
    "#491 → #489 → #461 → #426 → #453 → #351",
    "docs/mcp_operational_contract.md",
    "Una sola PR attiva per repository",
    "MCP_MUTATION_EXPOSURE = BLOCKED_UNTIL_CORE_AUTHORITY_READY",
    "NON importa BetfairClient, TradingEngine o OrderManager",
    "NON apre il DB Pickfair, neppure in sola lettura",
    "NON usa credenziali Betfair",
    "NON parla direttamente con Betfair",
    "NON duplica formule MM, stake calculation, cashout o reconciliation",
    "NON implementa master/copy/follow",
    "Roserpina resta l'unica autorità monetaria",
    "MANUAL via MCP: doppia conferma",
    "Telegram, Copy Trading e Mirror sono SOSPESI",
    "nessun cap monetario arbitrario di default",
    "un solo set di tool",
    "Nessuna route oltre le 25 approvate",
    "PASS/FAIL/BLOCKED_ENV/NOT_RUN/RINVIATO separati",
    "RED → GREEN",
    "Nessun merge senza autorizzazione owner",
    "Nessun LIVE",
]
AGENTS_REVERSALS = [
    r"(?i)una\s+(?:sola\s+)?PR\s+(?:attiva\s+)?globale",
    r"\b(?:sim|live)_(?:place_order|cashout|cancel|replace|stop|resume|reconcile)\b(?!`)",
    r"(?i)MANUAL via MCP\s*=\s*DECISIONE ANCORA APERTA",
    r"(?i)\b(?:LIVE_DATA_SIM|PAPER|HYBRID)\b",
    r"(?i)auto-merge (?:consentito|autorizzato)",
]


def test_agents_md_carries_the_governance_clauses() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", text.replace("**", "").replace("`", ""))
    missing = [clause for clause in AGENTS_REQUIRED if clause not in flat]
    assert missing == []


@pytest.mark.parametrize("pattern", AGENTS_REVERSALS)
def test_agents_md_has_no_reversed_clause(pattern: str) -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    plain = text.replace("**", "")
    for line in plain.splitlines():
        if re.search(pattern, line) and not re.search(r"(?i)\b(vietat|non|mai|nessun)", line):
            pytest.fail(f"clausola ribaltata in AGENTS.md: {line.strip()}")


def test_contract_doc_table_matches_code() -> None:
    text = (REPO_ROOT / "docs" / "contract_v1.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (?:Read|Command) \| (GET|POST|PATCH) \| `([^`]+)` \|", text, re.M)
    assert {f"{m} {p}" for m, p in rows} == {route_key(r) for r in APPROVED_ROUTES}
    assert len(rows) == 25
