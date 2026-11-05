# Handoff a Claude B — MCP-01k: compatibilità del ponte con P0 e F-16 di Claude D

Da: Claude C · Per: Claude B · 05/11/2026 · **dipende da MCP-01d … MCP-01j**. `Roadmap-Card: F-14` (rende
osservabili correttamente gli ordini AMBIGUOUS del P0) · mandato owner del 05/11/2026, punto 3.
Proposta di patch, in coda come gli incrementi precedenti: le correzioni P0/P1 di Claude D e #608/#606 hanno
la precedenza. È integrabile anche **prima** del fix P0 (sul `main` attuale non cambia nulla di visibile per le
righe AMBIGUOUS senza report) e prima di F-16 (sul `main` il limite resta 120 s).

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01k.patch` (vedi `core_bridge_mcp01k.patch.sha256`) |
| Base della patch | `main` `ada40765` + patch MCP-01d … 01h e 01j |
| Contratto | 1.7.0 (vedi sezione 3) |
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

Compilate in fondo alla consegna (sezione «Esiti»).

## 4. Rapporto di compatibilità

`docs/handoff/compat_claude_d_20261105.md`: esito per branch di D (P0, betId, F-02, F-03, F-04, F-16, F-23,
streaming, settlement) con le prove riproducibili.
