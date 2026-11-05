# Runbook

```bash
git clone https://github.com/zarbopiero963-droid/pickfair-mcp- && cd pickfair-mcp-
git checkout <code.sha di STATE.json>              # oggi ccr-edf04c7d-e7vtj1-mcp01m-trailing
python3 -m pytest -q tests                          # suite MCP (crossrepo richiede il core)
python3 scripts/run_suites.py campaign:all-offline --evidence /tmp/ev   # G8 (branch ccr-edf04c7d-e7vtj1-g8-suites)
python3 scripts/critical_mutations.py               # mutanti critici MCP
# E2E col core reale: PICKFAIR_CORE_PATH=<Pickfair-nogui + patch 01d...> PICKFAIR_CORE_PYTHON=<python 3.11> pytest tests/crossrepo
```
Verifica del checkpoint: `python3 tools/agent_checkpoint/pfckpt.py verify --repo . --ref origin/ccr-edf04c7d-e7vtj1-checkpoint --dir checkpoint/claude-c-mcp` (strumento di Pickfair-nogui).
