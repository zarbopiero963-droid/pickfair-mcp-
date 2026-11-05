# Stato persistente di Claude C (MCP + Control API) — protocollo `pf-checkpoint/3`

Branch di **solo stato** (nessun codice): ogni checkpoint è un commit con `checkpoint/claude-c-mcp/`
(`STATE.json`, `MANIFEST.sha256`, `HANDOFF.md`, `RUNBOOK.md`, evidenze), scritto e verificato con
`tools/agent_checkpoint/pfckpt.py` di Pickfair-nogui (`save` con concorrenza ottimistica, lease, nessun force-push,
readback remoto). Il codice vive nei branch `ccr-edf04c7d-e7vtj1-*`; il registro degli incrementi è
pickfair-mcp- #37.
