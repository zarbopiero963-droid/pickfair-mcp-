"""Mutation testing mirato sui controlli critici (catalogo deterministico).

Ogni mutante disattiva un controllo di sicurezza in una copia temporanea del
repository; la suite unit+integration deve fallire (mutante KILLED). Soglia: 100 %.
Un mutante che sopravvive indica un controllo non coperto dai test.

Uso: python scripts/critical_mutations.py [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ("src", "tests", "docs", "pyproject.toml", "AGENTS.md", ".guardrails")
TEST_ARGS = ("tests/unit", "tests/integration")


@dataclass(frozen=True)
class Mutant:
    ident: str
    control: str
    edits: tuple[tuple[str, str, str], ...]  # (file, old, new): old deve comparire una volta


H = "src/pickfair_mcp/policy/handshake.py"
MO = "src/pickfair_mcp/contract/models.py"
P = "src/pickfair_mcp/contract/parsing.py"
R = "src/pickfair_mcp/tools/registry.py"
E = "src/pickfair_mcp/policy/exposure.py"
S = "src/pickfair_mcp/server.py"
C = "src/pickfair_mcp/config.py"
A = "src/pickfair_mcp/audit.py"
ME = "src/pickfair_mcp/tools/meta.py"

MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        "M01",
        "versione non supportata accettata",
        ((H, 'reasons.append("VERSION_UNSUPPORTED")', "pass"),),
    ),
    Mutant(
        "M02",
        "schema hash sconosciuto accettato",
        ((H, "elif meta.schema_hash not in accepted_hashes:", "elif False:"),),
    ),
    Mutant(
        "M03",
        "capability non approvate ignorate",
        (
            (
                H,
                'reasons.extend(f"CAPABILITY_NOT_APPROVED:{c}" for c in sorted(advertised - approved))',
                "pass",
            ),
        ),
    ),
    Mutant(
        "M04",
        "capability richieste mancanti ignorate",
        (
            (
                H,
                'reasons.extend(f"CAPABILITY_MISSING:{c}" for c in sorted(required - advertised))',
                "pass",
            ),
        ),
    ),
    Mutant(
        "M05",
        "cancello require_compatible aperto su esito non compatibile",
        (
            (
                H,
                "if result.status is not HandshakeStatus.COMPATIBLE or result.meta is None:",
                "if result.meta is None:",
            ),
            (
                H,
                "                meta=None,\n                reasons=reasons,",
                "                meta=meta,\n                reasons=reasons,",
            ),
        ),
    ),
    Mutant(
        "M06",
        "handshake non ripetuto dopo riconnessione",
        ((H, "result.epoch == self._adapter.connection_epoch", "True"),),
    ),
    Mutant(
        "M07",
        "timeout upstream non applicato",
        ((H, "with anyio.fail_after(self._timeout_s):", "if True:"),),
    ),
    Mutant(
        "M08",
        "verdetto di handshake ignorato da get_meta",
        (
            (
                ME,
                "if result.status is not HandshakeStatus.COMPATIBLE or result.meta is None:",
                "if result.meta is None:",
            ),
            (
                H,
                "                meta=None,\n                reasons=reasons,",
                "                meta=meta,\n                reasons=reasons,",
            ),
        ),
    ),
    Mutant("M09", "campi extra ammessi", ((MO, 'extra="forbid"', 'extra="ignore"'),)),
    Mutant("M10", "coercizione di tipo ammessa", ((MO, "strict=True", "strict=False"),)),
    Mutant(
        "M11", "NaN/Inf ammessi nei modelli", ((MO, "allow_inf_nan=False", "allow_inf_nan=True"),)
    ),
    Mutant(
        "M12",
        "capability duplicate ammesse",
        ((MO, 'raise ValueError("capabilities duplicate")', "pass"),),
    ),
    Mutant(
        "M13",
        "chiavi JSON duplicate ammesse",
        ((P, 'raise UpstreamInvalidResponse("DUPLICATE_KEY")', "pass"),),
    ),
    Mutant(
        "M14",
        "NaN/Infinity JSON ammessi",
        ((P, "parse_constant=_reject_constant", "parse_constant=float"),),
    ),
    Mutant(
        "M15",
        "limite di dimensione disattivato",
        ((P, "if len(raw) > MAX_UPSTREAM_BYTES:", "if False:"),),
    ),
    Mutant(
        "M16",
        "comandi registrabili con esposizione bloccata",
        (
            (
                R,
                "if route.kind is not RouteKind.READ and not exposure.commands_exposed():",
                "if False:",
            ),
        ),
    ),
    Mutant(
        "M17",
        "interruttore di esposizione aperto",
        (
            (
                E,
                "def commands_exposed() -> bool:\n    return False",
                "def commands_exposed() -> bool:\n    return True",
            ),
        ),
    ),
    Mutant(
        "M18",
        "nomi vietati non controllati",
        (
            (
                R,
                "if not TOOL_NAME_RE.fullmatch(spec.name) or FORBIDDEN_TOOL_NAME_RE.search(spec.name):",
                "if not TOOL_NAME_RE.fullmatch(spec.name):",
            ),
        ),
    ),
    Mutant(
        "M19",
        "route non coerente con il nome accettata",
        ((R, "if spec.route != expected_route:", "if False:"),),
    ),
    Mutant(
        "M20",
        "input del tool non validato",
        (
            (
                S,
                "spec.input_model.model_validate(arguments if arguments is not None else {})",
                "pass",
            ),
        ),
    ),
    Mutant(
        "M21",
        "eccezioni interne verso il client",
        (
            (
                S,
                "        except Exception:  # noqa: BLE001 - mai testo di eccezione verso il client\n"
                "            envelope = internal_error(request_id, tool_name)\n",
                "",
            ),
        ),
    ),
    Mutant(
        "M22",
        "host non loopback accettati",
        ((C, "if not address.is_loopback or (", "if False and ("),),
    ),
    Mutant(
        "M23",
        "audit senza allowlist",
        ((A, "        if key not in ALLOWED_FIELDS:\n            continue\n", ""),),
    ),
    Mutant(
        "M24",
        "tool sconosciuto non rifiutato",
        (
            (
                S,
                '                raise ToolError(ErrorCode.UNKNOWN_TOOL, reasons=("UNKNOWN_TOOL",))',
                '                spec = self._registry.get("get_meta")\n'
                "                assert spec is not None",
            ),
        ),
    ),
)


def apply(tmp: Path, mutant: Mutant) -> None:
    for rel, old, new in mutant.edits:
        path = tmp / rel
        text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"{mutant.ident}: testo da mutare trovato {count} volte in {rel}")
        path.write_text(text.replace(old, new), encoding="utf-8")


SUITE_TIMEOUT_S = 90  # la suite pulita impiega pochi secondi


def run_suite(tmp: Path) -> str:
    """'pass', 'fail' oppure 'timeout' (una suite bloccata è un mutante rilevato)."""
    env = {**os.environ, "PYTHONPATH": str(tmp / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *TEST_ARGS],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    return "pass" if proc.returncode == 0 else "fail"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pf-mcp-mut-") as base:
        clean = Path(base) / "clean"
        clean.mkdir()
        for item in COPY:
            src = ROOT / item
            if src.is_dir():
                shutil.copytree(src, clean / item, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, clean / item)
        if run_suite(clean) != "pass":
            print("BASELINE FAIL: la suite non passa sul codice non mutato")
            return 1
        results = []
        for mutant in MUTANTS:
            work = Path(base) / mutant.ident
            shutil.copytree(clean, work)
            apply(work, mutant)
            started = time.monotonic()
            outcome = run_suite(work)
            status = "SURVIVED" if outcome == "pass" else "KILLED"
            results.append(
                {
                    "id": mutant.ident,
                    "control": mutant.control,
                    "status": status,
                    "detected_by": outcome,
                    "seconds": round(time.monotonic() - started, 2),
                }
            )
            print(f"{mutant.ident} {status:8} ({outcome:7}) {mutant.control}", flush=True)
            shutil.rmtree(work)
    killed = sum(r["status"] == "KILLED" for r in results)
    score = killed / len(results)
    print(f"critical mutation score: {killed}/{len(results)} = {score:.0%}")
    if args.json:
        args.json.write_text(
            json.dumps(
                {"killed": killed, "total": len(results), "score": score, "results": results},
                indent=2,
            )
        )
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
