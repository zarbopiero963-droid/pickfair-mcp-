# ruff: noqa: T201, S603  (strumento da riga di comando: stampa il risultato ed esegue pytest)
"""Campagna completa dei mutanti critici, in parallelo, con il risultato di ogni mutante.

Stesso catalogo, stessi file copiati e stessi test di scripts/critical_mutations.py (importati dal
worktree sotto prova). Per ogni mutante: KILLED (test falliti, con il primo test fallito), SURVIVED,
NOT_APPLICABLE (originale non presente esattamente una volta), TIMEOUT, INFRA_ERROR (pytest non ha
eseguito: collezione, import, uso). Ogni worker usa una propria copia; esito scritto riga per riga.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
WORKERS = int(sys.argv[3])
sys.path.insert(0, str(SRC / "scripts"))
import critical_mutations as c  # noqa: E402

c.SUITE_TIMEOUT_S = 400  # 3 worker in parallelo: la suite dura di piu, 90 s darebbe falsi TIMEOUT


def run_suite(work):
    env = {**os.environ, "PYTHONPATH": str(work / "src") + os.pathsep + str(work)}
    t = time.monotonic()
    try:
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-x",
                "-p",
                "no:cacheprovider",
                "-rf",
                *c.TEST_ARGS,
            ],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            timeout=c.SUITE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", None, time.monotonic() - t
    failed = re.findall(r"^FAILED (\S+)", p.stdout, re.M)
    status = {0: "SURVIVED", 1: "KILLED"}.get(p.returncode, "INFRA_ERROR")
    return (
        status,
        (failed[0] if failed else (p.stdout.strip().splitlines() or [""])[-1][:200]),
        time.monotonic() - t,
    )


def worker(idents):
    base = Path(tempfile.mkdtemp(prefix="pf-mcp-camp-"))
    work = base / "w"
    work.mkdir()
    for item in c.COPY:
        s = SRC / item
        (
            shutil.copytree(s, work / item, ignore=shutil.ignore_patterns("__pycache__"))
            if s.is_dir()
            else shutil.copy2(s, work / item)
        )
    status, first, dur = run_suite(work)
    results = [
        {
            "ident": "BASELINE",
            "status": "PASS" if status == "SURVIVED" else "BASELINE_FAIL",
            "detail": first,
            "seconds": round(dur, 1),
        }
    ]
    if status != "SURVIVED":
        shutil.rmtree(base, ignore_errors=True)
        return results
    by_id = {m.ident: m for m in c.MUTANTS}
    for ident in idents:
        m = by_id[ident]
        originals = {}
        applicable = True
        for f, o, _n in m.edits:
            path = work / f
            text = originals.setdefault(path, path.read_text(encoding="utf-8"))
            if text.count(o) != 1:
                applicable = False
        if not applicable:
            rec = {
                "ident": ident,
                "status": "NOT_APPLICABLE",
                "detail": None,
                "seconds": 0,
                "control": m.control,
            }
        else:
            for f, o, n in m.edits:
                path = work / f
                path.write_text(path.read_text(encoding="utf-8").replace(o, n, 1), encoding="utf-8")
            status, first, dur = run_suite(work)
            rec = {
                "ident": ident,
                "status": status,
                "detail": first,
                "seconds": round(dur, 1),
                "control": m.control,
            }
            for path, text in originals.items():
                path.write_text(text, encoding="utf-8")
        with open(OUT, "a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        results.append(rec)
    shutil.rmtree(base, ignore_errors=True)
    return results


if __name__ == "__main__":
    done = set()
    if OUT.exists():
        done = {json.loads(line)["ident"] for line in OUT.read_text().splitlines() if line.strip()}
    todo = [m.ident for m in c.MUTANTS if m.ident not in done]
    chunks = [todo[i::WORKERS] for i in range(WORKERS)]
    with ProcessPoolExecutor(WORKERS) as ex:
        for res in ex.map(worker, chunks):
            print(json.dumps(res[0]))
