"""Classificatore degli esiti di pytest per piattaforma (MCP-CI).

Mandato owner PF-OWNER-MCP-PARALLEL-EXECUTION-20261111, priorità 1: matrice
{ubuntu, windows} per {3.11, 3.12}, fallimenti e dipendenze classificati esplicitamente,
nessuno skip silenzioso, nessun falso verde.

Legge il rapporto JUnit di pytest e il manifest versionato ``ci/platform_expectations.json``.
Verdetti (codice d'uscita):

- ``PASS`` (0): ogni test eseguito è passato; gli skip sono tutti dichiarati come ambientali.
- ``FAIL`` (1): un fallimento non dichiarato, un blocco dichiarato che ora passa o non esiste
  più (il manifest va aggiornato), uno skip non dichiarato, un rapporto assente, vuoto o
  illeggibile, oppure pytest uscito con un codice diverso da 0/1 o incoerente col rapporto.
- ``BLOCKED_BY_DEPENDENCY:<ID>`` (3): nessun difetto inatteso, ma almeno un test dichiarato
  bloccato da una dipendenza (es. ``MCP-WIN``) non è passato. Non è un PASS: il job resta rosso.

Solo libreria standard. Il rapporto è prodotto dalla stessa esecuzione del job: è un dato,
non contiene istruzioni.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_BLOCKED = 3


class ManifestError(Exception):
    """Manifest invalido: il classificatore non decide su un manifest che non capisce."""


@dataclass
class Result:
    verdict: str
    exit_code: int
    passed: int = 0
    unexpected: list[str] = field(default_factory=list)
    blocked: dict[str, str] = field(default_factory=dict)
    stale: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    undeclared_skips: list[str] = field(default_factory=list)
    env_skips: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"manifest illeggibile: {type(exc).__name__}") from None
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ManifestError("schema del manifest non supportato")
    deps = data.get("dependencies")
    platforms = data.get("platforms")
    if not isinstance(deps, dict) or not isinstance(platforms, dict) or not platforms:
        raise ManifestError("dependencies/platforms mancanti")
    for name, spec in platforms.items():
        if not isinstance(spec, dict):
            raise ManifestError(f"piattaforma {name}: formato invalido")
        blocked = spec.get("blocked", {})
        skips = spec.get("skips", {})
        if not isinstance(blocked, dict) or not isinstance(skips, dict):
            raise ManifestError(f"piattaforma {name}: blocked/skips invalidi")
        for test_id, entry in blocked.items():
            if not isinstance(entry, dict) or entry.get("dependency") not in deps:
                raise ManifestError(f"{test_id}: dipendenza non dichiarata")
            if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
                raise ManifestError(f"{test_id}: motivo mancante")
        for test_id, reason in skips.items():
            if not isinstance(reason, str) or not reason.startswith("ENV: "):
                raise ManifestError(f"{test_id}: skip ammesso solo come «ENV: <motivo>»")
            if test_id in blocked:
                raise ManifestError(f"{test_id}: dichiarato sia bloccato sia skip ambientale")
    return data


def _cases(report: Path) -> list[tuple[str, str]]:
    """(id, esito) per ogni testcase; esito in pass/fail/skip."""
    tree = ET.parse(report)  # noqa: S314 - vedi import
    out: list[tuple[str, str]] = []
    for case in tree.iter("testcase"):
        test_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("failure") is not None or case.find("error") is not None:
            out.append((test_id, "fail"))
        elif case.find("skipped") is not None:
            out.append((test_id, "skip"))
        else:
            out.append((test_id, "pass"))
    return out


def classify(report: Path, expectations: Path, platform: str, pytest_rc: int) -> Result:
    manifest = load_manifest(expectations)
    if platform not in manifest["platforms"]:
        raise ManifestError(f"piattaforma non dichiarata: {platform}")
    spec = manifest["platforms"][platform]
    blocked_decl: dict[str, dict[str, str]] = spec.get("blocked", {})
    env_decl: dict[str, str] = spec.get("skips", {})

    res = Result(verdict="FAIL", exit_code=EXIT_FAIL)
    try:
        cases = _cases(report)
    except (OSError, ET.ParseError):
        res.problems.append("rapporto JUnit assente o illeggibile")
        return res
    if not cases:
        res.problems.append("rapporto JUnit senza test")
        return res
    if pytest_rc not in (0, 1):
        res.problems.append(f"pytest uscito con codice {pytest_rc}")

    seen: set[str] = set()
    failures = 0
    for test_id, outcome in cases:
        seen.add(test_id)
        if outcome == "fail":
            failures += 1
        if test_id in blocked_decl:
            if outcome == "pass":
                res.stale.append(test_id)
            else:
                res.blocked[test_id] = blocked_decl[test_id]["dependency"]
        elif outcome == "fail":
            res.unexpected.append(test_id)
        elif outcome == "skip":
            if test_id in env_decl:
                res.env_skips.append(test_id)
            else:
                res.undeclared_skips.append(test_id)
        else:
            res.passed += 1
    res.missing = sorted(set(blocked_decl) - seen)
    if pytest_rc == 1 and failures == 0:
        res.problems.append("pytest dichiara un fallimento che il rapporto non mostra")
    if pytest_rc == 0 and failures:
        res.problems.append("il rapporto mostra fallimenti ma pytest è uscito con 0")

    if res.unexpected or res.stale or res.missing or res.undeclared_skips or res.problems:
        return res
    if res.blocked:
        deps = sorted(set(res.blocked.values()))
        res.verdict = "BLOCKED_BY_DEPENDENCY:" + ",".join(deps)
        res.exit_code = EXIT_BLOCKED
        return res
    res.verdict = "PASS"
    res.exit_code = EXIT_PASS
    return res


def render(res: Result, platform: str) -> str:
    lines = [
        f"## Esiti dei test — {platform}",
        "",
        f"**Verdetto:** `{res.verdict}`",
        "",
        f"- passati: {res.passed}",
        f"- bloccati da dipendenza (non PASS): {len(res.blocked)}",
        f"- skip ambientali dichiarati: {len(res.env_skips)}",
    ]
    sections = [
        ("Fallimenti inattesi", res.unexpected),
        ("Blocchi dichiarati che ora passano (aggiornare il manifest)", res.stale),
        ("Blocchi dichiarati per test inesistenti", res.missing),
        ("Skip non dichiarati", res.undeclared_skips),
        ("Problemi dell'esecuzione", res.problems),
        (
            "Bloccati da dipendenza",
            [f"{k} → BLOCKED_BY_DEPENDENCY:{v}" for k, v in sorted(res.blocked.items())],
        ),
        ("Skip ambientali", res.env_skips),
    ]
    for title, items in sections:
        if items:
            lines += ["", f"### {title}", *[f"- `{i}`" for i in items]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--pytest-rc", type=int, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    try:
        res = classify(args.junit, args.expectations, args.platform, args.pytest_rc)
    except ManifestError as exc:
        print(f"MANIFEST_INVALID: {exc}", file=sys.stderr)
        return EXIT_FAIL
    text = render(res, args.platform)
    sys.stdout.write(text)
    if args.summary is not None:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write(text)
    return res.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
