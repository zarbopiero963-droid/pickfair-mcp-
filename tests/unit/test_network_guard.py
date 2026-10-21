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
        lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendmsg(
            [b"x"], [], 0, ("127.0.0.1", 9)
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
