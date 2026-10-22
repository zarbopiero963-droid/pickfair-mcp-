"""Gate «independent-review»: verdetto leggibile da macchina nei commenti della PR.

Passa solo se il commento più recente intitolato «Independent review» (prima riga),
di un autore OWNER/MEMBER/COLLABORATOR, dichiara `REVIEWED-SHA: <sha completo>`
uguale alla head della PR e contiene
esattamente una riga `REVIEW-VERDICT: APPROVE`, esattamente una riga `REVIEWED-SHA`
e nessuna riga che inizi con `BLOCKING:`. Un nuovo push cambia la head e invalida
ogni verdetto precedente. Il parser è puro: nessuna rete; il workflow gli passa i
commenti già scaricati.

Formato (rigido, fail-closed): le righe `REVIEW-VERDICT: <VALORE>` e
`REVIEWED-SHA: <40 hex>` vanno scritte in chiaro, senza grassetto, backtick o altra
decorazione (G3): una riga decorata non è riconosciuta e il verdetto risulta
MALFORMED. Il testo è normalizzato (NFKC, niente caratteri invisibili, niente tag HTML)
prima dell'analisi.

Uso: python scripts/review_gate.py --comments comments.json --head-sha <sha>
Uscita 0 = PASS, 1 = FAIL; stampa il motivo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TITLE_RE = re.compile(r"^[#*\s]*Independent review\b", re.IGNORECASE)
VERDICT_RE = re.compile(r"^\s*REVIEW-VERDICT:\s*(\S*)\s*$")
SHA_LINE_RE = re.compile(r"^\s*REVIEWED-SHA:\s*(\S*)\s*$")
# G1 (review 4a5b1c7): nessuna allow-list di prefissi. Dopo la normalizzazione
# (NFKC, rimozione dei caratteri di formato invisibili e dei tag HTML) una riga che
# contiene la parola BLOCKING, in qualsiasi forma o posizione e senza distinzione di
# maiuscole, conta come finding bloccante; sono escluse solo le forme NON-BLOCKING.
# Un falso positivo fa fallire il gate (fail-closed): il reviewer non deve usare la
# parola in un APPROVE se non nella forma NON-BLOCKING.
# Confini su lettere/cifre (non \b): «_» e «*» attorno alla parola non la nascondono.
NON_BLOCKING_RE = re.compile(
    r"(?<![A-Za-z0-9])NON[\s\-_\u2010-\u2015]*BLOCKING(?![A-Za-z0-9])", re.IGNORECASE
)
BLOCKING_WORD_RE = re.compile(r"(?<![A-Za-z0-9])BLOCKING(?![A-Za-z0-9])", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]*>")
# Repository pubblico: contano solo commenti di chi ha accesso al repository.
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def normalize(body: str) -> str:
    text = unicodedata.normalize("NFKC", body)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return HTML_TAG_RE.sub("", text)


def is_blocking(line: str) -> bool:
    return BLOCKING_WORD_RE.search(NON_BLOCKING_RE.sub(" ", line)) is not None


def _parse(body: str) -> tuple[list[str], list[str], int] | None:
    lines = normalize(body).replace("\r\n", "\n").split("\n")
    if not lines or not TITLE_RE.match(lines[0]):
        return None
    verdicts = [m.group(1) for m in map(VERDICT_RE.match, lines) if m]
    shas = [m.group(1).lower() for m in map(SHA_LINE_RE.match, lines) if m]
    blocking = sum(1 for line in lines if is_blocking(line))
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
