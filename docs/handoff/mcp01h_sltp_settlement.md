# Handoff a Claude B — MCP-01h: SL/TP per tavolo, settlement, barriere di cashout

Da: Claude C · Per: Claude B · 04/11/2026 · **dipende da MCP-01d … MCP-01g**.
Proposta di patch. Per decisione owner (`pfab-b-20261104-response-priority-001`) la corsia d'integrazione
va prima alle correzioni P0/P1 di Claude D: MCP-01h resta in coda come gli incrementi precedenti.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01h.patch`, 10 file, +519/−4, SHA-256 in `core_bridge_mcp01h.patch.sha256` |
| Base della patch | `main` `ada40765` + patch MCP-01d, 01e, 01f, 01g |
| Package | `pickfair_control_api` **1.5.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01h` |
| Contratto | 1.5.0, schema hash `3878844a9518a6778a871d6cba054c5778820e2b5d20f3155d355e944f8ff070` |
| Scope del core | `pf_api5_control_api_sltp_settlement` (10 file = diff; `guardrail_check` PASS) |

## 2. Cosa cambia nel core

| File | Modifica |
|---|---|
| `control_api/views.py` | `_sl_tp` (dal `meta` del tavolo, solo chiavi SL/TP), sezione `settlement` della riconciliazione (conteggi da `settlement_effects` e `cycle_recovery_checkpoints` in sola lettura, `_unrecorded_settlements` e `_held_batch_ids` sotto i loro lock, settlement del broker SIM), `cashout_barriers` nelle code |
| `control_api/bridge.py` | pin 1.5.0 / `a1cec77e…` |
| `tests/control_api/test_settlement_sltp_views.py` | 11 test (main: NOT_ARMED; forma di F-02: ARMED; TRIGGERED/UNKNOWN; settlement; lock occupato; DB illeggibile; DB invariato; contratto del server) |
| `test_diagnostics_views.py`, `test_finance_views.py`, `test_views_real_runtime.py` | attese aggiornate per i campi nuovi (barriere, `sl_tp`, `settlement`) |
| `guardrails/mutation_catalog.json` | +11 mutazioni (62 nell'area `control_api`) |
| `docs/control_api.md`, `CHANGELOG.md`, `.guardrails/allowed_scope.json` | documentazione e scope |

## 3. Constatazione sul core (per Claude B e Claude D, nessuna modifica fatta)

Sul `main` (`ada40765`) **nessun percorso di produzione scrive `stop_loss`/`take_profit` nel `meta` dei
tavoli** (percorso del segnale e auto-next: `runtime_controller.py:4731-4741`, `:8143-8154`), quindi
`_monitor_sl_tp_trailing` non agisce mai; il trailing non ha logica. Il branch di Claude D
`keep/f02-sl-tp-path-20261103` (`80b00909`, non integrato) introduce gli importi nel `meta`
(`_sl_tp_meta`); `claude/d-f04-sl-tp-close` (`aa7959a8`) la chiusura del solo tavolo. MCP-01h riporta
lo stato reale (NOT_ARMED) e la forma di F-02 è coperta da un test.

## 4. Evidenze (clone integro, Python 3.11, base + 01d … 01h)

| Prova | Esito |
|---|---|
| RED: test nuovi contro il ponte di MCP-01g | 10 falliti su 11 |
| `tests/control_api/` | 156 passed |
| Mutazioni `control_api` (`--fail-under 100`) | 62/62 KILLED, GATE PASS |
| E2E fra processi (`tests/crossrepo`) | 12/12, su 3 esecuzioni |
| Regressione completa del core (`0a894c4d`, `pytest -n 4 tests`) | 11937 passed, 0 failed, 16 skipped, 56 xfailed |

## 5. Verifica e rollback

```bash
sha256sum -c core_bridge_mcp01h.patch.sha256
# dopo le patch 01d, 01e, 01f, 01g:
git apply --check core_bridge_mcp01h.patch && git apply core_bridge_mcp01h.patch
python -m pytest -q tests/control_api
```
Rollback: `git apply -R core_bridge_mcp01h.patch` riporta esattamente a MCP-01g (pin 1.4.0).

## 6. Stato e rischi residui

`NOT_CERTIFIED`. Rischi: lo stato SL/TP diventa significativo solo con F-02 integrato; nessuno storico
dei cashout nel core oltre alle righe hedge e agli `audit_events` (non esposti: testo libero); storico P/L
dei settlement con importi non ancora esposto (richiede una decisione di route).
