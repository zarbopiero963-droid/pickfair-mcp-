"""La guardia di rete dei test non è a vuoto: ogni via di rete viene bloccata."""

from __future__ import annotations

import socket

import pytest

from tests.conftest import NetworkAttemptError


@pytest.mark.parametrize(
    "attempt",
    [
        lambda: socket.gethostbyname("localhost"),
        lambda: socket.getaddrinfo("localhost", 80),
        lambda: socket.getnameinfo(("127.0.0.1", 80), 0),
        lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.1", 9)),
        # sendmsg esiste solo dove il sistema lo offre (non su Windows).
        *(
            [
                lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendmsg(
                    [b"x"], [], 0, ("127.0.0.1", 9)
                )
            ]
            if hasattr(socket.socket, "sendmsg")
            else []
        ),
        lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", 9)),
    ],
)
def test_network_paths_are_blocked(attempt: object, forbid_network: list[object]) -> None:
    import tests.conftest as guard

    with pytest.raises(NetworkAttemptError):
        attempt()  # type: ignore[operator]
    # Tentativi attesi: non devono far fallire il teardown delle guardie.
    guard._hook_attempts.clear()
    forbid_network.clear()


def _python_socketpair() -> tuple[socket.socket, socket.socket]:
    """Come il socketpair di Windows: listener su 127.0.0.1 e connessione a sé stesso."""
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lsock.bind(("127.0.0.1", 0))
        lsock.listen()
        csock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        csock.connect(lsock.getsockname())
        ssock, _ = lsock.accept()
    finally:
        lsock.close()
    return ssock, csock


def test_socketpair_may_connect_to_itself_only_inside_the_call(
    forbid_network: list[object],
) -> None:
    """MCP-CI: l'eccezione per il socketpair di Windows è circoscritta alla chiamata stessa."""
    import tests.conftest as guard

    a, b = guard.guarded_socketpair(_python_socketpair)()  # type: ignore[misc]
    try:
        a.sendall(b"x")
        assert b.recv(1) == b"x"
    finally:
        a.close()
        b.close()
    # fuori dalla chiamata la stessa connessione loopback resta vietata
    with pytest.raises(NetworkAttemptError):
        _python_socketpair()
    guard._hook_attempts.clear()
    forbid_network.clear()


def test_socketpair_exception_never_covers_a_non_loopback_target(
    forbid_network: list[object],
) -> None:
    import tests.conftest as guard

    def outbound() -> None:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("10.255.255.1", 9))

    with pytest.raises(NetworkAttemptError):
        guard.guarded_socketpair(outbound)()
    guard._hook_attempts.clear()
    forbid_network.clear()


def test_socketpair_is_guarded_during_tests() -> None:
    """La fixture installa il socketpair circoscritto: un socketpair qualsiasi passa da lì."""
    assert socket.socketpair.__name__ == "socketpair"
    assert socket.socketpair.__qualname__.startswith("guarded_socketpair")


def test_subprocess_env_is_minimal_and_adds_windows_system_vars_only_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    import tests.conftest as guard

    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    monkeypatch.setenv("PICKFAIR_SECRET_LIKE", "x")
    monkeypatch.setattr(sys, "platform", "linux")
    assert set(guard.subprocess_env(PYTHONPATH="src")) == {"PATH", "PYTHONPATH"}
    monkeypatch.setattr(sys, "platform", "win32")
    env = guard.subprocess_env(PYTHONPATH="src")
    assert env["SYSTEMROOT"] == "C:\\Windows" and env["PYTHONPATH"] == "src"
    assert "PICKFAIR_SECRET_LIKE" not in env  # mai l'ambiente completo del processo di test
