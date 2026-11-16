"""Token Bearer locale della Control API letto da file (D-11, prima implementazione).

Il file è creato dalla Control API (permessi 0600, proprietario = utente del processo).
Prima di ogni lettura l'adapter verifica, fail-closed:

- percorso assoluto, senza componenti «..»;
- nessun symlink (apertura con O_NOFOLLOW), file regolare;
- proprietario = utente atteso; nessun permesso per gruppo o altri (mode & 0o077 == 0);
- cartella contenitore non scrivibile da gruppo o altri e di proprietà dell'utente o di root;
- dimensione massima e alfabeto URL-safe, lunghezza 43-128 (nessun a capo, nessuno spazio).

Il token non compare mai in eccezioni, log, audit o risposte: gli errori portano solo un codice.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Final

TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
MAX_TOKEN_FILE_BYTES: Final = 256


class TokenFileError(Exception):
    """File del token non utilizzabile. `code` è stabile e non contiene dati del file."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_token_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise TokenFileError("TOKEN_PATH_INVALID")
    return path


class LocalTokenFile:
    """Legge e verifica il token a ogni richiesta di (ri)caricamento."""

    def __init__(self, path: Path | str, *, expected_uid: int | None = None) -> None:
        self._path = validate_token_path(str(path))
        # Su Windows os.getuid non esiste: nessun uid atteso (-1, mai un utente reale) e read()
        # fallisce col codice dichiarato TOKEN_PLATFORM_UNSUPPORTED, non con un AttributeError qui.
        if expected_uid is not None:
            self._uid = expected_uid
        else:
            self._uid = os.getuid() if os.name == "posix" else -1

    @property
    def path(self) -> Path:
        return self._path

    def _check_directory(self) -> None:
        try:
            info = os.lstat(self._path.parent)
        except OSError:
            raise TokenFileError("TOKEN_DIR_UNSAFE") from None
        if not stat.S_ISDIR(info.st_mode):
            raise TokenFileError("TOKEN_DIR_UNSAFE")
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise TokenFileError("TOKEN_DIR_UNSAFE")
        if info.st_uid not in (self._uid, 0):
            raise TokenFileError("TOKEN_DIR_UNSAFE")

    def read(self) -> str:
        if os.name != "posix":
            # Permessi e proprietario POSIX non dimostrano nulla altrove: fail-closed finché
            # non esiste una verifica equivalente delle ACL di Windows (limite dichiarato).
            raise TokenFileError("TOKEN_PLATFORM_UNSUPPORTED")
        self._check_directory()
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = os.open(self._path, flags)
        except FileNotFoundError:
            raise TokenFileError("TOKEN_FILE_MISSING") from None
        except OSError:
            # ELOOP con O_NOFOLLOW: il percorso è un symlink.
            if self._path.is_symlink():
                raise TokenFileError("TOKEN_FILE_SYMLINK") from None
            raise TokenFileError("TOKEN_FILE_UNREADABLE") from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise TokenFileError("TOKEN_FILE_NOT_REGULAR")
            if info.st_uid != self._uid:
                raise TokenFileError("TOKEN_FILE_OWNER")
            if info.st_mode & 0o077:
                raise TokenFileError("TOKEN_FILE_PERMISSIONS")
            if info.st_size > MAX_TOKEN_FILE_BYTES:
                raise TokenFileError("TOKEN_FILE_TOO_LARGE")
            raw = os.read(fd, MAX_TOKEN_FILE_BYTES + 1)
        finally:
            os.close(fd)
        try:
            token = raw.decode("ascii")
        except UnicodeDecodeError:
            raise TokenFileError("TOKEN_FILE_MALFORMED") from None
        if not TOKEN_RE.fullmatch(token):
            raise TokenFileError("TOKEN_FILE_MALFORMED")
        return token
