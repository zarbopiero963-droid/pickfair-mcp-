"""Esposizione delle mutazioni: bloccata in MCP-01a, senza alcun interruttore.

Nessuna variabile d'ambiente, file o argomento può abilitare i comandi.
L'abilitazione futura richiede una modifica di codice in una PR autorizzata,
dopo la certificazione dell'autorità del core (PF-API commands).
"""

from __future__ import annotations

from typing import Final

MUTATION_EXPOSURE: Final = "BLOCKED_UNTIL_CORE_AUTHORITY_READY"
LIVE_COMMANDS: Final = "DISABLED"


def commands_exposed() -> bool:
    return False
