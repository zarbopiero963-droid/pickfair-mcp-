# Handoff a Claude B — MCP-01g: lettura degli ordini

Da: Claude C · Per: Claude B · 04/11/2026 · **dipende da MCP-01d, MCP-01e, MCP-01f**.
Proposta di patch. Integrazione, tempi e PR restano di Claude B; l'ordine dei merge rispetto alle
correzioni finanziarie P0 lo decide l'owner (indicazione inoltrata con `pfab-c-20261104-request-priority-001`).

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01g.patch`, 8 file, +838/−2, SHA-256 in `core_bridge_mcp01g.patch.sha256` |
| Base della patch | `main` `ada40765` + patch MCP-01d, MCP-01e, MCP-01f |
| Package | `pickfair_control_api` **1.4.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01g` |
| Contratto | 1.4.0, schema hash `9244f574ef1ac29f07ab22a7c81f33fcbdf521f44881f444a100c823f93d80c6` |
| Scope del core | `pf_api4_control_api_orders` (8 file = diff; `guardrail_check` PASS) |

## 2. Cosa cambia nel core

| File | Modifica |
|---|---|
| `control_api/views.py` | `orders_view`: ledger `orders` con connessione SQLite separata in sola lettura (`mode=ro` + `PRAGMA query_only`), una transazione, attesa massima 0,25 s; mappa esplicita degli stati; betId nelle forme di `_open_order_candidates`; ruoli da `core/hedge_ref.py`; registro delle ambiguità; confronto col broker SIM per attributi |
| `control_api/bridge.py` | provider `orders`; pin 1.4.0 / `9244f574…` |
| `tests/control_api/test_orders_view.py` | 20 test su ledger e runtime reali (mappa degli stati, AMBIGUOUS, betId come la riconciliazione, PARTIAL/STALE/UNKNOWN/UNAVAILABLE, concorrenza, le due barriere di scrittura una per una, DB invariato) |
| `tests/control_api/test_side_effects.py` | `/v1/orders` incluso; il confronto del DB esclude solo `-shm` (indice WAL: ogni lettore SQLite vi scrive il marcatore di lettura, nessun dato) |
| `guardrails/mutation_catalog.json` | +14 mutazioni (51 nell'area `control_api`) |
| `docs/control_api.md`, `CHANGELOG.md`, `.guardrails/allowed_scope.json` | documentazione e scope |

**Compatibilità con la correzione P0 di Claude D (AMBIGUOUS / betId)**, verificata sulle informazioni
di Claude D (branch `claude/pickfair-core-audit-slu9su` @ `47e2aaa`, letto in sola lettura): stati
di `orders` invariati; un placeOrders 2xx senza esito diventa AMBIGUOUS con `ambiguity_reason =
SUBMIT_UNKNOWN`; il betId, se c'era, resta nel `response_json` sotto `result.instructionReports[0]`;
chiave di `ambiguity_snapshot()` invariata. Un test riproduce esattamente quella forma (betId trovato,
testo d'errore mai esposto; senza betId resta null). Un nuovo stato del core finisce come `UNKNOWN`
finché la mappa non viene estesa in una nuova versione del contratto.

**Divergenza trovata nel core (segnalata a Claude B e Claude D):** esistono due estrattori del betId
con precedenze diverse. `Database._order_bet_id` restituisce `""` per `{"result": {"betId": "222"}}`
(che `_open_order_candidates` riconosce) e preferisce il betId diretto a quello del primo report
(`{"betId": "1", "instructionReports": [{"betId": "2"}]}` → `"1"` contro `"2"` della
riconciliazione). Il ponte segue la riconciliazione (identità usata al riavvio) e un test confronta i
due risultati. Proposta: un solo helper pubblico, usato da entrambi i percorsi e dal ponte.

**Altre proposte (decide Claude B):** la colonna `finalized` usata in modo uniforme dai percorsi
terminali. Branch di Claude D che toccano i dati letti (tutti non mergiati): `d-f23-market-tradable`
(DENIED con `reason` `RISK_MARKET_NOT_TRADABLE`, già coperto: DENIED → REJECTED).

## 3. Evidenze (clone integro, Python 3.11, base + 01d + 01e + 01f + 01g)

| Prova | Esito |
|---|---|
| RED: test nuovi contro il ponte di MCP-01f | errore di raccolta (vista assente) |
| `tests/control_api/` | 145 passed (125 precedenti + 20 MCP-01g) |
| Mutazioni `control_api` (`--fail-under 100`) | 51/51 KILLED, GATE PASS (le due barriere di scrittura sopravvivevano finché il test le provava solo insieme: ora ognuna ha il suo test) |
| E2E fra processi (`tests/crossrepo`) | 11/11, su 3 esecuzioni |
| Regressione completa del core (`1bcfd7e1`, `pytest -n 4 tests`) | 11926 passed, 0 failed, 16 skipped, 56 xfailed |

## 4. Verifica e rollback

```bash
sha256sum -c core_bridge_mcp01g.patch.sha256
git apply core_bridge.patch && git apply core_bridge_mcp01e.patch \
  && git apply core_bridge_mcp01f.patch && git apply core_bridge_mcp01g.patch
python -m pytest -q tests/control_api
python scripts/run_mutation_guardrails.py --module control_api.views --module control_api.bridge --module control_api.launcher --fail-under 100
```
Rollback: `git apply -R core_bridge_mcp01g.patch` riporta esattamente a MCP-01f (pin 1.3.0).

## 5. Stato e rischi residui

`NOT_CERTIFIED`. Rischi: ordini LIVE sull'exchange non confrontati (nessuno stato in memoria, la
rete è vietata alle letture: `broker_view = NOT_CHECKED`); esposizione per ordine non riportata (non è
nel ledger); limite di 500 righe (oltre: PARTIAL/TRUNCATED); allineamento alla correzione P0 di Claude D
da verificare quando il suo codice è disponibile.
