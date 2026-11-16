# ruff: noqa: T201  (strumento da riga di comando: stampa il rapporto)
"""Rapporto markdown di una campagna di mutanti dal suo JSONL (nessun numero scritto a mano)."""

import collections
import hashlib
import json
import sys

path, sha, title = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(path, "rb").read()
rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
c = collections.Counter(r["status"] for r in rows)
print(f"### {title}\n")
print(
    f"Commit `{sha}` · {len(rows)} mutanti · file `{path.split('/')[-1]}` "
    f"sha256 `{hashlib.sha256(raw).hexdigest()}`\n"
)
print("| Esito | Numero |\n|---|---|")
for k in ("KILLED", "SURVIVED", "NOT_APPLICABLE", "TIMEOUT", "INFRA_ERROR"):
    print(f"| {k} | {c.get(k, 0)} |")
print()
others = [r for r in rows if r["status"] != "KILLED"]
if others:
    print("Non KILLED:\n")
    for r in others:
        print(f"- `{r['ident']}` {r['status']} — {r.get('control')} ({r['seconds']} s)")
    print()
print("<details><summary>Esito di ogni mutante (primo test fallito)</summary>\n")
print("| Mutante | Esito | Primo test fallito | s |\n|---|---|---|---|")
for r in sorted(rows, key=lambda r: r["ident"]):
    print(f"| `{r['ident']}` | {r['status']} | `{r.get('detail') or '—'}` | {r['seconds']} |")
print("\n</details>\n")
