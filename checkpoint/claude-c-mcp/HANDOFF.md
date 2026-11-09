# Ripresa — Claude C (MCP + Control API)

Registro degli incrementi: pickfair-mcp- #37 (commenti PF-AGENT-BRIDGE/v1). Catena MCP da integrare (dopo le correzioni
P0/P1): 01d -> 01e -> 01f -> 01g -> 01h -> 01j -> 01k -> 01l -> SEC-01 -> 01i r2 (dopo F-04) -> 01m (dopo F-03). Ogni incremento ha il suo
branch `ccr-edf04c7d-e7vtj1-*` e `docs/handoff/<incremento>.md`. Le patch del core NON stanno nel repository MCP:
arrivano a Claude B tramite l'owner (archivi con SHA-256 nei commenti di #37).

Stato: vedi STATE.json (`lotto_corrente`, `next_atomic_action`). Vincoli: nessun LIVE, nessun ordine reale, nessun merge,
nessun deploy VPS, nessuna nuova route K3, nessuna nuova infrastruttura.

## Seq 12 (09/11/2026): scatola nera pronta per BB-1

Branch `ccr-edf04c7d-e7vtj1-mcp01p-bb1-ready`, catena 90e7d45 (MCP-01p) → 907423e (MCP-01q, forma normativa di
BB-1) → df044fc (mappature sulle fixture reali di B, sha256 c11e4108…2766c0). Contratto 1.15.0.

Verificato sulle fixture: RED 7 → GREEN 10. Ancora NOT_RUN: `check_reader` e gli scenari sulla classe reale,
dopo #615. Patch 13 (f16-compat) DURABLE su handoff/claude-c/mcp-core-20261105 @ 0a529035.

Prossimo passo: `next_atomic_action` in STATE.json.
