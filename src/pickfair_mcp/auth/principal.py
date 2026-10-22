"""Principal: identità locale e insieme esplicito di scope (nessuna gerarchia implicita).

Il principal non porta credenziali: nessun campo token/password esiste, quindi
nessuna credenziale può finire in stdout, stderr, audit o journal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final


class Scope(Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    OWNER = "owner"


PRINCIPAL_ID_RE: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_SCOPES_BY_VALUE: Final = {s.value: s for s in Scope}
_PRINCIPAL_KEYS: Final = frozenset({"id", "scopes"})


class PrincipalInvalid(Exception):
    """Principal assente o malformato. Il messaggio non riporta mai l'input."""

    reason: Final = "PRINCIPAL_INVALID"

    def __init__(self) -> None:
        super().__init__("PRINCIPAL_INVALID")


def principal_is_valid(principal_id: object, scopes: object) -> bool:
    return (
        type(principal_id) is str
        and PRINCIPAL_ID_RE.fullmatch(principal_id) is not None
        and type(scopes) is frozenset
        and len(scopes) > 0
        and all(type(s) is Scope for s in scopes)
    )


@dataclass(frozen=True, slots=True)
class Principal:
    principal_id: str
    scopes: frozenset[Scope]

    def __post_init__(self) -> None:
        if not principal_is_valid(self.principal_id, self.scopes):
            raise PrincipalInvalid()


def parse_principal(raw: object) -> Principal:
    """Parsing rigoroso: solo le chiavi `id` e `scopes`, scope esatti e senza duplicati."""
    if type(raw) is not dict or set(raw) != _PRINCIPAL_KEYS:
        raise PrincipalInvalid()
    values = raw["scopes"]
    if type(values) is not list or len(set(map(repr, values))) != len(values):
        raise PrincipalInvalid()
    scopes = []
    for value in values:
        if type(value) is not str or value not in _SCOPES_BY_VALUE:
            raise PrincipalInvalid()
        scopes.append(_SCOPES_BY_VALUE[value])
    return Principal(principal_id=raw["id"], scopes=frozenset(scopes))
