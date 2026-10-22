"""Gate «independent-review»: verdetto leggibile da macchina nei commenti della PR.

Passa solo se il commento più recente intitolato «Independent review» (prima riga),
di un autore OWNER/MEMBER/COLLABORATOR, dichiara `REVIEWED-SHA: <sha completo>`
uguale alla head della PR e contiene
esattamente una riga `REVIEW-VERDICT: APPROVE`, esattamente una riga `REVIEWED-SHA`
e nessuna riga che inizi con `BLOCKING:`. Un nuovo push cambia la head e invalida
ogni verdetto precedente. Il parser è puro: nessuna rete; il workflow gli passa i
commenti già scaricati.

Uso: python scripts/review_gate.py --comments comments.json --head-sha <sha>
Uscita 0 = PASS, 1 = FAIL; stampa il motivo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TITLE_RE = re.compile(r"^[#*\s]*Independent review\b", re.IGNORECASE)
VERDICT_RE = re.compile(r"^\s*REVIEW-VERDICT:\s*(\S*)\s*$")
SHA_LINE_RE = re.compile(r"^\s*REVIEWED-SHA:\s*(\S*)\s*$")
# Prefissi markdown ammessi (spazi, citazioni, elenchi puntati/numerati, titoli,
# grassetto/codice/parentesi) e chiusure prima dei due punti; case-insensitive.
# «NON-BLOCKING» non corrisponde: il prefisso non può contenere lettere.
BLOCKING_RE = re.compile(r"^[\s>*+\-#\d.)(\[_`]*BLOCKING[*_`\])]*\s*:", re.IGNORECASE)
# Repository pubblico: contano solo commenti di chi ha accesso al repository.
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def _parse(body: str) -> tuple[list[str], list[str], int] | None:
    lines = body.replace("\r\n", "\n").split("\n")
    if not lines or not TITLE_RE.match(lines[0]):
        return None
    verdicts = [m.group(1) for m in map(VERDICT_RE.match, lines) if m]
    shas = [m.group(1).lower() for m in map(SHA_LINE_RE.match, lines) if m]
    blocking = sum(1 for line in lines if BLOCKING_RE.match(line))
    return verdicts, shas, blocking


def evaluate(comments: list[Any], head_sha: str) -> tuple[bool, str]:
    head = head_sha.lower()
    if not SHA_RE.match(head):
        raise ValueError("head sha non valido")
    candidates = []
    for comment in comments:
        if not isinstance(comment, dict) or not isinstance(comment.get("body"), str):
            continue
        if comment.get("author_association") not in TRUSTED_ASSOCIATIONS:
            continue
        parsed = _parse(comment["body"])
        if parsed is None:
            continue
        cid = comment.get("id", 0)
        candidates.append(
            (str(comment.get("created_at", "")), cid if isinstance(cid, int) else 0, parsed)
        )
    if not candidates:
        return False, "NO_REVIEW_FOR_HEAD"
    # Decide solo il commento «Independent review» più recente: un verdetto più nuovo,
    # anche malformato o per un altro SHA, invalida quelli precedenti (fail-closed).
    candidates.sort(key=lambda item: (item[0], item[1]))
    verdicts, shas, blocking = candidates[-1][2]
    if len(verdicts) != 1 or len(shas) != 1 or not SHA_RE.match(shas[0]):
        return False, "MALFORMED_VERDICT"
    if shas[0] != head:
        return False, "NO_REVIEW_FOR_HEAD"
    if blocking:
        return False, f"BLOCKING_FINDINGS:{blocking}"
    if verdicts[0] != "APPROVE":
        return False, "NOT_APPROVED"
    return True, "APPROVED"


def _flatten(data: Any) -> list[Any]:
    if isinstance(data, list) and all(isinstance(page, list) for page in data):
        return [item for page in data for item in page]
    return data if isinstance(data, list) else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comments", type=Path, required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    comments = _flatten(json.loads(args.comments.read_text(encoding="utf-8")))
    ok, reason = evaluate(comments, args.head_sha)
    print(("PASS " if ok else "FAIL ") + reason)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
