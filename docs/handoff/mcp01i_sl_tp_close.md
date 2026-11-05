# Handoff a Claude B — MCP-01i: stato della chiusura SL/TP (dipende da F-04)

Da: Claude C · Per: Claude B · 05/11/2026 · mandato owner del 05/11/2026, punto 2. `Roadmap-Card: F-04`.
**Preparato offline, NON integrabile finché F-04 (`claude/d-f04-sl-tp-close` @ `2d0cf4ca`) non è su `main`.**
Dipende da MCP-01d … MCP-01k. Nessuna route nuova: estensione di `GET /v1/exposure`.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01i.patch`, 8 file, +581/−4, SHA-256 `ba7340e65b1c6fe06f8a912bcf5c0737401237b396bc5ddbe8e96d9a79f0f99b` |
| Base della patch | `main` `ada40765` + patch MCP-01d … 01h, 01j, 01k + i tre commit di F-04 fino a `2d0cf4ca` (codice identico al branch di D, verificato file per file) |
| Package | `pickfair_control_api` **1.8.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01i-sltp-close` |
| Contratto | 1.8.0, schema hash `3928ea8b28215476e0ad84621bf7b7e2e750c0564b49844546261da42818268a` |
| Scope del core | `pf_api8_control_api_sl_tp_close` (8 file = diff) |

## 2. Cosa espone (solo dati persistiti)

Tavolo, posizione (mercato, selezione, lato, betId), evento SL/TP, stato della chiusura (CLAIMED / ROUTED /
NOT_EXECUTED / UNCERTAIN, illeggibile UNKNOWN), ritentabile come decide il core, dettaglio/blocco come codice,
ordini della posizione (parzialmente abbinati, in riconciliazione, ambigui), esposizione residua dal tavolo che
porta ancora la posizione, hedge della chiusura legati per id di richiesta (`cashout_request_ids`, F-04 @ `2d0cf4ca`). Dettagli e limiti in `docs/contract_v1.md` (MCP-01i).

## 3. Evidenze

| Prova | Esito |
|---|---|
| RED: test nuovi contro il ponte di MCP-01k (su F-04) | 8 falliti su 9 (sezione assente) |
| Test sulla catena reale di F-04 (scenari di D: tre tavoli, SL instradato, SL non eseguito, TP, record illeggibili, record di un'altra posizione, tavolo riassegnato, lock dei tavoli occupato, core senza F-04, DB invariato, contratto) | 12 passed; `tests/control_api` + accettazione F-04: 271 passed |
| Legame hedge → chiusura | via `cashout_request_ids` (F-04 @ `2d0cf4ca`, aggiunto da D su richiesta del 05/11): la sola riga d'hedge della posizione A, mai quelle di altre chiusure; richieste senza riga in `not_in_ledger` |
| Mutazioni `control_api` (`--fail-under 100`) | 90/90 KILLED, GATE PASS. Primo giro 87/89 + 1 NOT_APPLICABLE: sopravvissuti `cap_close_ref_not_checked` e `cap_close_residual_any_table` (lacune reali, due test aggiunti); NOT_APPLICABLE `cap_busy_as_empty` per la gestione «DB occupato» duplicata, unificata in `_ro_transaction` |
| E2E fra processi | 15/15, su 3 esecuzioni (record persistito con le funzioni di F-04 nel core reale) |
| Suite MCP | 1762 passed, 16 skipped; mutanti critici L01–L08 8/8 KILLED |
| Regressione completa del core (`pytest -n 4 tests`, base + F-04 + 01i) | 12052 passed, 0 failed, 16 skipped, 56 xfailed. Una prima esecuzione aveva dato 1 fallito (nome non registrato), non ripetuto in due esecuzioni complete successive |
