"""Control API v1 di Pickfair — server di SOLA LETTURA (PF-API-1), solo libreria standard.

Vive nel repository pickfair-mcp- (direttiva owner: separazione dei repository). Non importa
né conosce il motore Pickfair: il core gli fornisce due provider di lettura tramite un ponte
che appartiene a Pickfair-nogui (handoff a Claude B, ``docs/handoff/``).

Contenuto:
- ``contract``: versione, capability, schema hash e schemi letti da ``contract_v1.json``
  (copia identica del descrittore canonico del MCP);
- ``schema_check``: validazione fail-closed delle risposte prima dell'invio;
- ``tokens``: emissione e rotazione del token Bearer locale (file 0600);
- ``server``: server HTTP su 127.0.0.1, solo GET, nessuna route di comando.
"""

from pickfair_control_api.contract import CAPABILITIES, CONTRACT_VERSION, schema_hash
from pickfair_control_api.server import ControlApiConfigError, ControlApiServer
from pickfair_control_api.tokens import TokenStore, issue_token_file, publish_fresh_token

__all__ = [
    "CAPABILITIES",
    "CONTRACT_VERSION",
    "ControlApiConfigError",
    "ControlApiServer",
    "TokenStore",
    "issue_token_file",
    "publish_fresh_token",
    "schema_hash",
]
