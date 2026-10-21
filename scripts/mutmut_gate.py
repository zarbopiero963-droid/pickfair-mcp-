"""Gate sul punteggio di mutmut (dopo `mutmut run`).

Punteggio = mutanti rilevati (killed + timeout) / mutanti totali. Soglia di default 85 %.
I sopravvissuti equivalenti noti sono elencati in EQUIVALENT e documentati: non
vengono esclusi dal denominatore, ma il report li distingue dai sopravvissuti nuovi.

Uso: python scripts/mutmut_gate.py [--fail-under 85] [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

DETECTED = {"killed", "timeout"}

# Mutanti equivalenti verificati a mano (comportamento identico all'originale).
EQUIVALENT = {
    # status non compatibile <=> meta assente: invariante di HandshakeResult
    "pickfair_mcp.policy.handshake.xǁHandshakeGuardǁrequire_compatible__mutmut_14",
    "pickfair_mcp.tools.meta.x_make_get_meta__mutmut_2",
    # nomi di codec equivalenti ("utf-8"/"UTF-8", "ascii"/"ASCII")
    "pickfair_mcp.contract.parsing.x_parse_json_object__mutmut_13",
    "pickfair_mcp.contract.version.x_hash_descriptor__mutmut_18",
    # ensure_ascii=True è il default di json.dumps
    "pickfair_mcp.contract.version.x_hash_descriptor__mutmut_9",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-under", type=float, default=85.0)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    out = subprocess.run(
        [sys.executable, "-m", "mutmut", "results", "--all", "true"],
        capture_output=True,
        text=True,
        check=True,
        timeout=300,
    ).stdout
    statuses: dict[str, str] = {}
    for line in out.splitlines():
        name, sep, status = line.strip().rpartition(": ")
        if sep:
            statuses[name] = status
    if not statuses:
        print("NESSUN RISULTATO: eseguire prima `mutmut run`")
        return 1
    counts = Counter(statuses.values())
    detected = sum(counts[s] for s in DETECTED)
    score = 100.0 * detected / len(statuses)
    survivors = sorted(n for n, s in statuses.items() if s not in DETECTED)
    unexpected = [n for n in survivors if n not in EQUIVALENT]
    print(f"mutmut: {dict(counts)}")
    print(f"score: {detected}/{len(statuses)} = {score:.1f}% (soglia {args.fail_under}%)")
    for name in survivors:
        tag = "equivalente" if name in EQUIVALENT else "NUOVO"
        print(f"  {tag}: {name} [{statuses[name]}]")
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "counts": dict(counts),
                    "score": score,
                    "survivors": survivors,
                    "unexpected": unexpected,
                },
                indent=2,
            )
        )
    return 0 if score >= args.fail_under and not unexpected else 1


if __name__ == "__main__":
    raise SystemExit(main())
