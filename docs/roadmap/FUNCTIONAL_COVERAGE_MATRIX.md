# FUNCTIONAL COVERAGE MATRIX — catalogo delle capacità Pickfair

Catalogo **v0.1-DRAFT** · 03/11/2026 · baseline Pickfair-nogui `7a70062`, pickfair-mcp- `36bbef1`.

Catena tracciata: **CORE → CONTROL API → MCP → TEST → EVIDENZA → CERTIFICAZIONE**.
Gli ID `CAP-<AREA>-NN` sono **permanenti**: una capacità non si cancella e non si rinumera; si chiude solo
con uno stato motivato (`RETIRED`, `OUT_OF_SCOPE`) approvato dall'owner.

## 1. Come leggere la matrice

**Stato del catalogo** (capacità end-to-end, cioè raggiungibile da MCP sul core reale):

| Stato | Significato |
|---|---|
| `IMPLEMENTED` | core + Control API + MCP reali, collegati (oggi: nessuna) |
| `NOT_IMPLEMENTED` | il core la possiede (anche parzialmente); mancano Control API e/o MCP |
| `CORE_BLOCKED` | il core non la possiede o non è affidabile: è una **dipendenza**, non si simula |
| `OWNER_BLOCKED` | richiede una decisione owner (conflitti K1–K8 della master) |
| `RETIRED` | superata da una decisione owner, con riferimento |
| `OUT_OF_SCOPE` | esclusa da una decisione owner, con riferimento; non conta nel denominatore |

**Tre livelli di readiness** (colonna `L1/L2/L3`):

- **L1 Core:** `P` presente, non certificato · `F` fix mergiato su main, certificazione #586 da registrare ·
  `Pz` parziale · `A` assente · `V` da localizzare (primo passo della scheda) · `—` non applicabile.
- **L2 API/MCP:** `NO` · `SIM` solo adapter simulato (non vale come integrazione) · `SI` reale.
- **L3 Certificazione:** `NR` NOT_RUN · `PASS` · `FAIL` · `BLK` BLOCKED.

Una capacità è **COMPLETA** solo con L1, L2 e L3 tutti PASS / SI dove applicabili. Oggi: **0 complete**.

Le valutazioni L1 derivano da lettura statica del codice su `7a70062` e dal registro #586; **non sono
certificazioni**. «Fix mergiato» non significa certificato: il registro #586 richiede il PASS di Grok (K).

Endpoint: le 25 route approvate (pickfair-mcp- #1) sono scritte come `GET /v1/...`; le route **candidate**
non approvate sono `RC-nn` (§4) e richiedono ratifica owner (conflitto K3).

## 2. Catalogo

### 2.1 MET — Contratto, versioni, identità (16)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-MET-01 | Versione, capability, git SHA, schema hash | (nuovo) Control API | `GET /v1/meta` | `get_meta` | 004 · MCP-01a | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-MET-02 | Compat matrix e re-handshake a ogni riconnessione | MCP `policy/handshake.py` | `GET /v1/meta` | `get_meta` | 004 · MCP-01a/01d | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-MET-03 | Descrittore canonico e algoritmo di schema hash condiviso | (nuovo) | — | — | 003, 004 · PF-API-0 | CORE_BLOCKED | A/NO/NR |
| CAP-MET-04 | Errori tipizzati con codici fissi, mai testo upstream | MCP `errors.py` + Control API | tutte | tutti | 006 | NOT_IMPLEMENTED | A/SIM/NR |
| CAP-MET-05 | `request_id` generato dal MCP | MCP `journal/` | — | tutti | 006 · MCP-01b | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-MET-06 | `operation_id` e `correlation_id` dal core | (assente: 0 occorrenze) | tutte le mutazioni | comandi | 006 · PF-API-0 | CORE_BLOCKED | A/NO/NR |
| CAP-MET-07 | Catena request→operation→correlation→customer_ref→bet_id | `core/order_identity.py`, PR47 | `GET /v1/audit/{id}` | `get_audit_trail` | 007 · PR47 | CORE_BLOCKED | Pz/NO/NR |
| CAP-MET-08 | Idempotenza lato MCP (journal append-only, dedupe) | MCP `journal/store.py` | — | comandi | 006 · MCP-01b | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-MET-09 | Chiave di idempotenza fornita dal client (D-10) | (decisione tecnica) | mutazioni | comandi | 006 | OWNER_BLOCKED | A/NO/NR |
| CAP-MET-10 | Recovery MCP: `NOT_SENT` / `AMBIGUOUS`, mai replay | MCP `journal/` | — | — | 020 · MCP-01b/05c | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-MET-11 | Rifiuto campi extra, NaN, Inf, bool numerici | MCP `contract/parsing.py`; core PR27 | tutte | tutti | 006, 023 | NOT_IMPLEMENTED | Pz/SIM/NR |
| CAP-MET-12 | Retry solo per letture idempotenti | MCP `journal/retry.py` | letture | letture | 006 | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-MET-13 | Timeout configurati per chiamata | MCP + Control API | tutte | tutti | 006, 022 | NOT_IMPLEMENTED | A/SIM/NR |
| CAP-MET-14 | Stato operazione asincrona | (nuovo) registro operazioni | `GET /v1/operations/{id}` | `get_operation` | 006, 013 · MCP-02d | CORE_BLOCKED | A/NO/NR |
| CAP-MET-15 | Operazioni pendenti | (nuovo) | `GET /v1/operations?status=pending` | `list_pending_operations` | 013 · MCP-02d | CORE_BLOCKED | A/NO/NR |
| CAP-MET-16 | Provenienza `order_origin=MCP` | PF-API-0 | mutazioni | comandi | 004 · PF-API-0 | CORE_BLOCKED | A/NO/NR |

### 2.2 RT — Runtime, readiness, salute (11)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-RT-01 | Stato runtime STOPPED/ACTIVE/PAUSED/LOCKDOWN | `RuntimeController.get_status`, `RuntimeMode` | `GET /v1/status` | `get_status` | 008 · MCP-02a | NOT_IMPLEMENTED | P/NO/NR |
| CAP-RT-02 | Desk mode NORMAL/EXPANSION/DEFENSE/LOCKDOWN | `DeskMode`, `core/risk_desk.py` | `GET /v1/status` | `get_status` | 008, 011 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-RT-03 | Readiness SIM | `RuntimeController` | `GET /v1/status` | `get_status` | 008 · MCP-02a | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-RT-04 | Readiness LIVE e blocker | `evaluate_live_readiness`, `is_live_allowed` | `GET /v1/status` | `get_status` | 008 · MCP-02a | NOT_IMPLEMENTED | P/NO/NR |
| CAP-RT-05 | Readiness MCP-aware (Telegram non blocker se l'ingresso è MCP) | — | `GET /v1/status` | `get_status` | 008 · PF-API-0 | CORE_BLOCKED | A/NO/NR |
| CAP-RT-06 | Stato del deploy gate | `get_deploy_gate_status` | `GET /v1/status` | `get_status` | 008 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-RT-07 | Salute I/O e diagnostica runtime | `runtime_io_snapshot`, `observability/` | `GET /v1/status` | `get_status` | 008, 033 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-RT-08 | Autorità runtime e fencing | `core/runtime_authority.py`, PR32 | `GET /v1/status` | `get_status` | 008, 021 | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-RT-09 | Avvio del runtime (START) | `RuntimeController.start` | RC-01 | (candidato `start`) | 019 | OWNER_BLOCKED | P/NO/NR |
| CAP-RT-10 | Reset ciclo Roserpina | `reset_cycle` | RC-02 | (candidato) | 015 | OWNER_BLOCKED | P/NO/NR |
| CAP-RT-11 | Sincronizzazione catalogo su comando | `catalog_sync`, `CatalogSyncService` | RC-03 | (candidato) | 009 | OWNER_BLOCKED | P/NO/NR |

### 2.3 MOD — Modalità e switch (11)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-MOD-01 | Lettura modalità di esecuzione effettiva | `get_effective_execution_mode` | `GET /v1/status` | `get_status` | 008, 032 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-MOD-02 | Lettura modalità richiesta / transizione in corso | — | `GET /v1/status` | `get_status` | 032 | CORE_BLOCKED | A/NO/NR |
| CAP-MOD-03 | Lettura asse dati (Delayed / Live feed) separato dall'esecuzione | `BetfairConfig.app_key_delayed/app_key_live` | `GET /v1/status` | `get_status` | 032 | CORE_BLOCKED | Pz/NO/NR |
| CAP-MOD-04 | Cambio SIM↔LIVE su comando owner | `set_simulation_mode` | `POST /v1/mode` | `set_mode` | 019, 032 · MCP-03b | NOT_IMPLEMENTED | P/NO/NR |
| CAP-MOD-05 | Precondizioni del cambio: posizioni, pending, riconciliazione, credenziali (senza segreti) | `is_live_allowed` (parziale) | `POST /v1/mode` | `set_mode` | 032 | CORE_BLOCKED | Pz/NO/NR |
| CAP-MOD-06 | Transizione atomica o rollback sicuro | — | `POST /v1/mode` | `set_mode` | 032 | CORE_BLOCKED | V/NO/NR |
| CAP-MOD-07 | Motivazione e audit del cambio | — | `GET /v1/audit/{id}` | `get_audit_trail` | 032, 007 | CORE_BLOCKED | A/NO/NR |
| CAP-MOD-08 | Mai auto-LIVE; MCP non disattiva il gate LIVE | `safety_layer`, `enforce_deploy_gate` | `POST /v1/mode` | `set_mode` | 032, 023 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-MOD-09 | HYBRID_REAL_EXECUTION riconosciuta e rifiutata | — | `POST /v1/mode` | `set_mode` | 032 · MCP-03b | NOT_IMPLEMENTED | A/NO/NR |
| CAP-MOD-10 | «Live data con denaro fittizio» | vietato (07/10: LIVE_DATA_SIM) | — | — | 032 | OWNER_BLOCKED (K1) | —/NO/NR |
| CAP-MOD-11 | «SIM offline»: replay di dataset storici | `tests/replay/` (solo test) | — | — | 024, 026 | OWNER_BLOCKED (K1) | Pz/NO/NR |

### 2.4 MKT — Eventi, mercati, quote, liquidità (11)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-MKT-01 | Eventi per nome | `CatalogSyncService` | `GET /v1/events` | `list_events` | 009 · MCP-02c | NOT_IMPLEMENTED | P/NO/NR |
| CAP-MKT-02 | Mercati e runner | catalogo DB, `betfair_service` | `GET /v1/markets` | `list_markets` | 009 · MCP-02c | NOT_IMPLEMENTED | P/NO/NR |
| CAP-MKT-03 | Risoluzione deterministica evento/mercato/runner per nome | `DeterministicResolver`, PR08 | `GET /v1/markets` | `list_markets` | 009 · PR08 | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-MKT-04 | Book e quote | `betfair_service`, `MARKET_BOOK_UPDATE` | `GET /v1/markets/{id}/book` | `get_market_book` | 009 · MCP-02c | NOT_IMPLEMENTED | P/NO/NR |
| CAP-MKT-05 | Freshness dichiarata del book | feed Delayed/stream | idem | idem | 009 | CORE_BLOCKED | Pz/NO/NR |
| CAP-MKT-06 | Liquidità e ladder | `core/liquidity.py` | idem | idem | 009 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-MKT-07 | Stato del mercato (sospeso, chiuso, in-play) | book | idem | idem | 009 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-MKT-08 | Market Stream operativo | `services/streaming_feed.py`, PR11 | (interno) | — | 009, 022 · PR11 | CORE_BLOCKED | Pz/NO/NR |
| CAP-MKT-09 | Order Stream | assente (#495) | (interno) | — | 022 | CORE_BLOCKED | A/NO/NR |
| CAP-MKT-10 | Market P/L e superficie personale #495 | parziale | estensione route esistenti | — | 009, 013 · MCP-02f | CORE_BLOCKED | Pz/NO/NR |
| CAP-MKT-11 | Aggiornamenti incrementali / sottoscrizioni | stream | RC-04 | — | 009 | OWNER_BLOCKED | Pz/NO/NR |

### 2.5 ORD — Ordini BACK/LAY (22)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-ORD-01 | Preview senza effetti con motivi di rifiuto | `risk_middleware`, MM (nessuna preview esposta) | `POST /v1/preview` | `preview_order` | 016 · MCP-04a | CORE_BLOCKED | Pz/NO/NR |
| CAP-ORD-02 | BACK limit | `CMD_QUICK_BET` → `trading_engine` | `POST /v1/orders` | `place_order` | 016 · MCP-04b | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-03 | LAY limit con liability stake×(price−1) | idem, PR28 | `POST /v1/orders` | `place_order` | 016 · MCP-04b | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-04 | Stake EXPLICIT / FIXED / MM mutuamente esclusivi | `core/money_management.py`, `stake_mode.py` | `POST /v1/orders` | `place_order` | 016 · MCP-04b/04f | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-05 | Microstake nativo sotto il minimo exchange | `core/microstake_*` | `POST /v1/orders` | `place_order` | 016 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-06 | Cancel pertinente | `CMD_CANCEL_ORDER` | `POST /v1/orders/{id}/cancel` | `cancel_order` | 016 · MCP-04d | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-07 | Replace senza retry cieco | `CMD_REPLACE_ORDER` | `POST /v1/orders/{id}/replace` | `replace_order` | 016 · MCP-04d | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-08 | updateOrders (persistenza) | assente | estensione | — | 016 · MCP-04g | CORE_BLOCKED | A/NO/NR |
| CAP-ORD-09 | Stati matched / unmatched / partial | eventi `QUICK_BET_*` | `GET /v1/orders` | `list_orders` | 013 · MCP-02d | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-10 | TTL degli unmatched | `direct_unmatched_ttl.py` | `GET /v1/orders` | `list_orders` | 013, 016 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-11 | Anti-duplicato ordini | `duplication_guard`, `QUICK_BET_DUPLICATE` | `POST /v1/orders` | `place_order` | 016, 021 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-12 | AMBIGUOUS dopo l'invio, riconciliazione | `QUICK_BET_AMBIGUOUS`, PR30 | `GET /v1/operations/{id}` | `get_operation` | 016, 022 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-13 | customerOrderRef sul wire, parità SIM | F-13a (#601) | — | — | 016 | NOT_IMPLEMENTED | F/NO/NR |
| CAP-ORD-14 | Ordini correnti | `listCurrentOrders` | `GET /v1/orders` | `list_orders` | 013 · MCP-02d | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-15 | Ordini chiusi | `listClearedOrders` (sottoinsieme LIVE) | `GET /v1/orders` | `list_orders` | 013 · MCP-02d | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-ORD-16 | Rivalidazione della quota prima dell'invio (PF-OD12-04) | miglior prezzo dinamico **non implementato** | `POST /v1/orders` | `place_order` | 016 | CORE_BLOCKED | A/NO/NR |
| CAP-ORD-17 | Fondi insufficienti = blocco, mai ridimensionamento (PF-EXEC-04) | gate fondi Q10 | `POST /v1/orders` | `place_order` | 016 | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-ORD-18 | Rifiuto sotto `min_stake` e sopra `max_single_bet` | `stake_sotto_min_stake`, decisione 17/10 | `POST /v1/preview` | `preview_order` | 016, 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-19 | Rollback di un quick bet | `QUICK_BET_ROLLBACK_*` | (interno) | — | 016, 020 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ORD-20 | MANUAL a doppia conferma | assente | `POST /v1/preview` + `POST /v1/orders` | `preview_order`, `place_order` | 036 · MCP-04c | CORE_BLOCKED | A/NO/NR |
| CAP-ORD-21 | Ingresso automatico (principal automation) | — | `POST /v1/orders` | `place_order` | 034 · MCP-04f | NOT_IMPLEMENTED | —/NO/NR |
| CAP-ORD-22 | Mercato sospeso / feed perso = nessun ingresso (PF-EXEC-05) | safety gates | `POST /v1/orders` | `place_order` | 016, 022 | NOT_IMPLEMENTED | Pz/NO/NR |

### 2.6 DUT — Dutching (15)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-DUT-01 | Calcolo stake con Decimal | `dutching.py` | `POST /v1/preview`, `POST /v1/dutching` | `place_dutching` | 036 · MCP-04e | NOT_IMPLEMENTED | P/NO/NR |
| CAP-DUT-02 | Creazione gruppo/batch | `dutching_batch_manager`, `DUTCHING_BATCH_CREATED` | `POST /v1/dutching` | `place_dutching` | 036 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-DUT-03 | Numero variabile di selezioni | `dutching.py` | idem | idem | 036 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-DUT-04 | Distribuzione per rendimento o per rischio | da localizzare | idem | idem | 036 | CORE_BLOCKED | V/NO/NR |
| CAP-DUT-05 | Dutching risultati esatti FT/HT | `dutching*` | idem | idem | 036 · MCP-04e | NOT_IMPLEMENTED | V/NO/NR |
| CAP-DUT-06 | Liability ed esposizione del gruppo | `risk_gate`, MM | `GET /v1/exposure` | `get_exposure` | 036, 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-DUT-07 | Commissioni nel calcolo | `commission_pct` | `POST /v1/preview` | `preview_order` | 036 | NOT_IMPLEMENTED | V/NO/NR |
| CAP-DUT-08 | Ricalcolo al cambio quote | da localizzare | `POST /v1/preview` | `preview_order` | 036 | CORE_BLOCKED | V/NO/NR |
| CAP-DUT-09 | Parziale: ribilanciato, coperto o sospeso (PF-EXEC-02) | decisione registrata; implementazione da verificare | `GET /v1/operations/{id}` | `get_operation` | 036 | CORE_BLOCKED | V/NO/NR |
| CAP-DUT-10 | Hedge di emergenza del gruppo | `CMD_DUTCHING_EMERGENCY_HEDGE` | (interno) | — | 036 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-DUT-11 | Annullamento e recupero del batch | `DUTCHING_BATCH_STATUS_UPDATED`, `batch_lock_manager` | `POST /v1/orders/{id}/cancel` | `cancel_order` | 036, 020 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-DUT-12 | Cashout delle posizioni risultanti | cashout chain | `POST /v1/cashout` | `cashout` | 036, 035 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-DUT-13 | Simulazione preventiva e verifica del rischio | — | `POST /v1/preview` | `preview_order` | 036 | CORE_BLOCKED | Pz/NO/NR |
| CAP-DUT-14 | Compatibilità con i tavoli Roserpina | da localizzare | — | — | 036, 011 | CORE_BLOCKED | V/NO/NR |
| CAP-DUT-15 | Selezione automatica delle selezioni | da localizzare | — | — | 036 | CORE_BLOCKED | V/NO/NR |

### 2.7 CSH — Cashout (20)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-CSH-01 | Cashout di una selezione/posizione | `cashout_router`, `cashout_executor` | `POST /v1/cashout` (target=selection) | `cashout` | 035 · MCP-05b | NOT_IMPLEMENTED | P/NO/NR |
| CAP-CSH-02 | Cashout di un mercato | idem | `POST /v1/cashout` (market) | `cashout` | 035 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-CSH-03 | Cashout di un tavolo Roserpina | da localizzare | `POST /v1/cashout` (target da estendere) | `cashout` | 035, 011 | CORE_BLOCKED | V/NO/NR |
| CAP-CSH-04 | Cashout multiplo | idem | `POST /v1/cashout` | `cashout` | 035 | NOT_IMPLEMENTED | V/NO/NR |
| CAP-CSH-05 | Cashout di tutte le posizioni ammissibili | `risk_stop.cashout_all_signal` | `POST /v1/cashout` (all) | `cashout` | 035 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-CSH-06 | Cashout parziale (fraction / percentage) | PR44 | `POST /v1/cashout` | `cashout` | 035 · PR44 | CORE_BLOCKED | Pz/NO/NR |
| CAP-CSH-07 | Void hedge | PR43 | `POST /v1/cashout` (Void) | `cashout` | 035 · PR43 | CORE_BLOCKED | Pz/NO/NR |
| CAP-CSH-08 | Esposizione mista BACK/LAY e netting | PR43 | `POST /v1/cashout` | `cashout` | 035 · PR43 | CORE_BLOCKED | Pz/NO/NR |
| CAP-CSH-09 | P/L lordo e netto con commissione | `core/sl_tp_pnl.py`, F-01 | `POST /v1/preview` | `preview_order` | 035 | NOT_IMPLEMENTED | F/NO/NR |
| CAP-CSH-10 | Liquidità, spread, slippage | `core/liquidity.py` | `POST /v1/preview` | `preview_order` | 035 | CORE_BLOCKED | Pz/NO/NR |
| CAP-CSH-11 | L'hedge chiude davvero la posizione | F-06 (#600) | — | — | 035 | NOT_IMPLEMENTED | F/NO/NR |
| CAP-CSH-12 | Hedge scritto nel ledger ordini | F-05 (#593) | — | — | 035 | NOT_IMPLEMENTED | F/NO/NR |
| CAP-CSH-13 | AMBIGUOUS cashout con riconciliazione, nessun secondo hedge cieco | PR45 | `GET /v1/operations/{id}` | `get_operation` | 035 · PR45 | CORE_BLOCKED | Pz/NO/NR |
| CAP-CSH-14 | Protezione contro cashout duplicati | `CASHOUT_*`, identità | `POST /v1/cashout` | `cashout` | 035, 021 | NOT_IMPLEMENTED | V/NO/NR |
| CAP-CSH-15 | Monitoraggio esposizione residua | `cashout_residual_handler.py` | `GET /v1/exposure` | `get_exposure` | 035, 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-CSH-16 | Auto-cashout MM e intento P35 (lifecycle fino a chiusura mercato) | PR25 | `POST /v1/cashout` (intent/lifecycle) | `cashout` | 035 · PR25 | CORE_BLOCKED | Pz/NO/NR |
| CAP-CSH-17 | Cashout attivato da SL/TP/trailing | `_monitor_sl_tp_trailing` | — | — | 018, 035 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-CSH-18 | Cashout da STOP / RISK_STOP | `risk_stop`, PR37 | `POST /v1/stop` | `stop` | 019, 035 | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-CSH-19 | Mai CLOSED con esposizione non riconciliata | invariante | `GET /v1/positions` | `list_positions` | 035, 026 | NOT_IMPLEMENTED | V/NO/NR |
| CAP-CSH-20 | Auto-green con ritardo | `auto_green_delay_enabled/sec` | `PATCH /v1/config` | `patch_config` | 018 | NOT_IMPLEMENTED | P/NO/NR |

### 2.8 SLT — Stop-loss, take-profit, trailing (7)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-SLT-01 | Impostazione SL | payload ordine / `risk_middleware` | `POST /v1/orders`, `PATCH /v1/config` | `place_order`, `patch_config` | 018 · PR24 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-SLT-02 | Impostazione TP | idem | idem | idem | 018 · PR24 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-SLT-03 | Trailing persistente | idem, PR25 | idem | idem | 018 · PR25 | CORE_BLOCKED | Pz/NO/NR |
| CAP-SLT-04 | Monitor attivo (oggi solo da callback stream) | `runtime_controller.py:459,6904` | (interno) | — | 018, 022 | CORE_BLOCKED | Pz/NO/NR |
| CAP-SLT-05 | P/L liquidabile per la soglia | F-01 (#596) | — | — | 018 | NOT_IMPLEMENTED | F/NO/NR |
| CAP-SLT-06 | Stato SL/TP/trailing per posizione | ledger | `GET /v1/positions` | `list_positions` | 013 | NOT_IMPLEMENTED | V/NO/NR |
| CAP-SLT-07 | Propagazione config → runtime verificabile | `reload_config` | `PATCH /v1/config` | `patch_config` | 018, 014 | NOT_IMPLEMENTED | Pz/NO/NR |

### 2.9 ROS — Roserpina multitavolo (13)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-ROS-01 | Numero di tavoli e ridimensionamento | `TableManager.resize`, `table_count` | `PATCH /v1/config` | `patch_config` | 015 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ROS-02 | Stato del singolo tavolo | `snapshot_table` | `GET /v1/exposure` o RC-05 | `get_exposure` | 011 | OWNER_BLOCKED (K3) | P/NO/NR |
| CAP-ROS-03 | Vista aggregata dei tavoli | `TableManager` | idem | idem | 011 | OWNER_BLOCKED (K3) | P/NO/NR |
| CAP-ROS-04 | Allocazione evento → tavolo | `allocate`, `activate` | (interno) | — | 011, 025 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ROS-05 | Sblocco forzato di un tavolo (privilegiato) | `force_unlock*` | RC-06 | (candidato) | 015 | OWNER_BLOCKED | P/NO/NR |
| CAP-ROS-06 | Tavoli di recovery | `max_recovery_tables`, `allow_recovery` | `GET /v1/exposure` | `get_exposure` | 011 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ROS-07 | Target di profitto del ciclo | `target_profit_cycle_pct` | `GET/PATCH /v1/config` | config | 011, 014 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-ROS-08 | Transizioni desk EXPANSION / DEFENSE / LOCKDOWN | `risk_desk`, soglie drawdown | `GET /v1/status` | `get_status` | 011 · ROS-01/02 (#586) | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-ROS-09 | Auto-reset del ciclo | `auto_reset_drawdown_pct`, `reset_cycle` | RC-02 | (candidato) | 015 | OWNER_BLOCKED | P/NO/NR |
| CAP-ROS-10 | Avvio / pausa / STOP **per tavolo** | assente (STOP è globale) | — | — | 015 | CORE_BLOCKED | A/NO/NR |
| CAP-ROS-11 | Allocazione del capitale per tavolo | MM Roserpina | `GET /v1/exposure` | `get_exposure` | 011, 012 | NOT_IMPLEMENTED | V/NO/NR |
| CAP-ROS-12 | Debito di recovery persistente dopo crash | F-10 (#599) | `GET /v1/exposure` | `get_exposure` | 011, 020 | NOT_IMPLEMENTED | F/NO/NR |
| CAP-ROS-13 | Equity e bankroll Roserpina | `docs/roserpina_bankroll_equity.md` | `GET /v1/account` | `get_account` | 012 | NOT_IMPLEMENTED | P/NO/NR |

### 2.10 BKR — Bankroll, Money Management, limiti (17)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-BKR-01 | Saldo LIVE con freschezza 30 s (codice: 120 s, conflitto C2 #586) | `core/table_manager.py:51`, funds | `GET /v1/account` | `get_account` | 012 · FUNDS (#586) | CORE_BLOCKED | Pz/NO/NR |
| CAP-BKR-02 | Saldo fittizio SIM separato | `SimulationBroker` | `GET /v1/account` | `get_account` | 012 · PR15 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-03 | Capitale impegnato ed esposizione totale | `controller_event_exposure`, PR29 | `GET /v1/exposure` | `get_exposure` | 012 · MCP-02b | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-04 | Esposizione per ordine / mercato / evento / tavolo | cap `max_*_exposure` | `GET /v1/exposure` | `get_exposure` | 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-05 | Drawdown e peak separati per modalità | PR15, DD-01..04 (#586) | `GET /v1/exposure` | `get_exposure` | 012 | CORE_BLOCKED | Pz/NO/NR |
| CAP-BKR-06 | Perdita giornaliera e di sessione | `daily_loss_store`, `loss_limits` | `GET /v1/exposure` | `get_exposure` | 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-07 | Rifiuto sopra `max_single_bet` con stake richiesto | MM | `POST /v1/preview` | `preview_order` | 012, 016 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-08 | Rifiuto sotto il minimo configurato | MM | idem | idem | 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-09 | Commissione configurabile senza default nascosti | `commission_pct` (t80u) | `GET /v1/config` | `get_config` | 012 | CORE_BLOCKED | Pz/NO/NR |
| CAP-BKR-10 | Motivi di rifiuto machine-readable | reason codes del core | `POST /v1/preview` | `preview_order` | 012, 006 | CORE_BLOCKED | Pz/NO/NR |
| CAP-BKR-11 | Stake MM in percentuale del bankroll verificato | `money_management`, 23/10 | `POST /v1/preview` | `preview_order` | 012 · MM-01/02 | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-BKR-12 | Profilo di rischio | `RiskProfile` | `GET /v1/config` | `get_config` | 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-13 | P/L di sessione e giornaliero | `pnl_engine` | `GET /v1/exposure` o `/v1/account` | — | 012, 013 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-14 | Liquidity guard | `liquidity_guard_*` | `POST /v1/preview` | `preview_order` | 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-15 | Max win | `max_win`, `max_win_warning_only` | idem | idem | 012 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-BKR-16 | Cap opzionali OFF di default, valore invalido = fail-closed | `RoserpinaConfig` Optional | `GET /v1/config` | `get_config` | 012, 014 | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-BKR-17 | Sincronizzazione del bankroll | `BANKROLL_SYNC_RESULT` | `GET /v1/account` | `get_account` | 012 | NOT_IMPLEMENTED | P/NO/NR |

### 2.11 CFG — Configurazioni (10)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-CFG-01 | Lettura config redatta | `settings_service`, `config_registry` | `GET /v1/config` | `get_config` | 014 · MCP-02e | NOT_IMPLEMENTED | P/NO/NR |
| CAP-CFG-02 | Patch atomica, nessuna mutazione parziale | `config_store`, `atomic_io` | `PATCH /v1/config` | `patch_config` | 014 · MCP-03a | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-CFG-03 | Validazione senza applicare (dry-run) | — | `PATCH /v1/config` (estensione) o RC-07 | `patch_config` | 014 | CORE_BLOCKED | A/NO/NR |
| CAP-CFG-04 | Versionamento e rollback | — | RC-08 | — | 014 | CORE_BLOCKED | A/NO/NR |
| CAP-CFG-05 | Ambiti: globale, tavolo, mercato, sessione, modalità, strategia | parziale | `GET/PATCH /v1/config` | config | 014 | CORE_BLOCKED | Pz/NO/NR |
| CAP-CFG-06 | Save fallito non distrugge, config corrotta in backup | `config_store` | — | — | 014, 020 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-CFG-07 | `reload_config` preserva tavoli, esposizione, pending | PR28 | `PATCH /v1/config` | `patch_config` | 014 | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-CFG-08 | Inventario completo delle chiavi (GUI 42 + RoserpinaConfig + runtime) | CFG-01..07 (#586) | `GET /v1/config` | `get_config` | 001, 014 | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-CFG-09 | Segreti mai esposti (redazione) | `core/redaction.py`, `config_registry` mask | `GET /v1/config` | `get_config` | 014, 023 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-CFG-10 | Audit delle modifiche di configurazione | — | `GET /v1/audit/{id}` | `get_audit_trail` | 014, 007 | CORE_BLOCKED | A/NO/NR |

### 2.12 STR / SIG — Strategie e segnali (12)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-STR-01 | Creazione / lettura / modifica / eliminazione strategie | **assente nel core** | RC-09 | — | 010, 015 | CORE_BLOCKED (K2) | A/NO/NR |
| CAP-STR-02 | Attivazione / disattivazione | assente | RC-09 | — | 015 | CORE_BLOCKED | A/NO/NR |
| CAP-STR-03 | Versionamento, priorità, conflitti | assente | RC-09 | — | 015 | CORE_BLOCKED | A/NO/NR |
| CAP-STR-04 | Parametri e filtri | assente | RC-09 | — | 015 | CORE_BLOCKED | A/NO/NR |
| CAP-STR-05 | Cap di esposizione per strategia (P06, rinviato) | assente | — | — | 015 | CORE_BLOCKED | A/NO/NR |
| CAP-SIG-01 | Ricezione segnali Telegram | `telegram_*` | — | — | 010 | OUT_OF_SCOPE (Telegram sospeso, #426) | P/NO/NR |
| CAP-SIG-02 | Esito segnale (approvato / rifiutato) in lettura | `SIGNAL_APPROVED/REJECTED` | RC-10 | — | 010, 033 | OWNER_BLOCKED (K3) | P/NO/NR |
| CAP-SIG-03 | Dedupe dei segnali | `core/signal_dedupe.py` | — | — | 010 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-SIG-04 | Coda dei segnali | `core/signal_queue.py` | RC-10 | — | 010 | OWNER_BLOCKED (K3) | P/NO/NR |
| CAP-SIG-05 | Origine del segnale / provenienza | PF-API-0 | `GET /v1/audit/{id}` | `get_audit_trail` | 010, 007 | CORE_BLOCKED | Pz/NO/NR |
| CAP-SIG-06 | Gestione parser personalizzato | `custom_parser*` | — | — | — | OUT_OF_SCOPE (Telegram sospeso) | P/NO/NR |
| CAP-SIG-07 | Ingresso automatico da servizi esterni | OWNER-MCP-AUTO-ORDER-01 | `POST /v1/orders` | `place_order` | 034 · MCP-04f | NOT_IMPLEMENTED | —/NO/NR |

### 2.13 STP — STOP e barriere (10)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-STP-01 | PAUSE (nessun nuovo ordine, niente cancel, niente cashout) | `pause` | `POST /v1/stop` | `stop` | 019 · MCP-05a | NOT_IMPLEMENTED | P/NO/NR |
| CAP-STP-02 | STOP (blocco + cancel unmatched pertinenti + cashout pertinenti) | `stop`, PR37 | `POST /v1/stop` | `stop` | 019 · MCP-05a | NOT_IMPLEMENTED | Pz/NO/NR |
| CAP-STP-03 | RISK_STOP persistente | `risk_stop`, `persist_risk_stop` | `POST /v1/stop` | `stop` | 019 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-STP-04 | EMERGENCY | `emergency_stop` | `POST /v1/stop` | `stop` (owner) | 019 · MCP-05a | NOT_IMPLEMENTED | P/NO/NR |
| CAP-STP-05 | RESUME solo dopo nuova readiness completa | `resume` | `POST /v1/resume` | `resume` (owner) | 019 · MCP-05a | NOT_IMPLEMENTED | P/NO/NR |
| CAP-STP-06 | Reset di RISK_STOP / EMERGENCY | `reset_risk_stop`, `reset_emergency` | `POST /v1/resume` (estensione) | `resume` | 019 | OWNER_BLOCKED (K3) | P/NO/NR |
| CAP-STP-07 | Lockdown forzato | `force_lockdown` | `POST /v1/stop` | `stop` | 019 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-STP-08 | STOP persistente al riavvio (PF-EXEC-06) | `restore_risk_stop` | `GET /v1/status` | `get_status` | 019, 020 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-STP-09 | Nessun ingresso ritardato dopo STOP (in volo riconciliato) | PR37 | — | — | 019, 021 | CORE_BLOCKED | Pz/NO/NR |
| CAP-STP-10 | Stop per esposizione (`max_exposure_stop`) | `exposure_stop_reason` | `GET /v1/status` | `get_status` | 019, 012 | NOT_IMPLEMENTED | P/NO/NR |

### 2.14 REC / SET — Riconciliazione, recovery, settlement (13)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-REC-01 | Stato della riconciliazione | `ReconciliationEngine` | `GET /v1/reconciliation/status` | `get_reconciliation_status` | 008 · MCP-02a | NOT_IMPLEMENTED | P/NO/NR |
| CAP-REC-02 | Riconciliazione su comando, via runtime | idem | `POST /v1/reconcile` | `reconcile` | 017 · MCP-05c | NOT_IMPLEMENTED | P/NO/NR |
| CAP-REC-03 | Esito del recovery blocca ACTIVE | F-09 (#597) | `GET /v1/status` | `get_status` | 020 | NOT_IMPLEMENTED | F/NO/NR |
| CAP-REC-04 | Ordini ghost all'avvio persistiti | F-08 (#594) | `GET /v1/reconciliation/status` | idem | 020 | NOT_IMPLEMENTED | F/NO/NR |
| CAP-REC-05 | Coda di ambiguità (`RECONCILE_AMBIGUITY_ENQUEUED`) | reconciliation | `GET /v1/operations?status=pending` | `list_pending_operations` | 017, 022 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-REC-06 | Settlement trattenuti | `reconcile_held_settlements` | `POST /v1/reconcile` | `reconcile` | 017 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-REC-07 | Stato di recovery dopo crash | `core/state_recovery.py` | `GET /v1/reconciliation/status` | idem | 020 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-REC-08 | Durabilità SIM (broker e DB convergono dopo kill) | PR34 | — | — | 020, 026 | CORE_BLOCKED | Pz/NO/NR |
| CAP-REC-09 | Journal MCP → `get_operation` dopo riavvio | MCP | `GET /v1/operations/{id}` | `get_operation` | 020 · MCP-05c | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-REC-10 | Saga/outbox atomiche (PR33, BLOCKED_ENV) | PR33 | — | — | 020 | CORE_BLOCKED | V/NO/NR |
| CAP-SET-01 | Settlement exchange autorevole | SET-01 (#586) | `GET /v1/orders` (cleared) | `list_orders` | 013 | CORE_BLOCKED | Pz/NO/NR |
| CAP-SET-02 | Storico P/L verificabile | SET-02 (#586) | RC-11 o `GET /v1/orders` | `list_orders` | 013 | CORE_BLOCKED | Pz/NO/NR |
| CAP-SET-03 | Settlement incerto segnalato | `SETTLEMENT_RECONCILIATION_UNCERTAIN` | `GET /v1/reconciliation/status` | idem | 013 | NOT_IMPLEMENTED | P/NO/NR |

### 2.15 AUD — Audit, log, diagnostica (15)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-AUD-01 | Audit trail redatto per `correlation_id` | `event_journal`, PR47 | `GET /v1/audit/{id}` | `get_audit_trail` | 007 · MCP-02e | CORE_BLOCKED | Pz/NO/NR |
| CAP-AUD-02 | Log applicativi: ricerca, filtri, paginazione | `event_log`, `safety_logger` | RC-12 | (candidato `query_logs`) | 033 | OWNER_BLOCKED (K3) | Pz/NO/NR |
| CAP-AUD-03 | Log ordini | eventi `QUICK_BET_*` | RC-12 | idem | 033 | OWNER_BLOCKED | P/NO/NR |
| CAP-AUD-04 | Log cashout | `CASHOUT_*` | RC-12 | idem | 033 | OWNER_BLOCKED | P/NO/NR |
| CAP-AUD-05 | Log riconciliazione | `RECONCILIATION_*` | RC-12 | idem | 033 | OWNER_BLOCKED | P/NO/NR |
| CAP-AUD-06 | Log Roserpina e desk | `risk_desk`, `table_manager` | RC-12 | idem | 033 | OWNER_BLOCKED | Pz/NO/NR |
| CAP-AUD-07 | Eventi di STOP | `*_STOP_TRIGGERED/RESET` | RC-12 | idem | 033 | OWNER_BLOCKED | P/NO/NR |
| CAP-AUD-08 | Log del broker simulato | `simulation_broker` | RC-12 | idem | 033 | OWNER_BLOCKED | V/NO/NR |
| CAP-AUD-09 | Eventi di autenticazione/autorizzazione della Control API | (nuovo) | RC-12 | idem | 033, 005 | CORE_BLOCKED | A/NO/NR |
| CAP-AUD-10 | Log MCP (stderr, campi in allowlist) | MCP `audit.py` | — | — | 007 | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-AUD-11 | Traccia end-to-end request → bet_id | PR47 | `GET /v1/audit/{id}` | `get_audit_trail` | 007 | CORE_BLOCKED | Pz/NO/NR |
| CAP-AUD-12 | Esportazione autorizzata e redatta | (nuovo) | RC-12 | — | 033 | OWNER_BLOCKED | A/NO/NR |
| CAP-AUD-13 | Stato di test e certificazioni | ledger #606 | — | — | 037 | CORE_BLOCKED (#606 aperta) | A/NO/NR |
| CAP-AUD-14 | Regole di anomalia e probe | `observability/` | `GET /v1/status` | `get_status` | 033 · PR20 | NOT_IMPLEMENTED | P/NO/NR |
| CAP-AUD-15 | Log operativi separati dalle evidenze immutabili | — | — | — | 033, 028 | CORE_BLOCKED | A/NO/NR |

### 2.16 SEC — Sicurezza e privilegi (11)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-SEC-01 | Autenticazione MCP ↔ Control API (D-11) | (nuovo) | tutte | tutti | 005 · MCP-01d | CORE_BLOCKED | A/NO/NR |
| CAP-SEC-02 | Autorizzazione per tool (scope) | MCP `auth/` | — | tutti | 005 · MCP-01c | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-SEC-03 | Sei livelli di privilegio | proposta | — | tutti | 034 | OWNER_BLOCKED (K4) | —/NO/NR |
| CAP-SEC-04 | Four-eyes: conferma verificata fuori dall'agente | (nuovo) | — | — | 036, 005 | OWNER_BLOCKED (K5) | A/NO/NR |
| CAP-SEC-05 | Prompt injection: dati upstream = dati | MCP | — | tutti | 023 | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-SEC-06 | Solo loopback letterale, porta esplicita | MCP + Control API | — | — | 023 · MCP-01d | NOT_IMPLEMENTED | A/NO/NR |
| CAP-SEC-07 | Redazione segreti in output e log | `core/redaction.py`, MCP | tutte | tutti | 023 | NOT_IMPLEMENTED | P/SIM/NR |
| CAP-SEC-08 | Rate limit e quote della Control API | (nuovo) | tutte | — | 023 | CORE_BLOCKED | A/NO/NR |
| CAP-SEC-09 | Anti-replay e anti-spoofing (handle, nonce, scadenza) | (nuovo) | mutazioni | comandi | 023, 036 | CORE_BLOCKED | A/NO/NR |
| CAP-SEC-10 | No-bypass statico e runtime (MCP non importa core/Betfair/DB) | MCP `tests/guards` | — | — | 023 | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-SEC-11 | Nessun accesso dell'agente alle credenziali Betfair | invariante | — | — | 023 | NOT_IMPLEMENTED | P/SIM/NR |

### 2.17 REL / LIV — Rilascio e LIVE (8)

| ID | Capacità | Core: componente | Endpoint | Tool MCP | Schede | Stato | L1/L2/L3 |
|---|---|---|---|---|---|---|---|
| CAP-REL-01 | Packaging e installazione MCP (Windows, poi Linux) | — | — | — | 029 · MCP-07a | NOT_IMPLEMENTED | —/NO/NR |
| CAP-REL-02 | Compatibilità di versione MCP ↔ Control API | compat matrix | `GET /v1/meta` | `get_meta` | 029 | NOT_IMPLEMENTED | —/SIM/NR |
| CAP-REL-03 | Healthcheck post-installazione | — | `GET /v1/status` | `get_status` | 030 | CORE_BLOCKED | A/NO/NR |
| CAP-REL-04 | Rollback verificato | — | — | — | 030 | CORE_BLOCKED | A/NO/NR |
| CAP-REL-05 | Backup/restore prima dei test reali (P07) | #578 | — | — | 030 | CORE_BLOCKED | Pz/NO/NR |
| CAP-LIV-01 | Gate LIVE nel MCP, comando owner | — | `POST /v1/mode` | `set_mode` | MCP-06a | OWNER_BLOCKED (mandato LIVE) | —/NO/NR |
| CAP-LIV-02 | Prove LIVE su limiti di campagna | — | — | — | MCP-06b | OWNER_BLOCKED | —/NO/NR |
| CAP-LIV-03 | REAL-EXECUTION certification (Delayed key, ordini reali) | 27/10 | — | — | — | OWNER_BLOCKED (GO per caso) | —/NO/NR |

## 3. Conteggi del catalogo v0.1

| Area | Capacità | NOT_IMPLEMENTED | CORE_BLOCKED | OWNER_BLOCKED | OUT_OF_SCOPE |
|---|---:|---:|---:|---:|---:|
| MET | 16 | 9 | 6 | 1 | 0 |
| RT | 11 | 7 | 1 | 3 | 0 |
| MOD | 11 | 4 | 5 | 2 | 0 |
| MKT | 11 | 6 | 4 | 1 | 0 |
| ORD | 22 | 18 | 4 | 0 | 0 |
| DUT | 15 | 9 | 6 | 0 | 0 |
| CSH | 20 | 13 | 7 | 0 | 0 |
| SLT | 7 | 5 | 2 | 0 | 0 |
| ROS | 13 | 8 | 1 | 4 | 0 |
| BKR | 17 | 13 | 4 | 0 | 0 |
| CFG | 10 | 6 | 4 | 0 | 0 |
| STR/SIG | 12 | 2 | 6 | 2 | 2 |
| STP | 10 | 8 | 1 | 1 | 0 |
| REC/SET | 13 | 9 | 4 | 0 | 0 |
| AUD | 15 | 2 | 5 | 8 | 0 |
| SEC | 11 | 6 | 3 | 2 | 0 |
| REL/LIV | 8 | 2 | 3 | 3 | 0 |
| **Totale** | **222** | **127** | **66** | **27** | **2** |

Denominatore applicabile v0.1 = 222 − 2 OUT_OF_SCOPE = **220**. COMPLETE = **0/220**.

Il catalogo è **incompleto per costruzione** (PF-MCP-001): mancano la GUI riga per riga (42 chiavi),
le singole strategie del perimetro storico, lo streaming (gap #586), la sicurezza applicativa del core,
le PR chiuse, il dossier B1 di #506 (A 872, B 344, 1.062 differenze aperte, 125 righe Control API) e la
superficie #495. Il numero salirà: ogni nuova voce entra con ID nuovo, nessuna esce senza stato motivato.

## 4. Route candidate da ratificare (conflitto K3)

Preferenza owner OWN-MCP-02F: **estendere le route esistenti**; route nuove solo se le esistenti non
rappresentano correttamente la risorsa.

| ID | Bisogno | Opzione A: estensione | Opzione B: route nuova |
|---|---|---|---|
| RC-01 | START del runtime | campo `action` in `POST /v1/resume` (sconsigliato: semantica diversa) | `POST /v1/start` |
| RC-02 | Reset ciclo Roserpina | `PATCH /v1/config` non adatto (è un'azione) | `POST /v1/cycle/reset` |
| RC-03 | Sincronizzazione catalogo | `POST /v1/reconcile` non adatto | `POST /v1/catalog/sync` |
| RC-04 | Aggiornamenti incrementali | `GET /v1/markets/{id}/book?since=` | `GET /v1/events/stream` |
| RC-05 | Stato tavoli Roserpina | sezione `tables` in `GET /v1/exposure` (proposta contract_v1) | `GET /v1/tables` |
| RC-06 | Sblocco forzato tavolo | — | `POST /v1/tables/{id}/release` |
| RC-07 | Validazione config senza effetti | `PATCH /v1/config` con `dry_run: true` (preferita) | `POST /v1/config/validate` |
| RC-08 | Storico versioni config | `GET /v1/config?version=` | `GET /v1/config/history` |
| RC-09 | CRUD strategie | — | `/v1/strategies` (solo dopo contratto core) |
| RC-10 | Segnali e coda | — | `GET /v1/signals` |
| RC-11 | Storico P/L | filtro `cleared` di `GET /v1/orders` | `GET /v1/pnl` |
| RC-12 | Log e diagnostica | — | `GET /v1/logs` (filtri, paginazione, redazione) |

## 5. Aggiornamento del catalogo

- Formato canonico futuro: `catalog/capabilities.json` versionato (PF-MCP-037), da cui questa tabella si
  genera; finché non esiste, questo file è la fonte.
- Ogni modifica di stato porta: SHA dei due repository, fonte (issue/commento), autore, motivazione.
- Una capacità obbligatoria non può passare a `OUT_OF_SCOPE` o `RETIRED` senza decisione owner citata.
