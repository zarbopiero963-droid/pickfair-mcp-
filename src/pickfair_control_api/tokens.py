"""Token Bearer locale della Control API (D-11, prima implementazione): emissione e rotazione.

- `issue_token_file(path)`: token nuovo (256 bit, URL-safe) in un file NUOVO 0600, mai
  sovrascritto e mai attraverso un symlink.
- `TokenStore.rotate(path)`: rotazione senza finestra di rifiuto e senza file parziali:
  1. il nuovo token diventa valido INSIEME al vecchio;
  2. viene scritto in un file temporaneo 0600 nella stessa cartella e sostituito atomicamente
     (`os.replace`): un lettore vede il vecchio o il nuovo, mai un contenuto parziale;
  3. il vecchio token viene revocato.
  Rotazioni concorrenti sono serializzate per intero da un lock dedicato (MCP-SEC-01); il file temporaneo
  è creato con O_EXCL. Un token vuoto, corto o fuori alfabeto non è mai accettato (`WeakTokenError`).
- Il confronto è a tempo costante; il token non compare in repr, log o eccezioni.

Limiti dichiarati: chiunque possa leggere il file come lo stesso utente del processo ottiene il
token (è un segreto locale, non un'identità); il token non è legato al processo chiamante;
nessuna scadenza automatica oltre alla rotazione esplicita. Miglioramenti possibili senza nuovi
servizi: socket Unix con verifica SO_PEERCRED; token per sessione MCP; rotazione a ogni avvio.
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
import threading
from pathlib import Path
from typing import Final

TOKEN_BYTES: Final = 32  # 256 bit => 43 caratteri URL-safe
# MCP-SEC-01: un TokenStore non accetta mai un token vuoto, corto o fuori alfabeto (prima ogni stringa).
MIN_TOKEN_CHARS: Final = 43
MAX_TOKEN_CHARS: Final = 256
_TOKEN_RE: Final = re.compile(r"[A-Za-z0-9_-]+")


class WeakTokenError(ValueError):
    """Token troppo corto o fuori alfabeto URL-safe. Il messaggio non contiene mai il token."""


def _checked(token: object) -> bytes:
    if (
        not isinstance(token, str)
        or not MIN_TOKEN_CHARS <= len(token) <= MAX_TOKEN_CHARS
        or not _TOKEN_RE.fullmatch(token)
    ):
        raise WeakTokenError("TOKEN_WEAK")
    return token.encode("ascii")


def _new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def _write_exclusive(path: Path, token: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)  # indipendente dalla umask
        os.write(fd, token.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)


def issue_token_file(path: Path) -> str:
    token = _new_token()
    _write_exclusive(path, token)
    return token


def generate_token_store() -> TokenStore:
    """Token nuovo SOLO in memoria: nessun file finché il server non è pronto (vedi `publish`)."""
    return TokenStore(_new_token())


def publish_fresh_token(path: Path) -> TokenStore:
    """Avvio o riavvio: token NUOVO pubblicato atomicamente, anche se il file esiste già.

    Il token di un'esecuzione precedente non resta mai valido. Il file temporaneo è 0600 con
    O_EXCL nella stessa cartella; un symlink al percorso viene sostituito, mai seguito.
    """
    token = _new_token()
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        _write_exclusive(tmp, token)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return TokenStore(token)


class TokenStore:
    """Token validi del server. Di norma uno solo; due solo durante una rotazione."""

    def __init__(self, token: str) -> None:
        self._lock = threading.Lock()
        # MCP-SEC-01: una rotazione intera alla volta. Prima il lock copriva solo i passi in memoria: una
        # rotazione fallita dopo un'altra riuscita ripristinava il token revocato e revocava quello del file.
        self._rotation_lock = threading.Lock()
        self._valid: tuple[bytes, ...] = (_checked(token),)
        self.rotations = 0

    def __repr__(self) -> str:
        return "TokenStore(<redacted>)"

    def publish(self, path: Path) -> None:
        """Scrive il token CORRENTE in `path` (0600, sostituzione atomica, symlink sostituito)."""
        with self._lock:
            token = self._valid[-1].decode("ascii")
        tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        try:
            _write_exclusive(tmp, token)
            os.replace(tmp, path)
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    def accepts(self, presented: bytes) -> bool:
        with self._lock:
            valid = self._valid
        ok = False
        for candidate in valid:
            # Nessuna uscita anticipata: il tempo non dipende da quale token coincide.
            ok |= hmac.compare_digest(presented, candidate)
        return ok

    def rotate(self, path: Path) -> str:
        with self._rotation_lock:
            return self._rotate_serialized(path)

    def _rotate_serialized(self, path: Path) -> str:
        new = _new_token()
        new_bytes = _checked(new)
        tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        with self._lock:
            old = self._valid[-1]
            self._valid = (old, new_bytes)
        try:
            _write_exclusive(tmp, new)
            os.replace(tmp, path)
        except BaseException:
            with self._lock:
                self._valid = (old,)
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        with self._lock:
            self._valid = (new_bytes,)
            self.rotations += 1
        return new
