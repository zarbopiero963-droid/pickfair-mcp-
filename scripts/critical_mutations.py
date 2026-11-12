"""Mutation testing mirato sui controlli critici (catalogo deterministico).

Ogni mutante disattiva un controllo di sicurezza in una copia temporanea del
repository; la suite unit+integration deve fallire (mutante KILLED). Soglia: 100 %.
Un mutante che sopravvive indica un controllo non coperto dai test.

Uso: python scripts/critical_mutations.py [--json report.json] [--jobs N]

I mutanti girano in parallelo (``--jobs``, predefinito min(4, CPU)): ognuno nella propria copia,
con la propria suite; l'esito di ciascuno non dipende dagli altri. Il rapporto segue l'ordine del
catalogo.
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = (
    "src",
    "tests",
    "docs",
    "scripts",
    "ci",
    "catalog",
    "pyproject.toml",
    "AGENTS.md",
    ".guardrails",
    ".github",
)
TEST_ARGS = (
    "tests/unit",
    "tests/integration",
    "tests/contract",
    "tests/control_api",
    "tests/guards",
)


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
ST = "src/pickfair_mcp/tools/status.py"
HT = "src/pickfair_mcp/adapters/http.py"
TF = "src/pickfair_mcp/auth/token_file.py"
RT = "src/pickfair_mcp/journal/retry.py"
HS = "src/pickfair_mcp/policy/handshake.py"
CS = "src/pickfair_control_api/server.py"
CT = "src/pickfair_control_api/tokens.py"
CK = "src/pickfair_control_api/schema_check.py"
CC = "src/pickfair_control_api/contract.py"
FI = "src/pickfair_mcp/tools/finance.py"
TI = "src/pickfair_mcp/tools/__init__.py"

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
                "src/pickfair_mcp/server.py",
                "                validated = spec.input_model.model_validate(\n                    arguments if arguments is not None else {}\n                )\n",
                "                validated = spec.input_model.model_construct(**(arguments or {}))\n",
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
        "J03",
        "lock esclusivo ignorato",
        ((J, "if not lock.try_lock(self._lock_fd):", "if False:"),),
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
        "J20",
        "journal aperto su piattaforma senza protezioni (C-AUD-04: fallback più debole)",
        (
            (
                J,
                "        if not lock.PLATFORM_SUPPORTED:\n",
                "        if False:\n",
            ),
        ),
    ),
    Mutant(
        "J21",
        "win32 dichiarato supportato (C-AUD-04: reparse point seguiti)",
        (
            (
                "src/pickfair_mcp/journal/lock.py",
                'sys.platform != "win32" and _NOFOLLOW is not None',
                "_NOFOLLOW is not None",
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
                "src/pickfair_mcp/server.py",
                '            try:\n                authorize(self._principal, spec.name)\n            except AuthorizationDenied as denied:\n                raise denied.to_tool_error() from None\n            try:\n                validated = spec.input_model.model_validate(\n                    arguments if arguments is not None else {}\n                )\n            except ValidationError:\n                raise ToolError(ErrorCode.INVALID_REQUEST, reasons=("INPUT_SCHEMA",)) from None\n',
                '            try:\n                validated = spec.input_model.model_validate(\n                    arguments if arguments is not None else {}\n                )\n            except ValidationError:\n                raise ToolError(ErrorCode.INVALID_REQUEST, reasons=("INPUT_SCHEMA",)) from None\n            try:\n                authorize(self._principal, spec.name)\n            except AuthorizationDenied as denied:\n                raise denied.to_tool_error() from None\n',
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
    Mutant(
        "S01",
        "sorgente simulata accettata come core (o viceversa)",
        ((ST, "if snapshot.source != _expected_source(adapter):", "if False:"),),
    ),
    Mutant(
        "S02",
        "snapshot stantio o nel futuro accettato",
        ((ST, "if age > MAX_SNAPSHOT_AGE_S or age < -MAX_CLOCK_SKEW_S:", "if False:"),),
    ),
    Mutant(
        "S03",
        "capability della route non richiesta all'handshake",
        (
            (
                ST,
                'await guard.require_compatible(frozenset({"GET /v1/meta", route}))',
                'await guard.require_compatible(frozenset({"GET /v1/meta"}))',
            ),
        ),
    ),
    Mutant(
        "S04",
        "campo null non dichiarato in unavailable accettato",
        ((MO, 'raise ValueError("null field and unavailable list disagree")', "pass"),),
    ),
    Mutant(
        "S05",
        "ready con blocker accettato",
        ((MO, "if self.ready and self.blockers:", "if False:"),),
    ),
    Mutant(
        "S06",
        "ready e level incoerenti accettati",
        ((MO, 'if self.ready != (self.level == "READY"):', "if False:"),),
    ),
    Mutant(
        "S07",
        "codici a testo libero (injection) accettati",
        ((MO, 'CODE_PATTERN = r"^[A-Z][A-Z0-9_]{0,63}$"', 'CODE_PATTERN = r"^(?s:.){1,64}$"'),),
    ),
    Mutant(
        "S08",
        "sorgente libera accettata",
        ((MO, 'Source = Literal["core", "simulated"]', "Source = str"),),
    ),
    Mutant(
        "S09",
        "modalita diversa da SIM/LIVE accettata",
        ((MO, 'execution_mode: Literal["SIM", "LIVE"] | None', "execution_mode: str | None"),),
    ),
    Mutant(
        "S10",
        "retry di lettura oltre il limite",
        ((ST, "READ_ATTEMPTS: Final = 2", "READ_ATTEMPTS: Final = 5"),),
    ),
    Mutant(
        "S11",
        "riconciliazione NOT_RUN con esito accettata",
        ((MO, 'if self.state == "NOT_RUN" and (', "if False and ("),),
    ),
    Mutant(
        "S12",
        "blocker duplicati accettati",
        ((MO, 'raise ValueError("duplicate codes")', "pass"),),
    ),
    Mutant(
        "S13",
        "contatori negativi accettati",
        (
            (
                MO,
                "Count = Annotated[int, Field(ge=0, le=1_000_000)]",
                "Count = Annotated[int, Field(le=1_000_000)]",
            ),
        ),
    ),
    Mutant(
        "S14",
        "unavailable con nomi di campo arbitrari accettato",
        (
            (
                MO,
                "        tuple[StatusField, ...],\n        Field(max_length=len(STATUS_OPTIONAL_FIELDS)",
                "        tuple[str, ...],\n        Field(max_length=len(STATUS_OPTIONAL_FIELDS)",
            ),
        ),
    ),
    Mutant(
        "H01",
        "redirect 302 accettato come risposta",
        ((HT, "        if status != 200:", "        if status not in (200, 302):"),),
    ),
    Mutant(
        "H02",
        "content-type non verificato",
        ((HT, "        if content_type != EXPECTED_CONTENT_TYPE:", "        if False:"),),
    ),
    Mutant(
        "H03",
        "secondo 401 non classificato come credenziali rifiutate",
        (
            (
                HT,
                "            if status == 401:\n                raise UpstreamUnauthorized",
                "            if False:\n                raise UpstreamUnauthorized",
            ),
        ),
    ),
    Mutant(
        "H04",
        "token non riletto dopo 401 (rotazione non recuperata)",
        (
            (
                HT,
                "            fresh = self._current_token(reload=True)",
                "            fresh = self._current_token(reload=False)",
            ),
        ),
    ),
    Mutant(
        "H05",
        "guasto di trasporto senza nuovo handshake",
        (
            (
                HT,
                "        except (OSError, http.client.HTTPException):\n            self._bump()",
                "        except (OSError, http.client.HTTPException):\n            pass",
            ),
        ),
    ),
    Mutant(
        "H06",
        "corpo letto senza limite",
        ((HT, "            body = resp.read(self._max + 1)", "            body = resp.read()"),),
    ),
    Mutant(
        "H07",
        "destinazione diversa da 127.0.0.1",
        ((HT, 'LOOPBACK_HOST: Final = "127.0.0.1"', 'LOOPBACK_HOST: Final = "0.0.0.0"'),),
    ),
    Mutant(
        "H08",
        "file del token leggibile da altri accettato",
        ((TF, "            if info.st_mode & 0o077:", "            if False:"),),
    ),
    Mutant(
        "H09",
        "file del token di un altro utente accettato",
        ((TF, "            if info.st_uid != self._uid:", "            if False:"),),
    ),
    Mutant(
        "H10",
        "symlink seguito",
        (
            (
                TF,
                "        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC",
                "        flags = os.O_RDONLY | os.O_CLOEXEC",
            ),
        ),
    ),
    Mutant(
        "H11",
        "cartella del token scrivibile da altri accettata",
        ((TF, "        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):", "        if False:"),),
    ),
    Mutant(
        "H12",
        "token corto o alterato accettato",
        (
            (
                TF,
                'TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9_-]{43,128}$")',
                'TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,128}$")',
            ),
        ),
    ),
    Mutant(
        "H13",
        "adapter http mal configurato ripiega sul simulato",
        (
            (
                CLI,
                '        _usage_error("HTTP_ADAPTER_REQUIRES_PORT_AND_TOKEN_FILE")\n        return None',
                "        return SimulatedControlApiAdapter()",
            ),
        ),
    ),
    Mutant(
        "H14",
        "credenziali rifiutate trattate come indisponibilità ritentabile",
        (
            (
                RT,
                '            raise ToolError(\n                ErrorCode.UPSTREAM_UNAUTHORIZED, reasons=("UPSTREAM_UNAUTHORIZED",)\n            ) from None',
                "            last = ErrorCode.UPSTREAM_UNAVAILABLE",
            ),
        ),
    ),
    Mutant(
        "H15",
        "errore di protocollo all'handshake ignorato",
        (
            (
                HS,
                "        except UpstreamProtocolError as exc:\n            return self._invalid(epoch, exc.reason)",
                '        except UpstreamProtocolError:\n            return self._failed(epoch, ErrorCode.UPSTREAM_UNAVAILABLE, ("UPSTREAM_UNAVAILABLE",))',
            ),
        ),
    ),
    Mutant(
        "C01",
        "risposta del core inviata senza auto-verifica del contratto",
        (
            (
                "src/pickfair_control_api/server.py",
                "            validate(body, response_schema(schema_name))",
                "            response_schema(schema_name)",
            ),
        ),
    ),
    Mutant(
        "C02",
        "DNS inverso all'avvio del server",
        (
            (
                CS,
                "        socketserver.TCPServer.server_bind(self)",
                "        ThreadingHTTPServer.server_bind(self)",
            ),
        ),
    ),
    Mutant(
        "C03",
        "riavvio bloccato da TIME_WAIT",
        ((CS, '    allow_reuse_address = os.name == "posix"', "    allow_reuse_address = False"),),
    ),
    Mutant(
        "C04",
        "Host header arbitrario accettato",
        ((CS, '        if self.headers.get("Host") != app.expected_host:', "        if False:"),),
    ),
    Mutant(
        "C05",
        "rotazione senza doppia accettazione",
        (
            (
                "src/pickfair_control_api/tokens.py",
                "            self._valid = (old, new_bytes)",
                "            self._valid = (old,)",
            ),
        ),
    ),
    Mutant(
        "C06",
        "vecchio token non revocato dopo la rotazione",
        (
            (
                "src/pickfair_control_api/tokens.py",
                "            self._valid = (new_bytes,)\n            self.rotations += 1",
                "            self._valid = (old, new_bytes)\n            self.rotations += 1",
            ),
        ),
    ),
    Mutant(
        "C07",
        "confronto del token non esatto",
        (
            (
                CT,
                "            ok |= hmac.compare_digest(presented, candidate)",
                "            ok |= presented[:8] == candidate[:8]",
            ),
        ),
    ),
    Mutant(
        "C08",
        "a capo finale accettato dai pattern",
        ((CK, '        pattern = pattern[:-1] + r"\\Z"', "        pattern = pattern"),),
    ),
    Mutant(
        "C09",
        "parola chiave di schema sconosciuta ignorata",
        (
            (
                CK,
                '    if unknown:\n        raise SchemaUnsupported(",".join(sorted(unknown)))',
                '    if False:\n        raise SchemaUnsupported(",".join(sorted(unknown)))',
            ),
        ),
    ),
    Mutant(
        "C10",
        "booleano accettato come intero",
        (
            (
                CK,
                '    if expected == "integer":\n        return type(value) is int',
                '    if expected == "integer":\n        return isinstance(value, int)',
            ),
        ),
    ),
    Mutant(
        "C11",
        "null non dichiarato in unavailable accettato dal server",
        ((CK, "        if (value.get(name) is None) != (name in declared):", "        if False:"),),
    ),
    Mutant(
        "T01",
        "tavolo NOT_ARMED con importi SL/TP accettato",
        ((MO, '        if self.state == "NOT_ARMED" and has_amount:', "        if False:"),),
    ),
    Mutant(
        "T02",
        "tavolo ARMED senza importi SL/TP accettato",
        (
            (
                MO,
                '        if self.state in ("ARMED", "TRIGGERED") and not has_amount:',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "T03",
        "importo SL/TP negativo accettato",
        (
            (
                MO,
                'NON_NEGATIVE_DECIMAL_PATTERN = r"^(?:[1-9][0-9]{0,14}(?:\\.[0-9]{1,28})?|0(?:\\.[0-9]{1,28})?)$"',
                "NON_NEGATIVE_DECIMAL_PATTERN = DECIMAL_PATTERN",
            ),
        ),
    ),
    Mutant(
        "T04",
        "held in contrasto col dettaglio per esito accettato",
        ((MO, "        if held != self.held:", "        if False:"),),
    ),
    Mutant(
        "T05",
        "esiti di settlement duplicati accettati",
        (
            (
                MO,
                '        if len(set(outcomes)) != len(outcomes):\n            raise ValueError("duplicate outcome")',
                '        if False:\n            raise ValueError("duplicate outcome")',
            ),
        ),
    ),
    Mutant(
        "T06",
        "fasi del checkpoint duplicate accettate",
        (
            (
                MO,
                '        if len(set(stages)) != len(stages):\n            raise ValueError("duplicate stage")',
                '        if False:\n            raise ValueError("duplicate stage")',
            ),
        ),
    ),
    Mutant(
        "T07",
        "parte del settlement nulla non dichiarata accettata",
        (
            (
                MO,
                '        if tuple(values) != SETTLEMENT_OPTIONAL_FIELDS:\n            raise ValueError("optional field list out of sync")\n        _check_unavailable(values, self.unavailable)',
                '        if tuple(values) != SETTLEMENT_OPTIONAL_FIELDS:\n            raise ValueError("optional field list out of sync")',
            ),
        ),
    ),
    Mutant(
        "K01",
        "impostazione SET senza valore (o valore con NOT_SET/INVALID) accettata",
        (
            (
                MO,
                '        if (self.state == "SET") != (self._value() is not None):\n            raise ValueError("value present iff state is SET")',
                "        pass",
            ),
        ),
    ),
    Mutant(
        "K02",
        "chiave mancante, duplicata o fuori ordine accettata",
        (
            (
                MO,
                '        if tuple(s.key for s in self.settings) != tuple(CONFIG_KEYS):\n            raise ValueError("settings must list every contract key once, in contract order")',
                "        pass",
            ),
        ),
    ),
    Mutant(
        "K03",
        "tipo dell'impostazione diverso dal contratto accettato",
        (
            (
                MO,
                '            if s.kind != CONFIG_KEYS[s.key]:\n                raise ValueError("setting kind does not match the contract")',
                "            pass",
            ),
        ),
    ),
    Mutant(
        "K04",
        "campo obbligatorio presentato come NOT_SET accettato",
        (
            (
                MO,
                '            if s.state == "NOT_SET" and s.key not in OPTIONAL_CONFIG_KEYS:',
                "            if False:",
            ),
        ),
    ),
    Mutant(
        "K05",
        "nome sensibile accettato in unlisted",
        (
            (
                MO,
                '        if any(fragment in name for fragment in SENSITIVE_NAME_FRAGMENTS):\n            raise ValueError("sensitive field name must be redacted, not listed")',
                "        pass",
            ),
        ),
    ),
    Mutant(
        "K06",
        "chiave dell'allowlist ripetuta in unlisted accettata",
        (
            (
                MO,
                '        if name in CONFIG_KEYS:\n            raise ValueError("listed key reported as unlisted")',
                "        pass",
            ),
        ),
    ),
    Mutant(
        "K07",
        "impostazioni nulle senza dichiarazione in unavailable accettate",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        _check_unavailable(\n            {"settings": self.settings, "invalid_persisted": self.invalid_persisted},\n            self.unavailable,\n        )',
                "        pass",
            ),
        ),
    ),
    Mutant(
        "K08",
        "nomi duplicati in unlisted accettati",
        (
            (
                MO,
                '    if len(set(values)) != len(values):\n        raise ValueError("duplicate unlisted names")',
                "    pass",
            ),
        ),
    ),
    Mutant(
        "O12",
        "ordine AMBIGUOUS/PENDING con importi non confermati accettato",
        (
            (
                MO,
                "        if self.status in UNCONFIRMED_ORDER_STATUSES and (",
                "        if False and (",
            ),
        ),
    ),
    Mutant(
        "N01",
        "book di un altro mercato accettato per il mercato richiesto",
        (
            (
                "src/pickfair_mcp/tools/markets.py",
                "        if snapshot.market_id != market_id:",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "N02",
        "scala dei prezzi fuori ordine accettata",
        (
            (
                MO,
                "        if back != sorted(back, reverse=True) or lay != sorted(lay):",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "N03",
        "book presente con stato diverso da OK accettato",
        (
            (
                MO,
                '        if (self.book is not None) != (self.state == "OK"):',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "N04",
        "mercati non ordinati o duplicati accettati",
        (
            (
                MO,
                '    if ids != sorted(ids):\n        raise ValueError("markets must be sorted by market_id")',
                "    pass",
            ),
        ),
    ),
    Mutant(
        "N05",
        "percorso del book costruito da un id non validato",
        (
            (
                "src/pickfair_mcp/adapters/http.py",
                "        if not isinstance(market_id, str) or not _MARKET_ID_RE.fullmatch(market_id):",
                "        if not isinstance(market_id, str):",
            ),
        ),
    ),
    Mutant(
        "N06",
        "id del mercato non validato dalla Control API",
        (
            (
                "src/pickfair_control_api/contract.py",
                '    "/v1/markets/{id}/book": re.compile(r"\\A/v1/markets/(?P<id>[0-9]{1,4}\\.[0-9]{1,15})/book\\Z"),',
                '    "/v1/markets/{id}/book": re.compile(r"\\A/v1/markets/(?P<id>[^/]+)/book\\Z"),',
            ),
        ),
    ),
    Mutant(
        "X01",
        "token corto o fuori alfabeto accettato",
        (
            (
                "src/pickfair_control_api/tokens.py",
                "    if (\n        not isinstance(token, str)\n        or not MIN_TOKEN_CHARS <= len(token) <= MAX_TOKEN_CHARS\n        or not _TOKEN_RE.fullmatch(token)\n    ):",
                "    if not isinstance(token, str):",
            ),
        ),
    ),
    Mutant(
        "X02",
        "rotazioni concorrenti non serializzate",
        (
            (
                "src/pickfair_control_api/tokens.py",
                "        with self._rotation_lock:\n            return self._rotate_serialized(path)",
                "        return self._rotate_serialized(path)",
            ),
        ),
    ),
    Mutant(
        "X03",
        "connessioni oltre il tetto servite",
        (
            (
                "src/pickfair_control_api/server.py",
                "        if not self._slots.acquire(blocking=False):",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "X04",
        "connessione senza scadenza complessiva",
        (
            (
                "src/pickfair_control_api/server.py",
                "        self._deadline.start()",
                "        pass",
            ),
        ),
    ),
    Mutant(
        "X05",
        "errore di protocollo con il testo ricevuto",
        (
            (
                "src/pickfair_control_api/server.py",
                '        status, error = _PROTOCOL_ERRORS.get(code, (400, "BAD_REQUEST"))\n        try:\n            self._error(status, error)\n        except OSError:\n            self.close_connection = True',
                "        super().send_error(code, message, explain)",
            ),
        ),
    ),
    Mutant(
        "X06",
        "traceback per richiesta su stderr",
        (
            (
                "src/pickfair_control_api/server.py",
                '        logger.debug("control_api: connessione chiusa con errore")',
                "        super().handle_error(request, client_address)",
            ),
        ),
    ),
    Mutant(
        "L01",
        "esposizione residua senza il tavolo che porta la posizione accettata",
        (
            (
                MO,
                '        if (self.residual_exposure is not None) != (self.residual_source == "TABLE"):',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "L02",
        "chiusura non NOT_EXECUTED dichiarata ritentabile accettata",
        (
            (
                MO,
                '        if self.retryable and self.close_state != "NOT_EXECUTED":',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "L03",
        "chiusura rivendicata senza betId della posizione accettata",
        (
            (
                MO,
                '        if self.close_state in ("ROUTED", "CLAIMED", "UNCERTAIN") and not self.bet_ids:',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "L04",
        "betId duplicati nella chiusura accettati",
        (
            (
                MO,
                '        if len(set(self.bet_ids)) != len(self.bet_ids):\n            raise ValueError("duplicate bet ids")',
                "        pass",
            ),
        ),
    ),
    Mutant(
        "L05",
        "contatori della posizione oltre gli ordini letti accettati",
        (
            (
                MO,
                "        if max(self.partially_matched, self.in_reconciliation, self.ambiguous) > self.orders:",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "L06",
        "elenco delle chiusure OK con omissioni accettato",
        (
            (
                MO,
                '        if self.state == "OK" and (self.reason or self.omitted or self.truncated):\n            raise ValueError("OK closes with omissions or a reason")',
                "        pass",
            ),
        ),
    ),
    Mutant(
        "L07",
        "più righe d'hedge mancanti che richieste accettate",
        (
            (
                MO,
                "        if self.not_in_ledger > self.requests:",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "L08",
        "righe d'hedge senza richiesta registrata accettate",
        (
            (
                MO,
                "        if self.requests == 0 and (\n            self.pending or self.placed",
                "        if False and (\n            self.pending or self.placed",
            ),
        ),
    ),
    Mutant(
        "Y01",
        "picco senza fonte (o fonte senza picco) accettato",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if (self.peak_source == "NONE") == has_peak:',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "Y02",
        "trailing attivo senza percentuale accettato",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if self.state in ("WAITING_PROFIT", "ARMED", "TRIGGERED") and self.pct is None:',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "Y03",
        "trailing OFF con percentuale valida accettato",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if self.state == "OFF" and self.pct is not None:',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "Y04",
        "trailing ARMED senza picco o soglia accettato",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if self.state == "ARMED" and (not has_peak or self.threshold is None):',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "Y05",
        "soglia sopra il picco accettata",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                "            and Decimal(self.threshold) > Decimal(self.peak)",
                "            and False",
            ),
        ),
    ),
    Mutant(
        "Y06",
        "nome sensibile accettato fra le impostazioni non valide",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                "        if any(fragment in bare for fragment in SENSITIVE_NAME_FRAGMENTS):",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "Y07",
        "SHA del codice non risolto nei git worktree",
        (
            (
                "src/pickfair_control_api/contract.py",
                "        ref_file = git / ref if (git / ref).is_file() else common / ref",
                "        ref_file = git / ref",
            ),
        ),
    ),
    Mutant(
        "Z01",
        "età del mercato negativa o non decimale accettata",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                "    # MCP-01n: età (s) dell'ultimo book ricevuto (istante monotono del tracker, Claude D);\n    # null se ignota.\n    book_age_s: NonNegativeDecimal | None",
                "    # MCP-01n: età (s) dell'ultimo book ricevuto (istante monotono del tracker, Claude D);\n    # null se ignota.\n    book_age_s: str | None",
            ),
        ),
    ),
    Mutant(
        "Z02",
        "età del book negativa o non decimale accettata",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                "    omitted_runners: Count\n    book_age_s: NonNegativeDecimal | None",
                "    omitted_runners: Count\n    book_age_s: str | None",
            ),
        ),
    ),
    Mutant(
        "Z03",
        "età del mercato assente trattata come nota (default)",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                "    # MCP-01n: età (s) dell'ultimo book ricevuto (istante monotono del tracker, Claude D);\n    # null se ignota.\n    book_age_s: NonNegativeDecimal | None",
                '    # MCP-01n: età (s) dell\'ultimo book ricevuto (istante monotono del tracker, Claude D);\n    # null se ignota.\n    book_age_s: NonNegativeDecimal | None = "0"',
            ),
        ),
    ),
    Mutant(
        "Z04",
        "età del book assente trattata come nota (default)",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                "    omitted_runners: Count\n    book_age_s: NonNegativeDecimal | None",
                '    omitted_runners: Count\n    book_age_s: NonNegativeDecimal | None = "0"',
            ),
        ),
    ),
    Mutant(
        "B01",
        "richiesta non registrata servita comunque (registra o rifiuta)",
        (
            (
                "src/pickfair_control_api/server.py",
                '            if route not in UNRECORDED_ALLOWED_ROUTES:\n                return self._error(503, "BLACKBOX_UNAVAILABLE")',
                '            if False:\n                return self._error(503, "BLACKBOX_UNAVAILABLE")',
            ),
        ),
    ),
    Mutant(
        "B02",
        "server avviato senza hook di registrazione",
        (
            (
                "src/pickfair_control_api/server.py",
                "        if not callable(request_hook):",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "B03",
        "parametro sconosciuto della query accettato",
        (
            (
                "src/pickfair_control_api/blackbox_query.py",
                "        if not sep or name not in ALLOWED:",
                "        if not sep:",
            ),
        ),
    ),
    Mutant(
        "B04",
        "parametro ripetuto accettato",
        (
            (
                "src/pickfair_control_api/blackbox_query.py",
                '        if name in seen:\n            raise QueryRejected("QUERY_PARAM_REPEATED")',
                '        if False:\n            raise QueryRejected("QUERY_PARAM_REPEATED")',
            ),
        ),
    ),
    Mutant(
        "B05",
        "intervallo oltre 31 giorni accettato",
        (
            (
                "src/pickfair_control_api/blackbox_query.py",
                "        if (until - since).total_seconds() > MAX_RANGE_DAYS * 86400:",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "B06",
        "seconda redazione assente sul server",
        (
            (
                "src/pickfair_control_api/server.py",
                "            body = redact_response(body)",
                "            pass",
            ),
        ),
    ),
    Mutant(
        "B07",
        "un tentativo mostrato come esito confermato",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if self.phase == "ATTEMPT" and self.outcome != "PENDING":',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "B08",
        "valore sensibile non redatto accettato dal modello",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                "            if _is_sensitive_name(name) and value != BLACKBOX_REDACTED:",
                "            if False:",
            ),
        ),
    ),
    Mutant(
        "B09",
        "query fuori whitelist costruita dall'adapter HTTP",
        (
            (
                "src/pickfair_mcp/adapters/http.py",
                "            if name not in _BLACKBOX_PARAMS or not _BLACKBOX_VALUE_RE.fullmatch(value):",
                "            if False:",
            ),
        ),
    ),
    Mutant(
        "B10",
        "risposta 503 trattata come dato valido dall'adapter",
        (
            (
                "src/pickfair_mcp/adapters/http.py",
                "        if status == 503:\n            # PF-BLACKBOX-01: il core non ha potuto registrare la richiesta e non ha dato dati.\n            raise UpstreamUnavailable",
                "        if False:\n            raise UpstreamUnavailable",
            ),
        ),
    ),
    Mutant(
        "B11",
        "catena causale non verificata",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '            if link.event_id != expected:\n                raise ValueError("chain does not follow causation_id")',
                '            if False:\n                raise ValueError("chain does not follow causation_id")',
            ),
        ),
    ),
    Mutant(
        "B12",
        "cursore ignorato dal core non rilevato",
        (
            (
                "src/pickfair_mcp/tools/blackbox.py",
                "            e.seq <= args.after_seq for e in snapshot.events or ()",
                "            False for e in snapshot.events or ()",
            ),
        ),
    ),
    Mutant(
        "B13",
        "una richiesta per evento letto invece che per richiesta (ricorsione)",
        (
            (
                "src/pickfair_control_api/server.py",
                '        self._record_result(200, "OK")\n',
                '        for _ in (body.get("events") or [None]) if isinstance(body, dict) else [None]:\n            self._record_result(200, "OK")\n',
            ),
        ),
    ),
    Mutant(
        "B14",
        "query ammessa anche sulle altre route",
        (
            (
                "src/pickfair_control_api/server.py",
                "        if route is None and path_part in QUERY_ROUTE_SCHEMAS:",
                '        if route is None and "?" in raw_path:',
            ),
        ),
    ),
    Mutant(
        "P01",
        "chiusure SL/TP OK con righe omesse accettate",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if self.state == "OK" and (self.reason or self.omitted or self.truncated):\n            raise ValueError("OK closes with omissions or a reason")',
                '        if self.state == "OK" and self.reason:\n            raise ValueError("OK closes with omissions or a reason")',
            ),
        ),
    ),
    Mutant(
        "P02",
        "chiusure SL/TP PARTIAL senza dire cosa manca accettate",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if self.state == "PARTIAL" and not (self.reason and (self.omitted or self.truncated)):\n            raise ValueError("PARTIAL closes must say what is missing")',
                '        if False:\n            raise ValueError("PARTIAL closes must say what is missing")',
            ),
        ),
    ),
    Mutant(
        "P03",
        "chiusure SL/TP non lette senza motivo accettate",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                'class SlTpClosesMissing(StrictModel):\n    """UNAVAILABLE (core senza F-04: CORE_PENDING_F04, o DB illeggibile) o UNKNOWN (DB occupato)."""\n\n    state: Literal["UNKNOWN", "UNAVAILABLE"]\n    reason: Code\n',
                'class SlTpClosesMissing(StrictModel):\n    """UNAVAILABLE (core senza F-04: CORE_PENDING_F04, o DB illeggibile) o UNKNOWN (DB occupato)."""\n\n    state: Literal["UNKNOWN", "UNAVAILABLE"]\n    reason: Code | None\n',
            ),
        ),
    ),
    Mutant(
        "R01",
        "order_ref (customer_order_ref) esposto nella vista",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '        "bet_id": _opt(record, "bet_id", _BET),',
                '        "bet_id": _opt(record, "bet_id", _BET),\n        "order_ref": record.get("order_ref"),',
            ),
        ),
    ),
    Mutant(
        "R02",
        "record non mappabile saltato in silenzio invece che lacuna CORRUPT",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '                corrupt.append({"from_seq": seq, "to_seq": seq, "kind": "CORRUPT"})',
                "                continue",
            ),
        ),
    ),
    Mutant(
        "R03",
        "campo assente non dichiarato in not_recorded",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "            not_recorded.append(name)\n            continue",
                "            continue",
            ),
        ),
    ),
    Mutant(
        "R04",
        "hook accettato con una risposta solo truthy",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "        return reader.request_hook(dict(record)) is True",
                "        return bool(reader.request_hook(dict(record)))",
            ),
        ),
    ),
    Mutant(
        "R05",
        "filtri passati al motore con i nomi della vista",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "        out[FILTER_NAMES.get(name, name)] = value",
                "        out[name] = value",
            ),
        ),
    ),
    Mutant(
        "R06",
        "handshake /v1/meta rifiutato con il registro guasto (stato irraggiungibile via MCP)",
        (
            (
                "src/pickfair_control_api/contract.py",
                'UNRECORDED_ALLOWED_ROUTES: Final = frozenset({BLACKBOX_STATUS_ROUTE, "/v1/meta"})',
                "UNRECORDED_ALLOWED_ROUTES: Final = frozenset({BLACKBOX_STATUS_ROUTE})",
            ),
        ),
    ),
    Mutant(
        "R07",
        "tentativo non PENDING accettato dall'adapter",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '    if phase == "ATTEMPT" and outcome != "PENDING":',
                "    if False:",
            ),
        ),
    ),
    Mutant(
        "R08",
        "voci non rappresentabili non contate",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "            if not ok or not _NAME.fullmatch(name) or len(out) >= MAX_VALUES:\n                omitted += 1",
                "            if not ok or not _NAME.fullmatch(name) or len(out) >= MAX_VALUES:\n                pass",
            ),
        ),
    ),
    Mutant(
        "R09",
        "tempo esteso con le cifre sbagliate invece che troncato al ms",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "    return f\"{m.group(1)}.{(m.group(2) or '').ljust(3, '0')[:3]}Z\"",
                "    return f\"{m.group(1)}.{(m.group(2) or '').ljust(3, '0')[-3:]}Z\"",
            ),
        ),
    ),
    Mutant(
        "R10",
        "ora non UTC accettata",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '_TS = re.compile(r"\\A(\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2})(?:\\.(\\d{1,9}))?(?:Z|\\+00:00)\\Z")',
                '_TS = re.compile(r"\\A(\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2})(?:\\.(\\d{1,9}))?(?:Z|[+-]\\d{2}:\\d{2})\\Z")',
            ),
        ),
    ),
    Mutant(
        "R11",
        "id di BB-1 passati al lettore come interi (pagina vuota muta)",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "        elif name in _TEXT_IDS:",
                "        elif False:",
            ),
        ),
    ),
    Mutant(
        "R12",
        "lacune per tempo di BB-1 nascoste: pagina mostrata come completa",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '        windows = sorted((unrecorded_window(w) for w in raw_windows), key=lambda w: w["seq"])',
                "        windows = []",
            ),
        ),
    ),
    Mutant(
        "R13",
        "lettura della vista interna di BB-1 (external non richiesto)",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "        page = reader.query(engine, after_seq, limit, external=True)",
                "        page = reader.query(engine, after_seq, limit, external=False)",
            ),
        ),
    ),
    Mutant(
        "R14",
        "alias dell'ordine troncato accettato come filtro (il lettore non lo troverebbe)",
        (
            (
                "src/pickfair_control_api/blackbox_query.py",
                '_ORDER_ALIAS: Final = r"ord_[0-9a-f]{32}"',
                '_ORDER_ALIAS: Final = r"ord_[0-9a-f]{1,32}"',
            ),
        ),
    ),
    Mutant(
        "R15",
        "lacune non riportate dal motore mostrate come «nessuna lacuna»",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '    "retention_days",\n    "gaps",\n    "degraded",',
                '    "retention_days",\n    "degraded",',
            ),
        ),
    ),
    Mutant(
        "R16",
        "get senza causation_chain mostrato con una catena vuota",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '            raw_chain = got.get("causation_chain")',
                '            raw_chain = got.get("causation_chain") or []',
            ),
        ),
    ),
    Mutant(
        "R17",
        "not_recorded del motore ignorato (campo non registrato mostrato «non applicabile»)",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "        if source_name not in record or source_name in engine_not_recorded:",
                "        if source_name not in record:",
            ),
        ),
    ),
    Mutant(
        "R18",
        "valore nascosto da un not_recorded del motore",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "        if name not in _NULLABLE_COLUMNS or record.get(name) is not None:",
                "        if name not in _NULLABLE_COLUMNS:",
            ),
        ),
    ),
    Mutant(
        "R19",
        "finestra non registrata con un esito diverso da UNKNOWN accettata",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '    if type(seq) is not int or seq < 1 or outcome != "UNKNOWN":',
                "    if type(seq) is not int or seq < 1:",
            ),
        ),
    ),
    Mutant(
        "R20",
        "registro degradato mostrato disponibile",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '    available = runtime and raw.get("ok") is True and degraded is False',
                '    available = runtime and raw.get("ok") is True',
            ),
        ),
    ),
    Mutant(
        "R21",
        "sessione crashata mostrata in corso",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '        end_reason = "RUNNING" if session == current else "CRASH_DETECTED"',
                '        end_reason = "RUNNING"',
            ),
        ),
    ),
    Mutant(
        "R22",
        "ora di fine inventata per un crash",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '        "ended_at": last_event_at if end_reason == "CLEAN_STOP" else None,',
                '        "ended_at": last_event_at,',
            ),
        ),
    ),
    Mutant(
        "R23",
        "reason_code di un'eccezione (KeyError) reso record CORRUPT",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '            view[name] = _opt(record, "reason_code", _REASON)',
                '            view[name] = _opt(record, "reason_code", _UPPER)',
            ),
        ),
    ),
    Mutant(
        "R24",
        "id interno dell'ordine (ledger) mostrato nella vista invece dell'alias",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '_ORDER_ALIAS = re.compile(r"\\Aord_[0-9a-f]{32}\\Z")',
                '_ORDER_ALIAS = re.compile(r"\\A(?:ord_[0-9a-f]{32}|[0-9]+)\\Z")',
            ),
        ),
    ),
    Mutant(
        "R25",
        "ora dichiarata dall'exchange persa",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "            view[name] = None if value is None else ts_ms(value)",
                "            view[name] = None",
            ),
        ),
    ),
    Mutant(
        "R26",
        "catena chiesta oltre il limite di BB-1 (ogni get_blackbox_event fallirebbe)",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                "MAX_CHAIN: Final = 20",
                "MAX_CHAIN: Final = 32",
            ),
        ),
    ),
    Mutant(
        "R27",
        "salute di un lettore READER_LOCAL mostrata come quella del runtime",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '    runtime = raw.get("health_scope") == "RUNTIME"',
                "    runtime = True",
            ),
        ),
    ),
    Mutant(
        "R28",
        "sessione del lettore presa per la sessione corrente del runtime (falso crash)",
        (
            (
                "src/pickfair_control_api/blackbox_bridge.py",
                '        current = st.get("session_id") if st.get("health_scope") == "RUNTIME" else None',
                '        current = st.get("session_id")',
            ),
        ),
    ),
    Mutant(
        "R29",
        "sorgente assente ripiega sui dati simulati (default implicito, C-AUD-10)",
        (
            (
                "src/pickfair_mcp/cli.py",
                '        default=None,\n        help="sorgente dati, obbligatoria',
                '        default="simulated",\n        help="sorgente dati, obbligatoria',
            ),
        ),
    ),
    Mutant(
        "R30",
        "controllo della sorgente obbligatoria rimosso (C-AUD-10)",
        (
            (
                "src/pickfair_mcp/cli.py",
                '    if args.adapter is None:\n        _usage_error("SOURCE_REQUIRED")\n        return None\n',
                "",
            ),
        ),
    ),
    Mutant(
        "R31",
        "gettone non scalato all'ammissione (C-AUD-06)",
        (
            (
                "src/pickfair_control_api/rate_limit.py",
                "                self._store(key, tokens - 1.0, now)\n",
                "                self._store(key, tokens, now)\n",
            ),
        ),
    ),
    Mutant(
        "R32",
        "controllo e scalata fuori dallo stesso lock (C-AUD-06: race)",
        (
            (
                "src/pickfair_control_api/rate_limit.py",
                "        with self._lock:\n            now = self._clock()\n            tokens, at = self._buckets.get(key, (self._burst, now))\n            tokens = min(self._burst, tokens + max(0.0, now - at) * self._rate)\n            if tokens >= 1.0:\n",
                "        with self._lock:\n            now = self._clock()\n            tokens, at = self._buckets.get(key, (self._burst, now))\n            tokens = min(self._burst, tokens + max(0.0, now - at) * self._rate)\n        time.sleep(0.001)\n        with self._lock:\n            if tokens >= 1.0:\n",
            ),
        ),
    ),
    Mutant(
        "R33",
        "ricarico oltre la raffica (C-AUD-06)",
        (
            (
                "src/pickfair_control_api/rate_limit.py",
                "            tokens = min(self._burst, tokens + max(0.0, now - at) * self._rate)\n            if tokens >= 1.0:",
                "            tokens = tokens + max(0.0, now - at) * self._rate\n            if tokens >= 1.0:",
            ),
        ),
    ),
    Mutant(
        "R34",
        "limite non applicato prima del core (C-AUD-06)",
        (
            (
                "src/pickfair_control_api/server.py",
                "        if wait is not None:\n            return self._reject_rate_limited(wait)\n",
                "        if False:\n            return self._reject_rate_limited(wait)\n",
            ),
        ),
    ),
    Mutant(
        "R35",
        "rifiuto non contato nella finestra della scatola nera (C-AUD-06)",
        (
            (
                "src/pickfair_control_api/server.py",
                "        app.rejections.note()\n",
                "",
            ),
        ),
    ),
    Mutant(
        "R36",
        "audit dei rifiuti fallito in silenzio (C-AUD-06)",
        (
            (
                "src/pickfair_control_api/rate_limit.py",
                '            self._add_unrecorded(int(window["rejected_count"]))\n',
                "            pass\n",
            ),
        ),
    ),
    Mutant(
        "R37",
        "429 trattato come indisponibilità e quindi ritentato (C-AUD-06)",
        (
            (
                "src/pickfair_mcp/adapters/http.py",
                "            raise UpstreamRateLimited\n",
                "            raise UpstreamUnavailable\n",
            ),
        ),
    ),
    Mutant(
        "R38",
        "errori di protocollo in stile HTTP/0.9 senza stato né header (Python < 3.13)",
        (
            (
                "src/pickfair_control_api/server.py",
                '    default_request_version = "HTTP/1.0"\n',
                "",
            ),
        ),
    ),
    Mutant(
        "O01",
        "ordine AMBIGUOUS accettato come FAILED",
        (
            (
                MO,
                '    "AMBIGUOUS": ("AMBIGUOUS",),\n    "HEDGE_AMBIGUOUS": ("AMBIGUOUS",),\n}',
                '    "AMBIGUOUS": ("AMBIGUOUS", "FAILED"),\n    "HEDGE_AMBIGUOUS": ("AMBIGUOUS",),\n}',
            ),
        ),
    ),
    Mutant(
        "O02",
        "stato del core sconosciuto accettato con qualunque stato",
        (
            (
                MO,
                '        if self.status not in ORDER_STATUS_MAP.get(self.core_status, ("UNKNOWN",)):',
                "        if self.core_status in ORDER_STATUS_MAP and self.status not in ORDER_STATUS_MAP[self.core_status]:",
            ),
        ),
    ),
    Mutant(
        "O03",
        "abbinamento dichiarato senza quantità esplicite",
        (
            (
                MO,
                '            if self.size_matched is None or self.size_remaining is None:\n                raise ValueError("matched split without explicit sizes")',
                "            if self.size_matched is None or self.size_remaining is None:\n                return self",
            ),
        ),
    ),
    Mutant(
        "O04",
        "abbinamento in contrasto con le quantità accettato",
        (
            (
                MO,
                '            if self.status != expected:\n                raise ValueError("matched split disagrees with the sizes")',
                '            if False:\n                raise ValueError("matched split disagrees with the sizes")',
            ),
        ),
    ),
    Mutant(
        "O05",
        "confronto col broker senza betId accettato",
        (
            (
                MO,
                '        if self.broker_view != "NOT_CHECKED" and self.bet_id is None:',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "O06",
        "ordini duplicati accettati",
        ((MO, '        raise ValueError("duplicate local_id")', "        pass"),),
    ),
    Mutant(
        "O07",
        "snapshot OK con righe omesse accettato",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if self.state == "OK" and (self.reason or self.omitted or self.truncated):\n            raise ValueError("OK snapshot with omissions or a reason")',
                '        if self.state == "OK" and self.reason:\n            raise ValueError("OK snapshot with omissions or a reason")',
            ),
        ),
    ),
    Mutant(
        "O08",
        "snapshot PARTIAL senza dire cosa manca accettato",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                '        if self.state == "PARTIAL" and not (self.reason and (self.omitted or self.truncated)):\n            raise ValueError("PARTIAL snapshot must say what is missing")',
                '        if False:\n            raise ValueError("PARTIAL snapshot must say what is missing")',
            ),
        ),
    ),
    Mutant(
        "O09",
        "list_orders legge la route sbagliata",
        (
            (
                FI,
                "            read=adapter.get_orders_raw,",
                "            read=adapter.get_positions_raw,",
            ),
        ),
    ),
    Mutant(
        "O10",
        "valore d'ordine nullo non dichiarato accettato",
        (
            (
                MO,
                '        if tuple(values) != ORDER_OPTIONAL_FIELDS:\n            raise ValueError("optional field list out of sync")\n        _check_unavailable(values, self.unavailable)',
                '        if tuple(values) != ORDER_OPTIONAL_FIELDS:\n            raise ValueError("optional field list out of sync")',
            ),
        ),
    ),
    Mutant(
        "O11",
        "snapshot non letto senza motivo accettato",
        (
            (
                "src/pickfair_mcp/contract/models.py",
                'class OrdersSnapshotMissing(StrictModel):\n    """Lettura non riuscita: UNKNOWN (database occupato) o UNAVAILABLE (non leggibile)."""\n\n    state: Literal["UNKNOWN", "UNAVAILABLE"]\n    reason: Code\n',
                'class OrdersSnapshotMissing(StrictModel):\n    """Lettura non riuscita: UNKNOWN (database occupato) o UNAVAILABLE (non leggibile)."""\n\n    state: Literal["UNKNOWN", "UNAVAILABLE"]\n    reason: Code | None\n',
            ),
        ),
    ),
    Mutant(
        "G01",
        "protezione ACTIVE con un motivo accettata (stato non verificato mascherato)",
        (
            (
                MO,
                '    state: Literal["ACTIVE"]\n    reason: None',
                '    state: Literal["ACTIVE"]\n    reason: Code | None',
            ),
        ),
    ),
    Mutant(
        "G02",
        "protezione non verificabile senza motivo accettata",
        (
            (
                MO,
                '    state: Literal["INACTIVE", "TRIGGERED", "UNKNOWN", "UNAVAILABLE"]\n    reason: Code',
                '    state: Literal["INACTIVE", "TRIGGERED", "UNKNOWN", "UNAVAILABLE"]\n    reason: Code | None',
            ),
        ),
    ),
    Mutant(
        "G03",
        "elenchi derivati disabled/unverifiable non controllati",
        (
            (
                MO,
                "        if list(self.disabled) != disabled or list(self.unverifiable) != unverifiable:",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "G04",
        "UNAVAILABLE omesso dalle protezioni non verificabili",
        (
            (
                MO,
                '        unverifiable = sorted(n for n, s in states.items() if s in ("UNKNOWN", "UNAVAILABLE"))',
                '        unverifiable = sorted(n for n, s in states.items() if s == "UNKNOWN")',
            ),
        ),
    ),
    Mutant(
        "G05",
        "notazione esponenziale accettata negli importi Decimal",
        (
            (
                MO,
                '    r"|0(?:\\.[0-9]{1,28})?"',
                '    r"|0(?:\\.[0-9]{1,28})?|[0-9.]+[eE][-+]?[0-9]+"',
            ),
        ),
    ),
    Mutant(
        "G06",
        "posizione FLAT con esposizione accettata",
        (
            (
                MO,
                '        if self.side == "FLAT" and self.exposure not in (None, "0"):',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "G07",
        "importo di posizione nullo non dichiarato accettato",
        (
            (
                MO,
                '        if tuple(values) != POSITION_OPTIONAL_FIELDS:\n            raise ValueError("optional field list out of sync")\n        _check_unavailable(values, self.unavailable)',
                '        if tuple(values) != POSITION_OPTIONAL_FIELDS:\n            raise ValueError("optional field list out of sync")',
            ),
        ),
    ),
    Mutant(
        "G08",
        "motore READY con un componente non pronto accettato",
        (
            (
                MO,
                '        if self.state == "READY" and any(c.state != "READY" for c in self.components):',
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "G09",
        "modalità READ_ONLY inventata accettata",
        (
            (
                MO,
                '    read_only_mode: Literal["NOT_IN_CORE"]',
                "    read_only_mode: str",
            ),
        ),
    ),
    Mutant(
        "G10",
        "list_positions legge la route sbagliata",
        (
            (
                FI,
                "            read=adapter.get_positions_raw,",
                "            read=adapter.get_exposure_raw,",
            ),
        ),
    ),
    Mutant(
        "G11",
        "sezione diagnostica nulla non dichiarata accettata",
        (
            (
                MO,
                '        if tuple(values) != ENGINE_OPTIONAL_FIELDS:\n            raise ValueError("optional field list out of sync")\n        _check_unavailable(values, self.unavailable)',
                '        if tuple(values) != ENGINE_OPTIONAL_FIELDS:\n            raise ValueError("optional field list out of sync")',
            ),
        ),
    ),
    Mutant(
        "F01",
        "cassa verificata senza importo (o viceversa) accettata",
        (
            (
                MO,
                "        if self.verified != (self.cash_equity is not None):\n"
                '            raise ValueError("verified and cash_equity disagree")',
                "        if False:\n"
                '            raise ValueError("verified and cash_equity disagree")',
            ),
        ),
    ),
    Mutant(
        "F02",
        "fondi non verificabili senza motivo accettati",
        (
            (
                MO,
                "        if self.ok == (self.reason is not None):",
                "        if self.ok and self.reason is not None:",
            ),
        ),
    ),
    Mutant(
        "F03",
        "desk mode senza il bankroll da cui deriva",
        (
            (
                MO,
                "        if self.desk_mode is not None and self.bankroll is None:",
                "        if False:",
            ),
        ),
    ),
    Mutant(
        "F04",
        "tavoli duplicati accettati",
        ((MO, '        raise ValueError("duplicate table_id")', "        pass"),),
    ),
    Mutant(
        "F05",
        "testo libero accettato come identificativo di mercato",
        (
            (
                MO,
                'IDENTIFIER_PATTERN = r"^[0-9A-Za-z._-]{1,32}$"',
                'IDENTIFIER_PATTERN = r"^.{1,32}$"',
            ),
        ),
    ),
    Mutant(
        "F06",
        "limite monetario rimosso",
        (
            (
                MO,
                "Money = Annotated[float, Field(ge=-MONEY_LIMIT, le=MONEY_LIMIT)]",
                "Money = float",
            ),
        ),
    ),
    Mutant(
        "F07",
        "get_account legge la route sbagliata",
        (
            (
                FI,
                "            read=adapter.get_account_raw,",
                "            read=adapter.get_exposure_raw,",
            ),
        ),
    ),
    Mutant(
        "F08",
        "route approvata non servita risponde 404 invece di NOT_IMPLEMENTED",
        (
            (
                CS,
                "            if exact and any(p.fullmatch(raw_path) for p in unserved_read_routes()):",
                "            if False:",
            ),
        ),
    ),
    Mutant(
        "F09",
        "segmenti «.»/«..» accettati come identificativo di route",
        (
            (
                CC,
                '_SEGMENT: Final = "[A-Za-z0-9_-][A-Za-z0-9._-]{0,63}"',
                '_SEGMENT: Final = "[A-Za-z0-9._-]{1,64}"',
            ),
        ),
    ),
    Mutant(
        "F10",
        "NOT_IMPLEMENTED ritentato come indisponibilità",
        (
            (
                RT,
                "        except UpstreamNotImplemented:\n"
                "            # Capacità assente nel core: ripetere non la fa comparire.\n"
                "            raise ToolError(",
                "        except UpstreamNotImplemented:\n"
                "            last = ErrorCode.UPSTREAM_UNAVAILABLE\n"
                "            continue\n"
                "            raise ToolError(",
            ),
        ),
    ),
    Mutant(
        "F11",
        "501 dell'upstream non tipizzato",
        ((HT, "        if status == 501:\n            raise UpstreamNotImplemented\n", ""),),
    ),
    Mutant(
        "F12",
        "server avviato con provider mancanti",
        ((CS, "        if set(providers) != PROVIDER_NAMES or not all(", "        if not all("),),
    ),
    Mutant(
        "F13",
        "tool dichiarato dal contratto ma non esposto dal server",
        (
            (
                TI,
                "    registry.register(make_get_exposure(adapter, guard, timeout_s=timeout_s))\n",
                "",
            ),
        ),
    ),
    Mutant(
        "F14",
        "drawdown oltre il 100% accettato",
        (
            (
                MO,
                "Percent = Annotated[float, Field(ge=0, le=100)]",
                "Percent = Annotated[float, Field(ge=0)]",
            ),
        ),
    ),
    Mutant(
        "W01",
        "un blocco dichiarato dà PASS (falso verde su Windows)",
        (
            (
                "scripts/ci_platform_report.py",
                "    if res.blocked:\n",
                "    if False:\n",
            ),
        ),
    ),
    Mutant(
        "W02",
        "skip non dichiarato accettato (skip silenzioso)",
        (
            (
                "scripts/ci_platform_report.py",
                "                res.undeclared_skips.append(test_id)\n",
                "                res.env_skips.append(test_id)\n",
            ),
        ),
    ),
    Mutant(
        "W03",
        "blocco dichiarato che ora passa non segnalato (blocco stantio)",
        (
            (
                "scripts/ci_platform_report.py",
                "                res.stale.append(test_id)\n",
                "                res.passed += 1\n",
            ),
        ),
    ),
    Mutant(
        "W04",
        "codice d'uscita anomalo di pytest ignorato",
        (
            (
                "scripts/ci_platform_report.py",
                "    if pytest_rc not in (0, 1):\n",
                "    if False:\n",
            ),
        ),
    ),
    Mutant(
        "W05",
        "blocco dichiarato per un test inesistente non segnalato",
        (
            (
                "scripts/ci_platform_report.py",
                "    res.missing = sorted(set(blocked_decl) - seen)\n",
                "    res.missing = []\n",
            ),
        ),
    ),
    Mutant(
        "W06",
        "pytest fallito senza fallimenti nel rapporto accettato",
        (
            (
                "scripts/ci_platform_report.py",
                "    if pytest_rc == 1 and failures == 0:\n",
                "    if False:\n",
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


# Tetto per una singola suite: oltre, il mutante conta come rilevato (suite bloccata). Largo
# rispetto alla suite pulita (circa 1 minuto con le CPU occupate dagli altri mutanti in parallelo).
SUITE_TIMEOUT_S = 300


def run_suite(tmp: Path, *, explain: bool = False) -> str:
    """'pass', 'fail', 'timeout' (suite bloccata = mutante rilevato) o 'error'.

    Con ``explain`` (solo la baseline) un esito diverso da 'pass' stampa il codice d'uscita e la
    coda dell'output di pytest: una baseline rossa senza motivo non si può diagnosticare in CI.
    """
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
        if explain:
            print(f"baseline: suite oltre {SUITE_TIMEOUT_S} s")
        return "timeout"
    if explain and proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).splitlines()[-40:]
        print(f"baseline: pytest rc={proc.returncode}", *tail, sep="\n")
    # 0 = verde; 1 = test falliti; altri codici (collezione, uso) non provano nulla.
    return {0: "pass", 1: "fail"}.get(proc.returncode, "error")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    if args.jobs < 1:
        print("--jobs deve essere almeno 1")
        return 2
    idents = [m.ident for m in MUTANTS]
    if len(set(idents)) != len(idents):
        print("CATALOGO NON VALIDO: identificativi di mutante duplicati")
        return 2
    with tempfile.TemporaryDirectory(prefix="pf-mcp-mut-") as base:
        clean = Path(base) / "clean"
        clean.mkdir()
        for item in COPY:
            src = ROOT / item
            if src.is_dir():
                shutil.copytree(src, clean / item, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, clean / item)
        if run_suite(clean, explain=True) != "pass":
            print("BASELINE FAIL: la suite non passa sul codice non mutato")
            return 1

        def run_one(mutant: Mutant) -> dict[str, object]:
            work = Path(base) / mutant.ident
            shutil.copytree(clean, work)
            apply(work, mutant)
            started = time.monotonic()
            outcome = run_suite(work)
            status = {"pass": "SURVIVED", "error": "ERROR"}.get(outcome, "KILLED")
            print(f"{mutant.ident} {status:8} ({outcome:7}) {mutant.control}", flush=True)
            shutil.rmtree(work)
            return {
                "id": mutant.ident,
                "control": mutant.control,
                "status": status,
                "detected_by": outcome,
                "seconds": round(time.monotonic() - started, 2),
            }

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(run_one, MUTANTS))  # stesso ordine del catalogo
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
