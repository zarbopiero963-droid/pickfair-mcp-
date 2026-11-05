# Handoff a Claude B — MCP-01j: `GET /v1/config` in sola lettura, segreti oscurati

Da: Claude C · Per: Claude B · 05/11/2026 · **dipende da MCP-01d … MCP-01h**.
Mandato owner del 05/11/2026 (ORDINE OWNER: completamento MCP + Control API, priorità 1): «sola lettura,
segreti e credenziali sempre oscurati, nessun token o certificato, nessuna modifica, contratto
versionato, test negativi contro fughe». Route già approvata (`GET /v1/config`), nessuna route K3.
Proposta di patch: per decisione owner la corsia d'integrazione va prima alle correzioni P0/P1 di
Claude D e a #608/#606; MCP-01j resta in coda come gli incrementi precedenti. `Roadmap-Card: none`.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01j.patch`, 8 file, +521/−2, SHA-256 `85fcfd7687d7cfd9e9cfaff9825faf2aabf4cd28febc1e842462d58cc61cd8de` |
| Base della patch | `main` `ada40765` + patch MCP-01d, 01e, 01f, 01g, 01h |
| Package | `pickfair_control_api` **1.6.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01j-config` |
| Contratto | 1.6.0, schema hash `9c1aefb5c9b169f8513ceccdd4766d5a9330429bfa94aa9dc30e8334dafd5ed0` |
| Scope del core | `pf_api6_control_api_config` (8 file = diff) |

## 2. Cosa cambia nel core

| File | Modifica |
|---|---|
| `control_api/views.py` | `config_view`: allowlist `CONFIG_KEYS` (42 chiavi di `RoserpinaConfig`), `OPTIONAL_CONFIG_KEYS` (16), un solo riferimento a `rc.config` copiato con `vars()`, valori SET/NOT_SET/INVALID; nomi fuori allowlist solo per nome in `unlisted`, nomi sensibili (`core.redaction.is_sensitive_key` + `SENSITIVE_NAME_FRAGMENTS`) o non canonici solo contati in `redacted` |
| `control_api/bridge.py` | provider `config`; pin 1.6.0 / `9c1aefb5…` |
| `tests/control_api/test_config_view.py` | test nuovi: valori reali, reload, INVALID mai zero, campo mancante, bool≠int, config assente, credenziali Betfair/Telegram nel DB mai esposte, campi nuovi solo per nome, nomi sensibili mai elencati, tetto di `unlisted`, DB/config/bus invariati, contratto del server |
| `tests/control_api/test_side_effects.py` | `/v1/config` nelle 50 letture senza effetti e nel martellamento concorrente |
| `guardrails/mutation_catalog.json` | +13 mutazioni (75 nell'area `control_api`) |
| `docs/control_api.md`, `CHANGELOG.md`, `.guardrails/allowed_scope.json` | documentazione e scope |

Nessuna lettura di `settings_service`, `BetfairConfig`, Telegram, certificati o della tabella `settings`:
la vista legge solo l'oggetto `RoserpinaConfig` già in memoria. Nessun lock, nessuna scrittura.

## 3. Evidenze (clone integro, Python 3.11, base + 01d … 01j)

| Prova | Esito |
|---|---|
| RED: test nuovi contro il ponte di MCP-01h | errore di raccolta (`config_view` assente) |
| `tests/control_api/` | 180 passed |
| Mutazioni `control_api` (`--fail-under 100`) | 75/75 KILLED, GATE PASS; il primo giro ha dato 73/75: sopravvissuti `cap_config_missing_as_not_set` e `cap_config_int_bool_accepted`, lacune reali dei test, chiuse con due test e campagna completa rieseguita |
| E2E fra processi (`tests/crossrepo`, core reale in SIM, credenziali reali salvate nel DB) | 13/13, su 3 esecuzioni; nessun segreto nella risposta, DB/bus/stato/saldo invariati |
| Suite MCP | 1720 passed, 14 skipped; un fallimento sotto carico di `test_journal_kill` (stress SIGKILL, non toccato) rieseguito 4/4 PASS con e senza la modifica |
| Mutanti critici MCP, serie K (`get_config`) | 8/8 KILLED |
| Regressione completa del core | in corso al momento della consegna; esito nel commento su #37 |

## 4. Verifica e rollback

```bash
sha256sum -c core_bridge_mcp01j.patch.sha256
# dopo le patch 01d … 01h:
git apply --check core_bridge_mcp01j.patch && git apply core_bridge_mcp01j.patch
python -m pytest -q tests/control_api
```
Rollback: `git apply -R core_bridge_mcp01j.patch` riporta esattamente a MCP-01h (pin 1.5.0).

## 5. Stato e rischi residui

`NOT_CERTIFIED`, `NOT_INTEGRATED`. Limiti dichiarati: solo `RoserpinaConfig` (l'inventario completo
delle chiavi GUI/runtime/persistite, CAP-CFG-08, resta fuori); un campo nuovo del core (es. F-02 se
aggiunge impostazioni SL/TP) compare solo per nome finché il contratto non lo aggiunge all'allowlist.
La scrittura (`patch_config`) resta solo design e non è esposta.
