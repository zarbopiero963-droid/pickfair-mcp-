# pickfair-mcp

Server MCP **locale su stdio** per controllare Pickfair attraverso strumenti autorizzati.
È un livello di trasporto e controllo verso la Control API v1 di Pickfair: **non è
un'autorità di trading**. Roserpina e l'Order Authority del core restano le uniche
autorità finanziarie.

Stato attuale (MCP-01a):

- unico tool esposto: `get_meta` (sola lettura, handshake di contratto fail-closed);
- adapter verso la Control API: **solo simulato** e dichiarato `certified: false`;
- adapter HTTP reale: **BLOCKED_CORE** finché la Control API (PF-API-0/1) non esiste;
- comandi (ordini, cashout, STOP, config, modalità): **non esposti**
  (`MCP_MUTATION_EXPOSURE = BLOCKED_UNTIL_CORE_AUTHORITY_READY`);
- nessun LIVE, nessuna credenziale Betfair, nessun accesso al DB Pickfair.

Regole di lavoro: [AGENTS.md](AGENTS.md). Contratto atteso: [docs/contract_v1.md](docs/contract_v1.md).

## Installazione locale

Requisiti: Python ≥ 3.11.

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install --require-hashes -r requirements/dev.lock
pip install --no-deps -e .
```

## Uso

```bash
pickfair-mcp contract-info                      # versione e schema hash supportati
pickfair-mcp serve --adapter simulated          # server MCP su stdio
pickfair-mcp serve --sim-scenario incompatible_major   # prova del fail-closed
```

Esempio di configurazione per un client MCP desktop (stdio):

```json
{
  "mcpServers": {
    "pickfair": {
      "command": "/percorso/.venv/bin/pickfair-mcp",
      "args": ["serve", "--adapter", "simulated"]
    }
  }
}
```

`--adapter http` termina con codice 2 e messaggio `BLOCKED_CORE`. Diagnostica e audit
(JSON per riga, campi in allowlist) vanno su stderr; stdout è riservato al protocollo.

## Risultato di `get_meta`

Ogni tool restituisce lo stesso envelope, sia in caso di successo sia di errore:

```json
{"ok": true, "request_id": "req_…", "tool": "get_meta",
 "data": {"contract_version": "1.0.0", "capabilities": ["GET /v1/meta"],
          "git_sha": "…", "schema_hash": "…",
          "handshake": {"status": "COMPATIBLE", "epoch": 1, "...": "..."},
          "upstream": {"kind": "simulated", "certified": false}},
 "error": null}
```

Errori: `INVALID_REQUEST`, `UNKNOWN_TOOL`, `CONTRACT_INCOMPATIBLE`, `UPSTREAM_TIMEOUT`,
`UPSTREAM_UNAVAILABLE`, `UPSTREAM_INVALID_RESPONSE`, `INTERNAL_ERROR`, con messaggi fissi
e motivi codificati; mai testo di eccezioni o dell'upstream.

## Verifiche

```bash
ruff check . && ruff format --check . && mypy && pytest
python scripts/critical_mutations.py     # mutazioni mirate sui controlli critici
mutmut run                               # mutation testing generale
```

I test con adapter simulato sono verifiche offline: **non** equivalgono alla
certificazione runtime di Pickfair, che resta NOT_RUN fino a MCP-07.
