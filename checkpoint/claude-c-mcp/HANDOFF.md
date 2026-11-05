# Ripresa — Claude C (MCP + Control API)

Registro degli incrementi: pickfair-mcp- #37 (commenti PF-AGENT-BRIDGE/v1). Catena MCP da integrare (dopo le correzioni
P0/P1): 01d -> 01e -> 01f -> 01g -> 01h -> 01j -> 01k -> 01l -> SEC-01 -> 01i r2 (dopo F-04) -> 01m (dopo F-03). Ogni incremento ha il suo
branch `ccr-edf04c7d-e7vtj1-*` e `docs/handoff/<incremento>.md`. Le patch del core NON stanno nel repository MCP:
arrivano a Claude B tramite l'owner (archivi con SHA-256 nei commenti di #37).

Stato: vedi STATE.json (`lotto_corrente`, `next_atomic_action`). Vincoli: nessun LIVE, nessun ordine reale, nessun merge,
nessun deploy VPS, nessuna nuova route K3, nessuna nuova infrastruttura.
