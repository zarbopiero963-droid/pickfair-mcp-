# Handoff a Claude B — MCP-01e: `GET /v1/account` e `GET /v1/exposure` nel ponte del core

Da: Claude C · Per: Claude B · 04/11/2026 · **dipende da MCP-01d** (`docs/handoff/control_api_core_bridge.md`).
Claude C non modifica Pickfair-nogui: la patch è una proposta; integrazione, tempi e PR sono di
Claude B, dopo #608 e #606, con una PR indipendente e safety-critical. Nessuna fretta.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01e.patch`, 8 file, +735/−8, SHA-256 in `core_bridge_mcp01e.patch.sha256` (questa cartella) |
| Base della patch | Pickfair-nogui `main` `ada40765e7949b8deb7661b3b5e9ddc8484adba3` **con la patch MCP-01d applicata** (`505f579c…7d0c`) |
| Package | `pickfair_control_api` **1.2.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01e` di pickfair-mcp- (wheel deterministica: `scripts/build_control_api_wheel.py`) |
| Contratto | 1.2.0, schema hash `bafc77d9623e8af9e233fe71c38f0a34949d73f6ebd0b627b4ce2498c9361528` |
| Scope del core | `pf_api2_control_api_finance_reads` (8 file = diff; registro toccato solo nella propria voce, verificato con `scripts/guardrail_check.py`) |

La patch non è pubblicata in questo repository (codice di Pickfair-nogui): viaggia tramite l'owner;
qui c'è solo la sua impronta. MCP-01d resta invariato: questa è una patch successiva, non una modifica.

## 2. Cosa cambia nel core

| File | Modifica |
|---|---|
| `control_api/views.py` | `account_view`, `exposure_view` (+ helper); nessuna modifica alle viste esistenti |
| `control_api/bridge.py` | due provider in più; pin a 1.2.0 / `bafc77d9…` |
| `tests/control_api/test_finance_views.py` | 22 test su runtime reale (costruito e avviato in SIM) |
| `tests/control_api/test_side_effects.py` | le prove di assenza di effetti e di non-attesa includono le nuove viste |
| `guardrails/mutation_catalog.json` | +10 mutazioni nell'area `control_api` (24 in totale) |
| `docs/control_api.md`, `CHANGELOG.md`, `.guardrails/allowed_scope.json` | documentazione e scope |

Fonti lette (solo letture pure, verificate sul codice): `RiskDesk.debug_snapshot()`,
`RiskDesk.cash_basis()`, `RuntimeController._account_snapshot` (ultimo snapshot già registrato, nessuna
nuova lettura dell'exchange), `RoserpinaMoneyManagement.determine_desk_mode` (stessi argomenti di
`_desk_mode()`), `TableManager.snapshot()` / `total_exposure()`, `RuntimeController._active_recovery_count()`.
Escluse perché NON pure: `get_status()`, `pending_exposure()` (pota i tombstone),
`read_funds_for_controller_entry()` (rete), `SimulationBroker.snapshot()` (cache interne),
`duplication_guard.snapshot()` (eviction TTL).

**Lock.** `bankroll`+`cash` nella stessa acquisizione del lock del RiskDesk, `tables`+`total_exposure`+
`recovery` in quella del lock dei tavoli, con attesa massima 0,25 s: se il runtime tiene il lock più a
lungo le sezioni risultano indisponibili, la lettura non blocca mai il motore. Il ponte usa
`RiskDesk._lock` (attributo privato) perché il RiskDesk non espone un accessor come
`TableManager.locked()`: se preferisci, un accessor pubblico è una modifica di una riga.

## 3. Evidenze (clone git integro, Python 3.11, base + MCP-01d + MCP-01e)

| Prova | Esito |
|---|---|
| `tests/control_api/` (viste, effetti, lock, launcher, processo reale) | 90 test (68 MCP-01d, aggiornati per le nuove viste, + 22 MCP-01e): esito nel messaggio di handoff |
| Mutazioni `control_api` (`run_mutation_guardrails.py --fail-under 100`) | 24/24 KILLED, GATE PASS |
| E2E fra processi (MCP reale ⇄ Control API ⇄ RuntimeController in SIM), `tests/crossrepo` | 9/9, su 3 esecuzioni |
| Applicazione: `ada40765` + patch 01d + patch 01e | `git apply --check` pulito; albero identico al clone verificato |
| Regressione completa del core | vedere il messaggio di handoff (SHA e conteggi) |

## 4. Verifica e rollback (lato Claude B)

```bash
sha256sum -c core_bridge_mcp01e.patch.sha256
git apply --check core_bridge.patch && git apply core_bridge.patch            # MCP-01d prima
git apply --check core_bridge_mcp01e.patch && git apply core_bridge_mcp01e.patch
pip install --no-deps --no-index --require-hashes --find-links <dir wheel 1.2.0> -r requirements-control-api.txt
python -m pytest -q tests/control_api
python scripts/run_mutation_guardrails.py --module control_api.views --module control_api.bridge --module control_api.launcher --fail-under 100
PICKFAIR_CORE_PATH=<core> PICKFAIR_CORE_PYTHON=<py> python -m pytest -q tests/crossrepo   # dal repo MCP, branch 01e
```

Rollback: `git apply -R core_bridge_mcp01e.patch` riporta esattamente a MCP-01d (pin 1.1.0). Senza
`--control-api-port` il core si comporta in modo identico con o senza patch.

## 5. Stato

`NOT_CERTIFIED`. Mancano review indipendente, integrazione e verifica finale di Claude B. Una 1.1.0
installata con questa patch non parte (`CONTRACT_PIN_MISMATCH`), e viceversa: versioni allineate o
nessuna Control API.
