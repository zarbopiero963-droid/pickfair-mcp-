"""Ogni mutante critico deve applicarsi: il suo originale compare esattamente una volta nel file.

Senza questa guardia un mutante diventa inapplicabile in silenzio quando il codice cambia (è
successo a 9 mutanti fra MCP-01d e MCP-01n): il controllo che doveva provare resta scoperto e
nessuno lo vede.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# guardia: sotto mutmut i sorgenti sono riscritti e i testi da mutare non compaiono più
pytestmark = pytest.mark.guard

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import critical_mutations  # noqa: E402


def test_every_mutant_applies_exactly_once() -> None:
    stale = []
    for mutant in critical_mutations.MUTANTS:
        for path, original, _mutated in mutant.edits:
            count = (REPO_ROOT / path).read_text(encoding="utf-8").count(original)
            if count != 1:
                stale.append(f"{mutant.ident}: {path} ({count}x)")
    assert stale == []


def test_mutant_identifiers_are_unique() -> None:
    idents = [m.ident for m in critical_mutations.MUTANTS]
    assert len(idents) == len(set(idents))
