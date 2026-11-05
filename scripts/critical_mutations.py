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
COPY = ("src", "tests", "docs", "scripts", "pyproject.toml", "AGENTS.md", ".guardrails", ".github")
TEST_ARGS = ("tests/unit", "tests/integration", "tests/control_api", "tests/guards")


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
                "            status, content_type, body = self._request(path, self._current_token(reload=True))",
                "            status, content_type, body = self._request(path, self._current_token(reload=False))",
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
                CS,
                "            validate(body, response_schema(ROUTE_SCHEMAS[route]))",
                "            response_schema(ROUTE_SCHEMAS[route])",
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
                CT,
                '            self._valid = (old, new.encode("ascii"))',
                "            self._valid = (old,)",
            ),
        ),
    ),
    Mutant(
        "C06",
        "vecchio token non revocato dopo la rotazione",
        (
            (
                CT,
                '            self._valid = (new.encode("ascii"),)\n            self.rotations += 1',
                '            self._valid = (old, new.encode("ascii"))\n            self.rotations += 1',
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
                MO,
                '        _check_unavailable({"settings": self.settings}, self.unavailable)',
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
        "L01",
        "esposizione residua senza il tavolo che porta la posizione accettata",
        (
            (
                MO,
                '        if (self.residual_exposure is not None) != (self.residual_source == "TABLE"):',
                '        if False:',
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
                '        if False:',
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
                '        if False:',
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
                '        pass',
            ),
        ),
    ),
    Mutant(
        "L05",
        "contatori della posizione oltre gli ordini letti accettati",
        (
            (
                MO,
                '        if max(self.partially_matched, self.in_reconciliation, self.ambiguous) > self.orders:',
                '        if False:',
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
                '        pass',
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
                MO,
                '        if self.state == "OK" and (self.reason or self.omitted or self.truncated):',
                '        if self.state == "OK" and self.reason:',
            ),
        ),
    ),
    Mutant(
        "O08",
        "snapshot PARTIAL senza dire cosa manca accettato",
        (
            (
                MO,
                '        if self.state == "PARTIAL" and not (self.reason and (self.omitted or self.truncated)):',
                "        if False:",
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
                MO,
                '    state: Literal["UNKNOWN", "UNAVAILABLE"]\n    reason: Code\n',
                '    state: Literal["UNKNOWN", "UNAVAILABLE"]\n    reason: Code | None\n',
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
