"""Controllo automatico: capacità del core Pickfair non tracciate nel catalogo (PF-MCP-001/037).

Legge un checkout di Pickfair-nogui in SOLA LETTURA (analisi statica AST, nessun import del
core, nessuna esecuzione) ed estrae i «segnali di capacità»:

- ``method:<Classe>.<nome>`` — metodi pubblici delle classi indicate in ``extractors.methods``;
- ``config:<Classe>.<campo>`` — campi annotati delle classi in ``extractors.fields``;
- ``event:<NOME>`` — nomi di evento letterali passati a ``publish``/``subscribe`` del bus.

I nomi di file e classi del core sono DATI della mappa (``extractors``), non codice: lo script
non importa, non esegue e non nomina componenti del core.

Ogni segnale deve comparire in ``docs/roadmap/core_signal_map.json`` con almeno un CAP-ID
esistente in ``FUNCTIONAL_COVERAGE_MATRIX.md`` oppure con una giustificazione esplicita
(``"untracked": "<motivo>"``). Esito:

- exit 0: nessun segnale nuovo, nessun CAP-ID inesistente, nessuna voce orfana;
- exit 1: deriva (segnali nuovi non tracciati, CAP-ID sconosciuti, voci della mappa non più
  presenti nel core). La mappa non si modifica da sola: un segnale nuovo va classificato.

Uso: python scripts/capability_drift.py --core /percorso/Pickfair-nogui [--json report.json]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "docs" / "roadmap" / "core_signal_map.json"
MATRIX_PATH = ROOT / "docs" / "roadmap" / "FUNCTIONAL_COVERAGE_MATRIX.md"
EVENT_RE = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")
CAP_ROW_RE = re.compile(r"^\| (CAP-[A-Z]+-\d+) \|", re.M)
BUS_CALLS = {"publish", "subscribe"}
SCAN_DIRS = ("core", "services", "controllers", "ai", "observability")
EXCLUDED_PARTS = {"tests", ".git", "__pycache__", "venv", ".venv"}


def _python_files(core: Path) -> list[Path]:
    files = [p for p in core.glob("*.py")]
    for name in SCAN_DIRS:
        files.extend((core / name).rglob("*.py"))
    return sorted(p for p in files if not EXCLUDED_PARTS & set(p.relative_to(core).parts))


def _class(tree: ast.Module, name: str) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _load_class(core: Path, spec: dict[str, str]) -> ast.ClassDef:
    tree = ast.parse((core / spec["file"]).read_text(encoding="utf-8"))
    cls = _class(tree, spec["class"])
    if cls is None:
        raise SystemExit(f"classe {spec['class']} non trovata: struttura del core cambiata")
    return cls


def class_methods(core: Path, spec: dict[str, str]) -> set[str]:
    cls = _load_class(core, spec)
    return {
        f"method:{cls.name}.{n.name}"
        for n in cls.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and not n.name.startswith("_")
    }


def class_fields(core: Path, spec: dict[str, str]) -> set[str]:
    cls = _load_class(core, spec)
    return {
        f"config:{cls.name}.{n.target.id}"
        for n in cls.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    }


def bus_events(core: Path) -> set[str]:
    events: set[str] = set()
    for path in _python_files(core):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in BUS_CALLS or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if EVENT_RE.fullmatch(first.value):
                    events.add(f"event:{first.value}")
    return events


def core_signals(core: Path, extractors: dict[str, Any]) -> set[str]:
    signals = bus_events(core)
    for spec in extractors.get("methods", []):
        signals |= class_methods(core, spec)
    for spec in extractors.get("fields", []):
        signals |= class_fields(core, spec)
    return signals


def known_caps(matrix_text: str) -> set[str]:
    return set(CAP_ROW_RE.findall(matrix_text))


def check(signals: set[str], mapping: dict[str, Any], caps: set[str]) -> dict[str, Any]:
    entries = mapping.get("signals", {})
    untracked = sorted(signals - set(entries))
    orphaned = sorted(set(entries) - signals)
    unknown_caps: list[str] = []
    invalid: list[str] = []
    justified: list[str] = []
    for name, entry in sorted(entries.items()):
        if isinstance(entry, list) and entry and all(isinstance(c, str) for c in entry):
            unknown_caps.extend(f"{name}->{c}" for c in entry if c not in caps)
        elif (
            isinstance(entry, dict)
            and set(entry) == {"untracked"}
            and str(entry["untracked"]).strip()
        ):
            justified.append(name)
        else:
            invalid.append(name)
    return {
        "signals": len(signals),
        "mapped": len(signals & set(entries)) - len([j for j in justified if j in signals]),
        "justified_untracked": sorted(j for j in justified if j in signals),
        "untracked": untracked,
        "orphaned": orphaned,
        "unknown_caps": sorted(unknown_caps),
        "invalid_entries": invalid,
        "ok": not (untracked or orphaned or unknown_caps or invalid),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--list", action="store_true", help="stampa i segnali estratti e termina")
    args = parser.parse_args(argv)
    mapping = json.loads(args.map.read_text(encoding="utf-8"))
    signals = core_signals(args.core, mapping.get("extractors", {}))
    if args.list:
        sys.stdout.write("\n".join(sorted(signals)) + "\n")
        return 0
    report = check(signals, mapping, known_caps(args.matrix.read_text(encoding="utf-8")))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps({k: v for k, v in report.items()}, indent=2) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
