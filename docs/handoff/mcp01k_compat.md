# Handoff a Claude B — MCP-01k: compatibilità del ponte con P0 e F-16 di Claude D

Da: Claude C · Per: Claude B · 05/11/2026 · **dipende da MCP-01d … MCP-01j**. `Roadmap-Card: F-14` (rende
osservabili correttamente gli ordini AMBIGUOUS del P0) · mandato owner del 05/11/2026, punto 3.
Proposta di patch, in coda come gli incrementi precedenti: le correzioni P0/P1 di Claude D e #608/#606 hanno
la precedenza. È integrabile anche **prima** del fix P0 (sul `main` attuale non cambia nulla di visibile per le
righe AMBIGUOUS senza report) e prima di F-16 (sul `main` il limite resta 120 s).

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01k.patch`, 7 file, +212/−4, SHA-256 `7e29ca8b7f1b33547a9f6274f304c6d6dda550eef2430f22ab27298c01562bdc` |
| Base della patch | `main` `ada40765` + patch MCP-01d … 01h e 01j |
| Package | `pickfair_control_api` **1.7.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01k-compat` |
| Contratto | 1.7.0, schema hash `94982a9c9de0c62360d98c018190b4fad8ae71006fc93bcd339b85258fd6a6fd` |
| Scope del core | `pf_api7_control_api_compat` (7 file = diff) |

## 2. Cosa cambia nel core

| File | Modifica |
|---|---|
| `control_api/views.py` | `UNCONFIRMED_STATUSES` (AMBIGUOUS, HEDGE_AMBIGUOUS, INFLIGHT, HEDGE_PENDING): per queste righe nessun importo dal report; `_funds_limit`: accessore `funds_max_age_s()` se esiste, null con la soglia F-16 senza accessore, altrimenti il TTL attuale |
| `control_api/bridge.py` | pin 1.7.0 |
| `tests/control_api/test_compat_views.py` | forme P0 di D su tutte le righe incerte, righe confermate invariate, limite dei fondi nei tre casi, contratto del server |
| `guardrails/mutation_catalog.json` | +4 mutazioni (79 nell'area `control_api`) |
| `docs/control_api.md`, `CHANGELOG.md`, `.guardrails/allowed_scope.json` | documentazione e scope |

## 3. Evidenze

| Prova | Esito |
|---|---|
| RED sul ponte 01j (test nuovi) | 10 falliti su 25: importi non confermati esposti su AMBIGUOUS/HEDGE_AMBIGUOUS/INFLIGHT/HEDGE_PENDING; limite 120 con la soglia F-16 |
| Sonda sulla catena reale del branch P0 di D (fusione locale) | RED `('5', None, None)` col ponte 01j → GREEN 4/4 col ponte 01k |
| Sonda sul codice reale di F-16 (fusione locale) | RED `'120' is None` col ponte 01j → GREEN col ponte 01k |
| `tests/control_api/test_compat_views.py` | 25 passed |
| Mutazioni `control_api` (`--fail-under 100`) | 79/79 KILLED, GATE PASS |
| E2E fra processi | 14/14, su 3 esecuzioni (nuovo: riga AMBIGUOUS nella forma P0 sul core reale) |
| Suite MCP | 1733 passed, 15 skipped; mutante critico O12 KILLED |
| Regressione completa del core (`pytest -n 4 tests`) | 11986 passed, 0 failed, 16 skipped, 56 xfailed |

## 3-bis. Vincolo per la PR F-14 (richiesta di Claude B, 05/11)

Il fix P0 conserva sulla riga AMBIGUOUS la risposta senza esito, che può contenere `sizeMatched`. Vincolo
per chi legge il ledger (Control API, F-14 e ogni consumatore): per AMBIGUOUS, HEDGE_AMBIGUOUS, INFLIGHT e
HEDGE_PENDING gli importi del report **non sono dati confermati** e non vanno esposti né usati come
abbinato/residuo; il betId resta l'identità della riconciliazione.

## 4. Rapporto di compatibilità

`docs/handoff/compat_claude_d_20261105.md`: esito per branch di D (P0, betId, F-02, F-03, F-04, F-16, F-23,
streaming, settlement) con le prove riproducibili.
