"""Fixture comuni.

Guard di rete autouse: ogni test fallisce se qualcosa nel processo di test tenta
una connessione IPv4/IPv6, una risoluzione DNS o un invio UDP. I sottoprocessi
(e2e stdio) non sono coperti da questa guardia: lì valgono i guard statici.
MCP-01a non ha alcun motivo di aprire connessioni di rete; l'adapter HTTP verso
la Control API è BLOCKED_CORE.
"""

from __future__ import annotations

import socket
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "pickfair_mcp"

_INET_FAMILIES = {socket.AF_INET, socket.AF_INET6}


class NetworkAttemptError(AssertionError):
    """Sollevata quando il codice sotto test tenta una connessione di rete."""


_NETWORK_AUDIT_EVENTS = {
    "socket.connect",
    "socket.sendto",
    "socket.sendmsg",
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "socket.gethostbyaddr",
    "socket.getnameinfo",
}
_network_guard_active = False
_hook_attempts: list[object] = []


def _audit_hook(event: str, args: tuple[object, ...]) -> None:
    if not _network_guard_active or event not in _NETWORK_AUDIT_EVENTS:
        return
    if event in {"socket.connect", "socket.sendto", "socket.sendmsg"}:
        sock = args[0]
        if getattr(sock, "family", None) not in _INET_FAMILIES:
            return
    _hook_attempts.append(event)
    raise NetworkAttemptError(f"operazione di rete vietata: {event}")


sys.addaudithook(_audit_hook)  # gli audit hook non si rimuovono: si attiva per test


@pytest.fixture(autouse=True)
def network_audit_guard() -> Iterator[None]:
    """Copre anche i percorsi che il monkeypatch non vede (_socket, sendmsg, DNS)."""
    global _network_guard_active
    _hook_attempts.clear()
    _network_guard_active = True
    try:
        yield
    finally:
        _network_guard_active = False
    assert _hook_attempts == [], f"operazioni di rete rilevate: {_hook_attempts!r}"


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[object]]:
    attempts: list[object] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_connect(self: socket.socket, address: object) -> None:
        if self.family in _INET_FAMILIES:
            attempts.append(address)
            raise NetworkAttemptError(f"connessione di rete vietata: {address!r}")
        original_connect(self, address)  # type: ignore[arg-type]

    def guarded_connect_ex(self: socket.socket, address: object) -> int:
        if self.family in _INET_FAMILIES:
            attempts.append(address)
            raise NetworkAttemptError(f"connessione di rete vietata: {address!r}")
        return original_connect_ex(self, address)  # type: ignore[arg-type]

    def guarded_create_connection(address: object, *args: object, **kwargs: object) -> None:
        attempts.append(address)
        raise NetworkAttemptError(f"connessione di rete vietata: {address!r}")

    def guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> None:
        attempts.append(host)
        raise NetworkAttemptError(f"risoluzione DNS vietata: {host!r}")

    def guarded_sendto(self: socket.socket, *args: object) -> int:
        if self.family in _INET_FAMILIES:
            attempts.append(args[-1])
            raise NetworkAttemptError("invio UDP vietato")
        return original_sendto(self, *args)  # type: ignore[arg-type]

    original_sendto = socket.socket.sendto
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    yield attempts
    assert attempts == [], f"tentativi di rete rilevati: {attempts!r}"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Sotto mutmut i test e2e e di guardia (sottoprocessi, git) non sono pertinenti."""
    import os

    if "MUTANT_UNDER_TEST" not in os.environ:
        return
    skip = pytest.mark.skip(reason="eseguito dalla suite normale, non dal mutation testing")
    for item in items:
        if item.get_closest_marker("e2e") or item.get_closest_marker("guard"):
            item.add_marker(skip)
