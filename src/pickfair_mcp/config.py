"""Configurazione sicura.

- La Control API può essere raggiunta solo su loopback IP letterale
  (127.0.0.0/8 o ::1) con porta esplicita: niente nomi host, niente reti esterne.
- In MCP-01a l'adapter HTTP non esiste: il validatore prepara il vincolo per
  quando la Control API sarà pronta (BLOCKED_CORE).
"""

from __future__ import annotations

import ipaddress
from typing import Final
from urllib.parse import urlsplit

from pickfair_mcp.policy.handshake import validate_timeout_s

BLOCKED_CORE_MESSAGE: Final = (
    "BLOCKED_CORE: la Control API Pickfair (PF-API-0/1) non esiste ancora; "
    "l'adapter HTTP sarà abilitato solo quando sarà pronta e certificata."
)


class ConfigError(ValueError):
    """Configurazione rifiutata (fail-closed). `code` è stabile e verificato dai test."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_control_api_url(url: str) -> str:
    """Restituisce la forma canonica `http://IP:PORTA` oppure solleva ConfigError."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ConfigError("CONFIG_URL_INVALID") from None
    if parts.scheme != "http":
        raise ConfigError("CONFIG_SCHEME")
    if parts.username is not None or parts.password is not None:
        raise ConfigError("CONFIG_USERINFO")
    if parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ConfigError("CONFIG_PATH")
    # urlsplit rifiuta da sé porte negative o > 65535: restano assente e zero.
    if not port:
        raise ConfigError("CONFIG_PORT")
    if not parts.hostname:
        raise ConfigError("CONFIG_HOST_NOT_IP")
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        raise ConfigError("CONFIG_HOST_NOT_IP") from None
    # IPv6 ammesso solo come ::1: le forme IPv4-mapped sono rifiutate anche se
    # alcune versioni di Python le considerano loopback.
    if not address.is_loopback or (address.version == 6 and address != ipaddress.IPv6Address(1)):
        raise ConfigError("CONFIG_HOST_NOT_LOOPBACK")
    host = f"[{address}]" if address.version == 6 else str(address)
    return f"http://{host}:{port}"


def validate_timeout(value: object) -> float:
    try:
        return validate_timeout_s(value)
    except ValueError as exc:
        raise ConfigError(f"CONFIG_TIMEOUT:{exc}") from None
