# Handoff a Claude B — MCP-01m: trailing (F-03), percentuali F-02, impostazioni non valide F-18

Da: Claude C · Per: Claude B · 05/11/2026 · `Roadmap-Card: F-03`. **Preparato offline, NON integrabile finché F-03
(`claude/d-f03-trailing-stop`, che contiene F-02 e F-04) non è su `main`.** Verificato sulla fusione locale con
`65a84f56`; lo head attuale di D `b2bf8ab` non cambia `core/`, `services/`, `cashout_router.py`, `database.py`
(solo la fusione di `main`). Dipende da MCP-01d … MCP-01l, MCP-SEC-01, MCP-01i r2. Mandato owner del 05/11/2026, priorità 2.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01m.patch`, 11 file, +467/−33, SHA-256 `0c877b9aac0c824224ca01d226d6d8ed8d6648e19f06d13c42a0c3bdd6bb83cb` |
| Base della patch | base di MCP-01i r2 + fusione di F-03 di D |
| Package | `pickfair_control_api` **1.11.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01m-trailing` |
| Contratto | 1.11.0, schema hash `419e727980c52f57d91d2392289520384c5733cca37efd57b892736058366fa1` |
| Scope del core | `pf_api11_control_api_trailing` |

## 2. Cosa espone

Vedi `docs/contract_v1.md` (MCP-01m): trailing per tavolo, trigger `TRAILING_STOP`, percentuali F-02 e
`invalid_persisted` F-18 in `get_config`, protezione `config_validity`, `resolve_git_sha` nei worktree.

## 3. Evidenze

| Prova | Esito |
|---|---|
| Test core nuovi (`test_trailing_view.py`, logica reale `core.trailing_stop`, valore persistito illeggibile reale per F-18) | 10 passed; `tests/control_api` 235 passed |
| Mutazioni `control_api` | 111/111 KILLED, GATE PASS (primo giro: 2 NOT_APPLICABLE di 01h/01j per righe cambiate da 01m, riallineate) |
| Mutanti critici MCP Y01–Y07 | 7/7 KILLED (primo giro 2/7: mancavano i test unitari del modello Trailing, aggiunti) |
| `resolve_git_sha` nei worktree | RED 2/4 → GREEN 4/4 |
| E2E fra processi col core con F-03 | 17/17, su 3 esecuzioni (picco persistito reale, soglia del core) |
| Suite MCP | 1860 passed, 18 skipped |
| Regressione completa del core (base + F-03) | 12287 passed, **1 failed preesistente**: `test_il_catalogo_reale_e_applicabile_e_copre_le_aree_critiche` per `recovery_live_bets_inverted` e `f01_tp_ignores_depth`, identico sul branch di D da solo (`b2bf8ab`); difetto dello stack F-13b/F-02, preso in carico da Claude B. Nessuna mutazione `control_api` non applicabile |
