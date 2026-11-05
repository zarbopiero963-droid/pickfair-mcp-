"""G8: esecuzione delle suite MCP/Control API del manifest `catalog/g8/pf-mcp-suites.json`.

Stesse regole del catalogo canonico di Pickfair-nogui (`scripts/pf_test_dispatch.py`): runner `pytest`, argv
FISSO dal manifest (solo percorsi `tests/` esistenti, nessun flag, nessuna risalita), evidenze junit + log,
verdetto PASS / FAIL / BLOCKED. Un test saltato fuori da `allowed_skips` non è mai PASS (BLOCKED); un
prerequisito mancante (`requires`) è BLOCKED senza eseguire nulla.

Uso: python scripts/run_suites.py <suite:ID | campaign:NOME> --evidence DIR
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "catalog" / "g8" / "pf-mcp-suites.json"
SCHEMA = "pf-mcp-suites/1"
SUITE_FIELDS = frozenset({"id", "component", "behaviour", "category", "runner", "args", "environment", "risk",
                          "timeout_seconds", "resources", "datasets", "evidence", "requires", "criteria",
                          "allowed_skips"})
ENVIRONMENTS = frozenset({"OFFLINE", "SIM", "REPLAY_RECORDED", "SANDBOX_EPHEMERAL"})
RISKS = frozenset({"LOW", "MEDIUM", "HIGH"})
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_SAFE_ARG = re.compile(r"[A-Za-z0-9_./-]+")
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


class Refused(ValueError):
    """Manifest o richiesta non validi: il messaggio è un codice, mai un dettaglio."""


def validate_manifest(raw: bytes, root: Path = ROOT) -> dict[str, Any]:
    try:
        cat = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Refused("MANIFEST_MALFORMED") from None
    if not isinstance(cat, dict) or cat.get("schema") != SCHEMA or not isinstance(cat.get("version"), int):
        raise Refused("MANIFEST_SCHEMA")
    suites = cat.get("suites")
    if not isinstance(suites, list) or not suites:
        raise Refused("MANIFEST_EMPTY")
    seen: set[str] = set()
    for s in suites:
        if not isinstance(s, dict) or set(s) != SUITE_FIELDS:
            raise Refused("SUITE_FIELDS")
        sid = s["id"]
        if not isinstance(sid, str) or not _ID.fullmatch(sid) or sid in seen:
            raise Refused(f"SUITE_ID:{sid}")
        seen.add(sid)
        if s["runner"] != "pytest" or s["environment"] not in ENVIRONMENTS or s["risk"] not in RISKS:
            raise Refused(f"SUITE_RUNNER_ENV_RISK:{sid}")
        args = s["args"]
        if not isinstance(args, list) or not args:
            raise Refused(f"BAD_ARGS:{sid}")
        for a in args:
            if (not isinstance(a, str) or not _SAFE_ARG.fullmatch(a) or ".." in a or a.startswith(("/", "-"))
                    or not (a == "tests" or a.startswith("tests/"))
                    or any(seg in ("", ".") for seg in a.split("/")) or not (root / a).exists()):
                raise Refused(f"UNSAFE_ARG:{sid}")
        t = s["timeout_seconds"]
        if not isinstance(t, int) or isinstance(t, bool) or not 0 < t <= 7200:
            raise Refused(f"SUITE_TIMEOUT:{sid}")
        if set(s["criteria"]) != {"PASS", "FAIL", "BLOCKED"} or not s["evidence"]:
            raise Refused(f"SUITE_CRITERIA:{sid}")
        if not all(isinstance(r, str) and _ENV_NAME.fullmatch(r) for r in s["requires"]):
            raise Refused(f"SUITE_REQUIRES:{sid}")
        for skip in s["allowed_skips"]:
            if (not isinstance(skip, dict) or set(skip) != {"nodeid", "reason"}
                    or not str(skip["nodeid"]).startswith(tuple(a + "/" if not a.endswith(".py") else a
                                                                for a in args))
                    or not str(skip["reason"]).strip()):
                raise Refused(f"SUITE_SKIPS:{sid}")
    for name, ids in (cat.get("campaigns") or {}).items():
        if not _ID.fullmatch(str(name)) or not isinstance(ids, list) or not ids or not set(ids) <= seen:
            raise Refused(f"CAMPAIGN:{name}")
    return cat


def resolve(cat: dict[str, Any], target: str) -> list[dict[str, Any]]:
    by_id = {s["id"]: s for s in cat["suites"]}
    kind, _, name = target.partition(":")
    if kind == "suite" and name in by_id:
        return [by_id[name]]
    if kind == "campaign" and name in (cat.get("campaigns") or {}):
        return [by_id[i] for i in cat["campaigns"][name]]
    raise Refused("TARGET_NOT_IN_MANIFEST")


def _junit_counts(path: Path) -> tuple[dict[str, int], list[str]]:
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    skipped: list[str] = []
    if not path.is_file():
        return counts, skipped
    root = ET.parse(path).getroot()
    for case in root.iter("testcase"):
        counts["tests"] += 1
        if case.find("failure") is not None:
            counts["failures"] += 1
        if case.find("error") is not None:
            counts["errors"] += 1
        if case.find("skipped") is not None:
            counts["skipped"] += 1
            file_ = case.get("file") or (case.get("classname", "").replace(".", "/") + ".py")
            skipped.append(f"{file_}::{case.get('name', '')}")
    return counts, skipped


def run_suite(suite: dict[str, Any], evidence: Path) -> dict[str, Any]:
    sid = suite["id"]
    missing = [r for r in suite["requires"] if not os.environ.get(r)]
    if missing:
        return {"suite": sid, "verdict": "BLOCKED", "reason": "REQUIRES_MISSING", "missing": missing}
    junit = evidence / f"{sid}.junit.xml"
    log = evidence / f"{sid}.log"
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}",
            *suite["args"]]
    with log.open("w") as out:
        try:
            proc = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                  timeout=suite["timeout_seconds"], check=False)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            return {"suite": sid, "verdict": "FAIL", "reason": "TIMEOUT"}
    counts, skipped = _junit_counts(junit)
    allowed = {s["nodeid"] for s in suite["allowed_skips"]}
    unexpected = [n for n in skipped if n not in allowed]
    if counts["failures"] or counts["errors"] or code not in (0, 5):
        verdict, reason = "FAIL", "TESTS_FAILED"
    elif counts["tests"] == 0:
        verdict, reason = "BLOCKED", "NO_TESTS"
    elif unexpected:
        verdict, reason = "BLOCKED", "UNEXPECTED_SKIPS"
    else:
        verdict, reason = "PASS", None
    return {"suite": sid, "verdict": verdict, "reason": reason, "exit_code": code, **counts,
            "unexpected_skips": unexpected[:20], "junit": junit.name, "log": log.name}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="suite:<id> | campaign:<nome>")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        cat = validate_manifest(MANIFEST.read_bytes())
        suites = resolve(cat, args.target)
    except Refused as exc:
        print(json.dumps({"verdict": "REFUSED", "reason": str(exc)}))
        return 2
    args.evidence.mkdir(parents=True, exist_ok=True)
    results = [run_suite(s, args.evidence) for s in suites]
    overall = "PASS" if all(r["verdict"] == "PASS" for r in results) else (
        "FAIL" if any(r["verdict"] == "FAIL" for r in results) else "BLOCKED")
    report = {"target": args.target, "verdict": overall, "results": results}
    (args.evidence / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
