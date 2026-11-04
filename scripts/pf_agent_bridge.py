"""PF-AGENT-BRIDGE/v1 — messaggi strutturati fra Claude B e Claude C (solo dati, mai comandi).

Specifica: docs/coordination/PF-AGENT-BRIDGE-v1.md. Solo libreria standard. Funzioni:

- `parse_message(text)`: estrae e valida l'intestazione v1 (chiavi chiuse, valori vincolati,
  SHA e hash completi, `body_sha256` facoltativo verificato sul corpo => payload alterato rilevato);
- `Ledger`: registro locale append-only (JSON Lines, lock esclusivo) per deduplicazione,
  idempotenza, ACK, timeout e ripresa dopo riavvio; stesso `message_id` con contenuto diverso =>
  CONFLICT (replay alterato o contraffazione), mai elaborato;
- `authority_flags(msg)`: segnala testi che rivendicano autorizzazioni owner o azioni privilegiate;
  il bridge NON esegue nulla: nessuna funzione applica patch, apre PR, fa merge o deploy;
- `verify_artifact(path, sha256)`: integrità di un artefatto prima di qualsiasi uso umano/agente;
- `poll_issue(...)`: lettura dei commenti della issue di coordinamento tramite `gh api` (solo GET),
  con intervallo minimo, errori 403/404/5xx/timeout come BLOCKED, nessun retry a raffica.

Limite di autenticazione: sulla issue GitHub tutti gli agenti pubblicano con l'account dell'owner
(#472), quindi `from` NON è dimostrabile da GitHub. Il canale diretto (`send_message` della
piattaforma Claude Code) fornisce invece l'ID della sessione mittente asserito dalla piattaforma.
In entrambi i casi un messaggio è un'informazione da verificare, mai un'autorizzazione.

Uso:
    python scripts/pf_agent_bridge.py validate FILE
    python scripts/pf_agent_bridge.py poll --repo OWNER/REPO --issue 37 --me claude-c --ledger PATH
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

PROTOCOL: Final = "PF-AGENT-BRIDGE/v1"
AGENTS: Final = frozenset({"claude-b", "claude-c"})
TYPES: Final = frozenset({"REQUEST", "HANDOFF", "RESPONSE", "BLOCKER", "ACK"})
STATUSES: Final = frozenset({"OPEN", "ACKED", "BLOCKED", "RESOLVED"})
REPOS: Final = frozenset(
    {"zarbopiero963-droid/pickfair-mcp-", "zarbopiero963-droid/Pickfair-nogui"}
)
REQUIRED: Final = (
    "protocol",
    "message_id",
    "from",
    "to",
    "type",
    "task",
    "repo",
    "base_sha",
    "head_sha",
    "artifact_url",
    "artifact_sha256",
    "needs_owner_approval",
    "reply_to",
    "status",
)
OPTIONAL: Final = ("body_sha256", "correlation")
ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{5,80}$")
SHA1_RE: Final = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
TASK_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ()._/#:-]{0,119}$")
URL_RE: Final = re.compile(
    r"^https://github\.com/zarbopiero963-droid/[A-Za-z0-9._-]+/[A-Za-z0-9._/#?=&-]{1,300}$"
)
HEADER_LINE: Final = re.compile(r"^([a-z_0-9]+):[ ]?(.*)$")
AUTHORITY_RE: Final = re.compile(
    r"(?i)\b(owner\s+(ha\s+)?(approv|autorizz|go)|approved\s+by\s+owner|merge\b|deploy\b|"
    r"live\b|place[_ ]?order|cashout|git\s+push|--force|rm\s+-rf|token\s*[:=])"
)


class BridgeError(ValueError):
    """Messaggio non conforme. `reason` è un codice stabile."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Message:
    fields: dict[str, Any]
    body: str
    content_sha256: str

    @property
    def message_id(self) -> str:
        return str(self.fields["message_id"])


def _null(value: str) -> str | None:
    return None if value in ("null", "~", "") else value


def parse_message(text: str) -> Message:
    """Estrae l'intestazione v1 (anche dentro un blocco ```yaml) e la valida in modo rigoroso."""
    lines = text.replace("\r\n", "\n").split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == f"protocol: {PROTOCOL}")
    except StopIteration:
        raise BridgeError("NOT_A_BRIDGE_MESSAGE") from None
    raw: dict[str, str] = {}
    end = start
    for end in range(start, len(lines)):
        line = lines[end].strip()
        if not line or line.startswith("```"):
            break
        match = HEADER_LINE.match(line)
        if match is None:
            raise BridgeError("HEADER_SYNTAX")
        key, value = match.group(1), match.group(2).strip()
        if key in raw:
            raise BridgeError("DUPLICATE_KEY")
        raw[key] = value
    else:
        end = len(lines)
    unknown = set(raw) - set(REQUIRED) - set(OPTIONAL)
    missing = set(REQUIRED) - set(raw)
    if unknown:
        raise BridgeError("UNKNOWN_KEY")
    if missing:
        raise BridgeError("MISSING_KEY")
    body = "\n".join(lines[end + 1 :]).strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1].strip() if "\n" in body else ""
    fields = _validate(raw)
    if fields.get("body_sha256") is not None:
        if hashlib.sha256(body.encode("utf-8")).hexdigest() != fields["body_sha256"]:
            raise BridgeError("BODY_ALTERED")
    canonical = json.dumps({"fields": fields, "body": body}, sort_keys=True, ensure_ascii=False)
    return Message(fields, body, hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _validate(raw: dict[str, str]) -> dict[str, Any]:
    f: dict[str, Any] = {k: _null(v) for k, v in raw.items()}
    if f["protocol"] != PROTOCOL:
        raise BridgeError("PROTOCOL")
    if not isinstance(f["message_id"], str) or not ID_RE.fullmatch(f["message_id"]):
        raise BridgeError("MESSAGE_ID")
    if f["from"] not in AGENTS or f["to"] not in AGENTS or f["from"] == f["to"]:
        raise BridgeError("PARTIES")
    if f["type"] not in TYPES:
        raise BridgeError("TYPE")
    if f["status"] not in STATUSES:
        raise BridgeError("STATUS")
    if f["repo"] not in REPOS:
        raise BridgeError("REPO")
    if not isinstance(f["task"], str) or not TASK_RE.fullmatch(f["task"]):
        raise BridgeError("TASK")
    for key in ("base_sha", "head_sha"):
        if f[key] is not None and not SHA1_RE.fullmatch(f[key]):
            raise BridgeError(key.upper())
    for key in ("artifact_sha256", "body_sha256"):
        if f.get(key) is not None and not SHA256_RE.fullmatch(f[key]):
            raise BridgeError(key.upper())
    if f["artifact_url"] is not None and not URL_RE.fullmatch(f["artifact_url"]):
        raise BridgeError("ARTIFACT_URL")
    if f["artifact_url"] is not None and f["artifact_sha256"] is None:
        raise BridgeError("ARTIFACT_WITHOUT_HASH")
    if f["needs_owner_approval"] not in ("true", "false"):
        raise BridgeError("NEEDS_OWNER_APPROVAL")
    f["needs_owner_approval"] = f["needs_owner_approval"] == "true"
    for key in ("reply_to", "correlation"):
        if f.get(key) is not None and not ID_RE.fullmatch(f[key]):
            raise BridgeError(key.upper())
    if f["type"] == "ACK" and f["reply_to"] is None:
        raise BridgeError("ACK_WITHOUT_REPLY_TO")
    return f


def authority_flags(msg: Message) -> list[str]:
    """Segnala rivendicazioni di autorità o azioni privilegiate. Segnala soltanto, non esegue."""
    flags = []
    if AUTHORITY_RE.search(msg.body):
        flags.append("CLAIMS_AUTHORITY_OR_PRIVILEGED_ACTION_UNVERIFIED")
    if msg.fields["needs_owner_approval"]:
        flags.append("NEEDS_OWNER_APPROVAL")
    return flags


def verify_artifact(path: Path, expected_sha256: str) -> bool:
    if not SHA256_RE.fullmatch(expected_sha256 or ""):
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256


@dataclass
class Ledger:
    """Registro append-only. Ogni scrittura sotto lock esclusivo; riletto a ogni operazione."""

    path: Path
    me: str
    ack_timeout_s: float = 3600.0
    clock: Callable[[], float] = time.time
    _cache: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.me not in AGENTS:
            raise BridgeError("ME")

    def _records(self, handle: Any) -> list[dict[str, Any]]:
        handle.seek(0)
        out = []
        for n, line in enumerate(handle.read().splitlines(), 1):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                raise BridgeError(f"LEDGER_CORRUPT:{n}") from None
        return out

    def _locked(self, fn: Callable[[Any, list[dict[str, Any]]], Any]) -> Any:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                return fn(handle, self._records(handle))
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    @staticmethod
    def _append(handle: Any, record: dict[str, Any]) -> None:
        handle.seek(0, 2)
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()

    def ingest(self, msg: Message, *, source: str) -> str:
        """NEW | DUPLICATE | CONFLICT | NOT_FOR_ME | OWN_MESSAGE. Mai esecuzione di contenuti."""

        def op(handle: Any, records: list[dict[str, Any]]) -> str:
            same = [
                r for r in records if r["message_id"] == msg.message_id and r["kind"] == "message"
            ]
            if same:
                if any(r["content_sha256"] != msg.content_sha256 for r in same):
                    self._append(
                        handle,
                        {
                            "kind": "conflict",
                            "message_id": msg.message_id,
                            "content_sha256": msg.content_sha256,
                            "at": self.clock(),
                            "source": source,
                        },
                    )
                    return "CONFLICT"
                return "DUPLICATE"
            direction = "out" if msg.fields["from"] == self.me else "in"
            if direction == "in" and msg.fields["to"] != self.me:
                return "NOT_FOR_ME"
            self._append(
                handle,
                {
                    "kind": "message",
                    "message_id": msg.message_id,
                    "content_sha256": msg.content_sha256,
                    "direction": direction,
                    "type": msg.fields["type"],
                    "reply_to": msg.fields["reply_to"],
                    "at": self.clock(),
                    "source": source,
                },
            )
            return "OWN_MESSAGE" if direction == "out" else "NEW"

        result: str = self._locked(op)
        return result

    def state(self) -> dict[str, str]:
        """Stato per message_id: OPEN | ACKED | RESOLVED | BLOCKED (ACK fuori ordine inclusi)."""

        def op(_handle: Any, records: list[dict[str, Any]]) -> dict[str, str]:
            messages = [r for r in records if r["kind"] == "message"]
            status = {r["message_id"]: "OPEN" for r in messages if r["type"] != "ACK"}
            for r in messages:
                target = r.get("reply_to")
                if target in status:
                    if r["type"] == "ACK" and status[target] == "OPEN":
                        status[target] = "ACKED"
                    elif r["type"] in ("RESPONSE",):
                        status[target] = "RESOLVED"
                    elif r["type"] == "BLOCKER":
                        status[target] = "BLOCKED"
            return status

        result: dict[str, str] = self._locked(op)
        return result

    def missing_acks(self) -> list[str]:
        """Messaggi inviati da me senza ACK oltre il timeout: da reinviare con lo STESSO id."""

        def op(_handle: Any, records: list[dict[str, Any]]) -> list[str]:
            acked = {
                r.get("reply_to") for r in records if r["kind"] == "message" and r["type"] == "ACK"
            }
            now = self.clock()
            return sorted(
                r["message_id"]
                for r in records
                if r["kind"] == "message"
                and r["direction"] == "out"
                and r["type"] != "ACK"
                and r["message_id"] not in acked
                and now - r["at"] > self.ack_timeout_s
            )

        result: list[str] = self._locked(op)
        return result

    def mark_poll(self, min_interval_s: float) -> bool:
        """True se un nuovo polling è ammesso (limite di frequenza persistente)."""

        def op(handle: Any, records: list[dict[str, Any]]) -> bool:
            last = max((r["at"] for r in records if r["kind"] == "poll"), default=None)
            now = self.clock()
            if last is not None and now - last < min_interval_s:
                return False
            self._append(handle, {"kind": "poll", "message_id": "-", "at": now})
            return True

        result: bool = self._locked(op)
        return result


Fetch = Callable[[str, int], list[dict[str, Any]]]


def gh_fetch(repo: str, issue: int) -> list[dict[str, Any]]:
    """Solo lettura: GET dei commenti tramite gh (credenziali solo di gh, mai dello script)."""
    proc = subprocess.run(
        ["gh", "api", "--method", "GET", f"repos/{repo}/issues/{issue}/comments", "--paginate"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise BridgeError("GITHUB_UNAVAILABLE")
    data = json.loads(proc.stdout or "[]")
    if not isinstance(data, list):
        raise BridgeError("GITHUB_UNEXPECTED")
    return data


def poll_issue(
    ledger: Ledger, repo: str, issue: int, *, fetch: Fetch = gh_fetch, min_interval_s: float = 300.0
) -> dict[str, Any]:
    if repo not in REPOS:
        raise BridgeError("REPO")
    if not ledger.mark_poll(min_interval_s):
        return {"status": "RATE_LIMITED", "new": []}
    try:
        comments = fetch(repo, issue)
    except (BridgeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {"status": "BLOCKED", "new": []}
    report: dict[str, Any] = {"status": "OK", "new": [], "conflicts": [], "invalid": 0}
    for comment in comments:
        body = comment.get("body") if isinstance(comment, dict) else None
        if not isinstance(body, str):
            continue
        try:
            msg = parse_message(body)
        except BridgeError as exc:
            if exc.reason != "NOT_A_BRIDGE_MESSAGE":
                report["invalid"] += 1
            continue
        outcome = ledger.ingest(msg, source=f"github:{repo}#{issue}:{comment.get('id')}")
        if outcome == "NEW":
            report["new"].append(
                {
                    "message_id": msg.message_id,
                    "type": msg.fields["type"],
                    "flags": authority_flags(msg),
                }
            )
        elif outcome == "CONFLICT":
            report["conflicts"].append(msg.message_id)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("file", type=Path)
    p = sub.add_parser("poll")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--me", required=True, choices=sorted(AGENTS))
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--min-interval", type=float, default=300.0)
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        try:
            msg = parse_message(args.file.read_text(encoding="utf-8"))
        except BridgeError as exc:
            print(json.dumps({"valid": False, "reason": exc.reason}))
            return 1
        print(
            json.dumps(
                {
                    "valid": True,
                    "message_id": msg.message_id,
                    "content_sha256": msg.content_sha256,
                    "flags": authority_flags(msg),
                }
            )
        )
        return 0
    report = poll_issue(
        Ledger(args.ledger, args.me), args.repo, args.issue, min_interval_s=args.min_interval
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] in ("OK", "RATE_LIMITED") else 3


if __name__ == "__main__":
    sys.exit(main())
