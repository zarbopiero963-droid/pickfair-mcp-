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
R = REG = "src/pickfair_mcp/tools/registry.py"
E = "src/pickfair_mcp/policy/exposure.py"
S = SRV = "src/pickfair_mcp/server.py"
APO = "src/pickfair_mcp/auth/policy.py"
PRI = "src/pickfair_mcp/auth/principal.py"
CLI = "src/pickfair_mcp/cli.py"
C = "src/pickfair_mcp/config.py"
A = "src/pickfair_mcp/audit.py"
ME = "src/pickfair_mcp/tools/meta.py"
J = "src/pickfair_mcp/journal/store.py"
JR = "src/pickfair_mcp/journal/retry.py"

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
        ((H, 'reasons.append("CAPABILITY_NOT_APPROVED")', "pass"),),
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
    Mutant(
        "M25",
        "verdetto precedente conservato dopo handshake interrotto",
        (
            (
                H,
                "        # (cancellazione o errore imprevisto): fail-closed.\n        self._last = None\n",
                "        # (cancellazione o errore imprevisto): fail-closed.\n",
            ),
        ),
    ),
    Mutant(
        "M26",
        "testo delle capability upstream riecheggiato al client",
        (
            (
                H,
                'reasons.append("CAPABILITY_NOT_APPROVED")',
                'reasons.extend(f"CAPABILITY_NOT_APPROVED:{c}" for c in sorted(advertised - approved))',
            ),
        ),
    ),
    Mutant(
        "M27",
        "log dell'SDK non silenziati su stderr",
        (
            (
                A,
                "    root.handlers[:] = [logging.NullHandler()]\n    root.setLevel(logging.CRITICAL + 1)\n",
                "",
            ),
        ),
    ),
    Mutant(
        "M28",
        "comandi annotati come sola lettura",
        ((S, "    is_read = ROUTES_BY_KEY[route].kind is RouteKind.READ", "    is_read = True"),),
    ),
    Mutant(
        "M29",
        "handshake esplicito riapre un epoch incompatibile",
        ((H, "and last.status is HandshakeStatus.INCOMPATIBLE:", "and False:"),),
    ),
    Mutant(
        "M30",
        "SIGINT perso classificato come errore di trasporto",
        (
            (
                "src/pickfair_mcp/cli.py",
                "                self.seen = True\n",
                "                pass\n",
            ),
        ),
    ),
    Mutant(
        "M31",
        "SIGINT ignorato dal processo padre riattivato",
        (
            (
                "src/pickfair_mcp/cli.py",
                "        if not callable(current):\n            return\n",
                "",
            ),
        ),
    ),
    Mutant(
        "M32",
        "gestore del Runner asyncio sostituito prima del loop",
        (
            (
                "src/pickfair_mcp/cli.py",
                "    tracker = InterruptTracker(_force_interrupted_exit)\n",
                "    tracker = InterruptTracker(_force_interrupted_exit)\n    tracker.install()\n",
            ),
        ),
    ),
    Mutant(
        "M33",
        "SIGINT a riposo attende EOF di stdin (watchdog non armato)",
        (("src/pickfair_mcp/cli.py", "                self._signalled.set()\n", ""),),
    ),
    Mutant(
        "M34",
        "watchdog lasciato armato dopo la chiusura regolare",
        (
            (
                "src/pickfair_mcp/cli.py",
                "        return EXIT_INTERRUPTED\n    tracker.disarm()\n",
                "        return EXIT_INTERRUPTED\n",
            ),
        ),
    ),
    Mutant(
        "M35",
        "watchdog scaduto senza uscita dal processo",
        (("src/pickfair_mcp/cli.py", "    os._exit(_abnormal_stop(", "    (_abnormal_stop("),),
    ),
    Mutant(
        "M36",
        "thread avviato dentro il gestore di SIGINT (rischio di deadlock)",
        (
            (
                "src/pickfair_mcp/cli.py",
                "                self._signalled.set()\n",
                "                self._signalled.set()\n"
                "                threading.Thread(target=self._finished.wait, daemon=True).start()\n",
            ),
        ),
    ),
    Mutant(
        "M37",
        "uscita interrupted di main tramite la finalizzazione dell'interprete",
        (
            (
                "src/pickfair_mcp/cli.py",
                "            tracker.stop_interrupted()  # non ritorna: il thread di stdin può essere ancora vivo\n            return EXIT_INTERRUPTED\n",
                '            return _abnormal_stop("interrupted", EXIT_INTERRUPTED)\n',
            ),
        ),
    ),
    Mutant(
        "M38",
        "chiusura interrupted eseguita più di una volta",
        (
            (
                "src/pickfair_mcp/cli.py",
                "            if not self._finished.is_set():\n                self._finished.set()\n                self._on_expire()\n",
                "            self._finished.set()\n            self._on_expire()\n",
            ),
        ),
    ),
    Mutant(
        "M39",
        "chiusura interrupted senza lock",
        (
            (
                "src/pickfair_mcp/cli.py",
                "        with self._lock:\n            if not self._finished.is_set():\n",
                "        if True:\n            if not self._finished.is_set():\n",
            ),
        ),
    ),
    Mutant(
        "M40",
        "disarm senza lock supera un'uscita in corso",
        (
            (
                "src/pickfair_mcp/cli.py",
                "        with self._lock:\n            self._finished.set()\n        self._signalled.set()",
                "        if True:\n            self._finished.set()\n        self._signalled.set()",
            ),
        ),
    ),
    Mutant(
        "M41",
        "margine del watchdog di un'ora",
        (("src/pickfair_mcp/cli.py", "INTERRUPT_GRACE_S = 2.0\n", "INTERRUPT_GRACE_S = 3600.0\n"),),
    ),
    Mutant(
        "M42",
        "SIGINT tardivo interrompe l'uscita interrupted",
        (
            (
                "src/pickfair_mcp/cli.py",
                "            signal.signal(signal.SIGINT, signal.SIG_IGN)\n        with self._lock:\n",
                "            pass\n        with self._lock:\n",
            ),
        ),
    ),
    Mutant(
        "M43",
        "SIGINT ignorato anche dal thread del watchdog",
        (
            (
                "src/pickfair_mcp/cli.py",
                "        if threading.current_thread() is threading.main_thread():\n",
                "        if True:\n",
            ),
        ),
    ),
    Mutant(
        "M44",
        "raffica di SIGINT: ogni segnale delegato al Runner",
        (
            (
                "src/pickfair_mcp/cli.py",
                "            else:\n                signal.signal(signal.SIGINT, signal.SIG_IGN)\n",
                "",
            ),
        ),
    ),
    Mutant(
        "M45",
        "a fine loop SIGINT ancora delegato al Runner",
        (("src/pickfair_mcp/cli.py", "        self._delegate = None\n", "        pass\n"),),
    ),
    Mutant(
        "M46",
        "SIGINT tardivo dopo una chiusura regolare termina con -2",
        (
            (
                "src/pickfair_mcp/cli.py",
                "    _ignore_late_sigint()\n    if tracker.seen:\n",
                "    if tracker.seen:\n",
            ),
        ),
    ),
    Mutant(
        "M47",
        "SIGINT tardivo dopo un errore di trasporto termina con -2",
        (
            (
                "src/pickfair_mcp/cli.py",
                "        _ignore_late_sigint()\n        if tracker.seen or",
                "        if tracker.seen or",
            ),
        ),
    ),
    Mutant(
        "M48",
        "server_start scritto prima che SIGINT sia gestito dal tracker",
        (
            (
                "src/pickfair_mcp/cli.py",
                "    tracker.install()  # prima di server_start: da quella riga SIGINT è sempre gestito (N4)\n",
                "",
            ),
            (
                "src/pickfair_mcp/cli.py",
                "        server = build_server(adapter,",
                "        tracker.install()\n        server = build_server(adapter,",
            ),
        ),
    ),
    # MCP-01b: journal, dedupe, fsync, lock, AMBIGUOUS
    Mutant(
        "J01",
        "deduplica disattivata: stessa chiave rimandata upstream",
        ((J, "        existing = self._by_key.get(kh)\n", "        existing = None\n"),),
    ),
    Mutant("J02", "fsync rimosso", ((J, "            os.fsync(fd)\n", "            pass\n"),)),
    Mutant(
        "J03", "lock esclusivo ignorato", ((J, "if not try_lock(self._lock_fd):", "if False:"),)
    ),
    Mutant(
        "J04",
        "risposta upstream non valida accettata invece di AMBIGUOUS",
        ((J, "        if _valid_ack(ack):\n", "        if ack is not None:\n"),),
    ),
    Mutant(
        "J05",
        "recovery chiude un invio come NOT_SENT (replay possibile)",
        (
            (
                J,
                "EntryStatus.AMBIGUOUS if entry.sent else EntryStatus.NOT_SENT",
                "EntryStatus.NOT_SENT",
            ),
        ),
    ),
    Mutant("J06", "checksum non verificato", ((J, "if crc != _crc(rec) or ", "if "),)),
    Mutant(
        "J07",
        "journal non scrivibile ma mutazione ammessa",
        (
            (J, "if fd is None or self.failure_reason is not None:", "if fd is None:"),
            (
                J,
                "        if not self.writable:\n            raise self._unavailable()\n        entry",
                "        entry",
            ),
        ),
    ),
    Mutant(
        "J08",
        "file del journal sostituito non rilevato",
        ((J, "if (st.st_dev, st.st_ino) != self._ino:", "if False:"),),
    ),
    Mutant(
        "J09",
        "timeout dell'invio non applicato",
        (
            (
                J,
                "                with anyio.fail_after(timeout_s):\n",
                "                if True:\n",
            ),
        ),
    ),
    Mutant(
        "J10",
        "voce AMBIGUOUS non persistita al recovery",
        (
            (
                J,
                "            if self.writable:\n                self._close_entry(closed)",
                "            if False:\n                self._close_entry(closed)",
            ),
        ),
    ),
    Mutant(
        "J11",
        "chiave logica scritta in chiaro nel journal",
        (
            (
                J,
                'return hashlib.sha256(b"pickfair-mcp:journal-key:v1\\x00" + key.encode()).hexdigest()',
                "return key",
            ),
        ),
    ),
    Mutant(
        "J12",
        "invio upstream senza voce sent persistita",
        (
            (
                J,
                "            entry = self.mark_sent(entry)\n",
                "            entry = replace(entry, sent=True)\n            self._entries[entry.request_id] = entry\n",
            ),
        ),
    ),
    Mutant(
        "J13",
        "retry di lettura senza limite",
        ((JR, "if not 1 <= attempts <= MAX_READ_ATTEMPTS:", "if False:"),),
    ),
    Mutant(
        "A01",
        "controllo di scope rimosso dal server",
        ((SRV, "authorize(self._principal, spec.name)", "pass"),),
    ),
    Mutant(
        "A02",
        "condizione di scope invertita",
        ((APO, "not in principal.scopes:", "in principal.scopes:"),),
    ),
    Mutant(
        "A03",
        "principal assente accettato",
        ((APO, 'raise AuthorizationDenied("PRINCIPAL_MISSING")', "return"),),
    ),
    Mutant(
        "A04",
        "principal non valido accettato",
        ((APO, 'raise AuthorizationDenied("PRINCIPAL_INVALID")', "pass"),),
    ),
    Mutant(
        "A05",
        "EMERGENCY non riservato all'owner",
        ((APO, "        return Scope.OWNER\n", "        return scope\n"),),
    ),
    Mutant(
        "A06",
        "set_mode declassato a write",
        ((APO, '"set_mode": Scope.OWNER', '"set_mode": Scope.WRITE'),),
    ),
    Mutant(
        "A07",
        "place_order declassato a read",
        ((APO, '"place_order": Scope.WRITE', '"place_order": Scope.READ'),),
    ),
    Mutant(
        "A08",
        "registrazione senza scope accettata",
        ((REG, 'raise RegistryViolation(f"SCOPE_UNDECLARED:{spec.name}")', "pass"),),
    ),
    Mutant(
        "A09",
        "scope dichiarato diverso dal catalogo accettato",
        ((REG, "if spec.scope is not declared:", "if False:"),),
    ),
    Mutant(
        "A10",
        "validazione input prima dell'autorizzazione",
        (
            (
                SRV,
                "            try:\n                authorize(self._principal, spec.name)\n"
                "            except AuthorizationDenied as denied:\n"
                "                raise denied.to_tool_error() from None\n"
                "            try:\n"
                "                spec.input_model.model_validate(arguments if arguments is not None else {})\n"
                "            except ValidationError:\n"
                '                raise ToolError(ErrorCode.INVALID_REQUEST, reasons=("INPUT_SCHEMA",)) from None\n',
                "            try:\n"
                "                spec.input_model.model_validate(arguments if arguments is not None else {})\n"
                "            except ValidationError:\n"
                '                raise ToolError(ErrorCode.INVALID_REQUEST, reasons=("INPUT_SCHEMA",)) from None\n'
                "            try:\n                authorize(self._principal, spec.name)\n"
                "            except AuthorizationDenied as denied:\n"
                "                raise denied.to_tool_error() from None\n",
            ),
        ),
    ),
    Mutant(
        "A11",
        "scope forgiati (stringhe) accettati",
        ((PRI, "and all(type(s) is Scope for s in scopes)", "and True"),),
    ),
    Mutant(
        "A12",
        "chiavi extra (credenziali) accettate nel principal",
        ((PRI, "or set(raw) != _PRINCIPAL_KEYS", "or not _PRINCIPAL_KEYS <= set(raw)"),),
    ),
    Mutant(
        "A13",
        "principal del processo stdio elevato a owner",
        ((CLI, "scopes=frozenset({Scope.READ})", "scopes=frozenset(Scope)"),),
    ),
    Mutant(
        "A14",
        "insieme di scope vuoto accettato",
        ((PRI, "and len(scopes) > 0", "and True"),),
    ),
    Mutant(
        "A15",
        "resume declassato a write (revoca stop EMERGENCY da non-owner)",
        ((APO, '"resume": Scope.OWNER', '"resume": Scope.WRITE'),),
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
    """'pass', 'fail', 'timeout' (suite bloccata = mutante rilevato) o 'error'."""
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
    # 0 = verde; 1 = test falliti; altri codici (collezione, uso) non provano nulla.
    return {0: "pass", 1: "fail"}.get(proc.returncode, "error")


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
            status = {"pass": "SURVIVED", "error": "ERROR"}.get(outcome, "KILLED")
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
