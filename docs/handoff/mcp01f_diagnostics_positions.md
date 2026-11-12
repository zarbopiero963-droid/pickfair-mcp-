# Handoff a Claude B — MCP-01f: diagnostica, protezioni finanziarie e posizioni

Da: Claude C · Per: Claude B · 04/11/2026 · **dipende da MCP-01d e MCP-01e**.
Proposta di patch: integrazione, tempi e PR restano di Claude B, dopo #608, #606, MCP-01d e MCP-01e,
con una PR indipendente e safety-critical. MCP-01d ed MCP-01e restano invariati.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01f.patch`, 9 file, +1147/−6, SHA-256 in `core_bridge_mcp01f.patch.sha256` |
| Base della patch | `main` `ada40765` + patch MCP-01d (`505f579c…`) + patch MCP-01e (`39833bc3…`) |
| Package | `pickfair_control_api` **1.3.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01f` (wheel deterministica) |
| Contratto | 1.3.0, schema hash `887154aa1c8e44688caa80d0850a12668ad0f4bf64d79b5926432156b60411b8` |
| Scope del core | `pf_api3_control_api_diagnostics_positions` (9 file = diff; `guardrail_check` PASS) |

## 2. Cosa cambia nel core

| File | Modifica |
|---|---|
| `control_api/views.py` | `status_view` aggiunge `engine` e `protections`; nuova `positions_view`; `decimal_str` (Decimal canonico) |
| `control_api/bridge.py` | provider `positions`; pin 1.3.0 / `887154aa…` |
| `tests/control_api/test_diagnostics_views.py` | 35 test su runtime reale (costruito e avviato in SIM) |
| `tests/control_api/test_side_effects.py`, `test_views_real_runtime.py` | `keepalive_status()` ammessa (lettura locale); controllo del testo libero reso preciso (le chiavi fisse `cashout_*` contengono la parola) |
| `guardrails/mutation_catalog.json` | +13 mutazioni (37 nell'area `control_api`) |
| `docs/control_api.md`, `CHANGELOG.md`, `.guardrails/allowed_scope.json` | documentazione e scope |

Letture usate (tutte verificate pure): `TradingEngine.readiness()` e `risk_gate_wired`; attributi del
`BetfairService` (`connected`, `simulation_mode`, cliente, `last_error` solo come presenza) e
`keepalive_status()`; `streaming_feed.status()`; `runtime_io_snapshot()`; `bus.pressure_snapshot()`;
contatori `_cashout_inflight`, `_cashout_uncertain`, `direct_unmatched_bet_ids`; per le protezioni le
regole del core chiamate direttamente (`_is_kill_switch_active`, `_session_loss_block_reason`,
`risk_stop.exposure_stop_reason`, `validators.risk_pct_reason`, `_entry_funds_reason(…, 0.0)`,
`determine_desk_mode`, `loss_limits.persist_failed`); per le posizioni gli attributi Decimal del
`PositionLedger` sotto il lock del `PnLEngine`. Escluse: `CircuitBreaker.snapshot()/is_open()` (OPEN →
HALF_OPEN), `_loss_block_reason()` (può scrivere), `duplication_guard.snapshot()`, `get_status()`.

**Proposte per il core (decide Claude B, nessuna modifica fatta):**
1. `PositionLedger.snapshot()` converte in float: un `snapshot_decimal()` pubblico eviterebbe al ponte
   di leggere attributi privati (`_open_size`, `_avg_entry_price()`, `_residual_exposure_liability()`).
2. `RiskDesk` senza accessor del lock (già segnalato per MCP-01e).
3. La salute del `TradingEngine` è calcolata solo all'avvio: un refresh esplicito darebbe una
   diagnostica attuale (oggi dichiarata `evaluated_at = ENGINE_START`).
4. `_recovery_persist_failed` nasce solo alla prima scrittura (già segnalato): la protezione
   `recovery_state` resta `UNKNOWN` dopo un avvio pulito.

## 3. Evidenze (clone git integro, Python 3.11, base + 01d + 01e + 01f)

| Prova | Esito |
|---|---|
| RED: test nuovi contro il ponte di MCP-01e | errore di raccolta (viste assenti) |
| `tests/control_api/` | 125 passed |
| Mutazioni `control_api` (`--fail-under 100`) | 37/37 KILLED, GATE PASS |
| E2E fra processi (`tests/crossrepo`, MCP reale ⇄ Control API ⇄ RuntimeController SIM) | 10/10, su 3 esecuzioni |
| Regressione completa del core (`211374dc`, `pytest -n 4 tests`) | 11906 passed, 0 failed, 16 skipped, 56 xfailed |

## 4. Verifica e rollback

```bash
sha256sum -c core_bridge_mcp01f.patch.sha256
git apply core_bridge.patch && git apply core_bridge_mcp01e.patch && git apply core_bridge_mcp01f.patch
python -m pytest -q tests/control_api
python scripts/run_mutation_guardrails.py --module control_api.views --module control_api.bridge --module control_api.launcher --fail-under 100
```
Rollback: `git apply -R core_bridge_mcp01f.patch` riporta esattamente a MCP-01e (pin 1.2.0).

## 5. Stato e rischi residui

`NOT_CERTIFIED`. Rischi: salute del motore non aggiornata dopo l'avvio; freschezza dei fondi = gate
attuale (120 s), da riallineare a F-16 (Claude D); stato negoziabile del mercato `UNAVAILABLE` fino a
F-23; letture di attributi privati del ledger (proposta 1); importi di `get_account`/`get_exposure`
ancora float (1.2.0).
