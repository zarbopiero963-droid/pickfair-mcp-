# Audit MCP + Control API — Claude C, 03/11/2026

Tipo: audit in sola lettura + piano della prima fase. Nessuna PR, nessun merge,
nessun deploy, nessun LIVE. Le PR #606/#607 e il lavoro di Claude B non sono toccati.

## 0. Baseline verificata

| Repository | SHA `main` | PR aperte | Note |
|---|---|---|---|
| pickfair-mcp- | `36bbef1` (merge MCP-01c, #36) | nessuna | 5 PR storiche: #2, #33, #34, #36 mergiate; #35 prova del gate, chiusa |
| Pickfair-nogui | `7a70062` (merge #604) | #606, #607 (Claude B) | 1425 commit; sequenza core in corso via roadmap V2 (#586) |

Prove eseguite su pickfair-mcp- `36bbef1` (Python 3.13, lock con hash):

| Verifica | Esito |
|---|---|
| `ruff check` + `ruff format --check` | PASS |
| `mypy` (strict, 30 file) | PASS |
| `pytest` | PASS — 978 passed, 1 skipped (permessi ignorati da root) |
| `scripts/critical_mutations.py` | PASS — 76/76 KILLED |
| mutmut generale | NOT_RUN in questo audit (CI lo esegue sui PR) |
| Integrazione con Pickfair reale (L4/L5) | NOT_RUN — impossibile: la Control API non esiste |

## 1. Stato reale del repository MCP

È un **adapter di fondazione solido ma quasi senza funzioni**. Tutto ciò che c'è funziona
ed è testato; quasi tutto ciò che serve all'operatività manca, per una ragione
strutturale: non esiste ancora la Control API a cui collegarsi.

| Componente | File | Stato | Note |
|---|---|---|---|
| Server MCP stdio | `server.py`, `cli.py` | FUNZIONANTE (L3) | Arresto, SIGINT, stdout pulito testati con processo reale |
| Tool `get_meta` + handshake fail-closed | `tools/meta.py`, `policy/handshake.py` | FUNZIONANTE (L2/L3) | Compat matrix, epoch, capability fuori dalle 25 ⇒ incompatibile |
| Catalogo 25 route / 25 nomi tool | `contract/routes.py`, `tools/catalog.py` | FUNZIONANTE | Solo catalogo: 24 tool su 25 **non registrati** |
| Blocco mutazioni | `policy/exposure.py` | FUNZIONANTE | `commands_exposed() == False`, nessun interruttore |
| Identità richieste + journal append-only | `journal/` | FUNZIONANTE (L2) | Dedupe, recovery `NOT_SENT`/`AMBIGUOUS`, fsync, lock; **non cablato da CLI** |
| Principal e scope | `auth/` | FUNZIONANTE | `serve` usa principal fisso `local-stdio` con solo `read` |
| Envelope ed errori fissi | `envelope.py`, `errors.py` | FUNZIONANTE | Mai testo upstream/eccezioni verso il client |
| Audit su stderr | `audit.py` | FUNZIONANTE | Allowlist dei campi |
| Adapter simulato | `adapters/simulated.py` | FUNZIONANTE | Solo `get_meta_raw`; `certified: false` |
| Adapter HTTP reale | — | **ASSENTE** (`--adapter http` ⇒ exit 2 `BLOCKED_CORE`) | Scheda MCP-01d, bloccata sulla Control API |
| Gate `independent-review` | `.github/workflows/`, `scripts/review_gate.py` | FUNZIONANTE con limiti noti | N12 (sinonimi di BLOCKING) aperto, file protetto |

Niente da buttare: nessun componente è obsoleto o scollegato. L'unico codice
«scollegato» è il journal (pronto, ma senza percorso da CLI) — atteso, perché
servirà solo ai comandi.

## 2. Stato reale della Control API nel core

**Non esiste.** Su `7a70062`: zero route `/v1/*`, zero `operation_id` nel codice di
produzione, nessun modulo control-plane HTTP. Ciò che esiste e **non** va riusato:

- `betfair_market_api.py` (FastAPI, porta 8765, avviato da `AVVIA_API.bat`): API legacy di
  sincronizzazione catalogo (`/status`, `/sync`, `/events`, `/markets`, `/teams`,
  `/competitions`, `/summary`). Il contratto consolidato la esclude esplicitamente:
  «Nuova Control API, NON `betfair_market_api.py`». Va solo hardenizzata (PR36) o ritirata.
- Il «control plane» della mini GUI (`mini_gui.py`) è un pannello di modalità/readiness,
  non un'API.

Ciò che esiste nel core ed è il **materiale autorevole** su cui la Control API dovrà
appoggiarsi (sola mappatura, nessuna duplicazione nel MCP):

| Servizio core | Dove | Serve a |
|---|---|---|
| `RuntimeController.get_status`, `evaluate_live_readiness`, `is_live_allowed`, `get_effective_execution_mode`, `get_deploy_gate_status` | `core/runtime_controller.py` | `/v1/status`, readiness |
| `pause`, `stop`, `risk_stop`, `emergency_stop`, `resume`, `reset_*` | idem | `/v1/stop`, `/v1/resume` |
| `set_simulation_mode` | idem | `/v1/mode` (solo comando owner) |
| `reload_config`, `services/settings_service.py`, `core/config_store.py` | — | `/v1/config` GET/PATCH |
| `ReconciliationEngine`, `reconcile_held_settlements`, `core/state_recovery.py` | `core/reconciliation_engine.py` | `/v1/reconciliation/status`, `/v1/reconcile` |
| `TableManager` (Roserpina multitavolo) | `core/table_manager.py` | snapshot tavoli (route da decidere, §5 punto 2) |
| `MoneyManagement`, `risk_gate`, `risk_desk`, `loss_limits`, `daily_loss_store` | `core/` | solo dietro `/v1/preview` e i comandi — mai nel MCP |
| `position_ledger`, `pnl_engine`, `controller_event_exposure` | `core/` | `/v1/positions`, `/v1/exposure` |
| `CatalogSyncService`, `DeterministicResolver` (resolve evento/mercato/runner per nome) | `services/` | `/v1/events`, `/v1/markets` |
| `services/betfair_service.py`, `streaming_feed.py` (book, current/cleared orders, funds) | `services/` | `/v1/markets/{id}/book`, `/v1/orders`, `/v1/account` |
| Comandi su bus: `CMD_QUICK_BET`, `CMD_PLACE_DUTCHING`, `CMD_CANCEL_ORDER`, `CMD_REPLACE_ORDER`, `CMD_EXECUTE_CASHOUT` | `core/event_bus.py`, `core/trading_engine.py` | base del «neutral command contract» PF-API-0 |
| `_monitor_sl_tp_trailing`, `core/sl_tp_pnl.py` | `core/runtime_controller.py:6904` | SL/TP/trailing (solo lettura dello stato via API) |
| `SimulationBroker` | `simulation_broker.py` | SIM: stesso percorso, esecuzione simulata |

## 3. Matrice di copertura funzionale

Legenda stato MCP: **ESPOSTO** · **SCHEDA PRONTA** (READY_FOR_IMPLEMENTATION, solo su adapter
simulato) · **BLOCKED_CONTROL_API** · **BLOCKED_CORE** · **NON PREVISTO** (nessuna route
approvata) · **SOSPESO** (decisione owner).

| Area richiesta | Core Pickfair (stato #586) | Route Control API | Tool MCP / scheda | Stato MCP | Lavoro necessario |
|---|---|---|---|---|---|
| Versione / handshake | n/a | `GET /v1/meta` | `get_meta` / 01a | **ESPOSTO** (simulato) | Lato core: `/v1/meta` in PF-API-1, schema hash condiviso |
| Stato runtime, modalità, readiness | presente, readiness MCP-aware **mancante** (PF-API-0) | `GET /v1/status` | `get_status` / 02a | SCHEDA PRONTA | Core: readiness MCP-aware; MCP: tool + modelli strict |
| Riconciliazione | presente; F-08/F-09/F-10 mergiate, resto in #586 | `GET /v1/reconciliation/status`, `POST /v1/reconcile` | 02a, 05c | SCHEDA PRONTA | Core: stato esportabile; MCP: tool |
| Bankroll / saldo SIM e LIVE | presente; PR15 mode-scoped e FUNDS-01..03 aperte | `GET /v1/account` | `get_account` / 02b | SCHEDA PRONTA | Core: separazione SIM/LIVE certificata |
| Esposizione / liability / pending | presente; PR28/29 mergiate, AMBIGUOUS in #586 | `GET /v1/exposure` | `get_exposure` / 02b | SCHEDA PRONTA | — |
| Posizioni | `position_ledger` presente | `GET /v1/positions` | `list_positions` / 02b | SCHEDA PRONTA | — |
| Roserpina multitavolo | `TableManager` presente; ROS-01/02 aperte | **nessuna route dedicata** | — | NON PREVISTO | Decisione: dentro `/v1/exposure` o `/v1/status` (proposta in `contract_v1.md`) |
| Money Management (FIXED/MM) | presente; MM-01/02 in #586 | solo dentro `/v1/preview` e i comandi | — | NON PREVISTO come tool, per scelta | Corretto così: il MCP non calcola MM |
| Configurazioni | presente; CFG-01..07 aperte | `GET/PATCH /v1/config` | `get_config` 02e, `patch_config` 03a | SCHEDA PRONTA | Core: patch atomica + redazione |
| Modalità SIM/LIVE | presente (`set_simulation_mode`) | `POST /v1/mode` | `set_mode` / 03b | SCHEDA PRONTA (solo owner, ibrida rifiutata) | Core: comando owner via contract |
| Simulazione | `SimulationBroker` presente; CB-586 in corso | (stessi tool, nessun tool SIM dedicato) | tutti | — | Parità SIM/LIVE, un solo set di tool |
| Mercati / eventi per nome | resolver + catalog sync presenti (PR08 da certificare) | `GET /v1/events`, `GET /v1/markets` | 02c | SCHEDA PRONTA | Core: PR08 |
| Quote / book / freshness | `betfair_service`, stream parziale | `GET /v1/markets/{id}/book` | `get_market_book` / 02c | SCHEDA PRONTA | Core: freshness ratificata, stream (PR11) |
| Ordini correnti/chiusi | presente (current/cleared parziale) | `GET /v1/orders` | `list_orders` / 02d | SCHEDA PRONTA | — |
| Operazioni asincrone | **assente** (`operation_id` = 0 occorrenze) | `GET /v1/operations…` | 02d | SCHEDA PRONTA (lato MCP) | Core: PF-API-0 deve creare `operation_id` |
| Audit per correlation | parziale (PR47) | `GET /v1/audit/{correlation_id}` | 02e | SCHEDA PRONTA | Core: PR47 |
| Preview ordine | assente come API | `POST /v1/preview` | 04a | SCHEDA PRONTA (non esposta) | Core: preview senza effetti |
| BACK / LAY | presente (`CMD_QUICK_BET`, engine) | `POST /v1/orders` | 04b | SCHEDA PRONTA (non esposta) | Core: PF-API commands |
| Dutching (incl. risultati esatti) | presente | `POST /v1/dutching` | 04e | SCHEDA PRONTA (non esposta) | idem |
| Cancel / replace | presente; AMBIGUOUS PR30 | `POST /v1/orders/{id}/cancel`, `/replace` | 04d | SCHEDA PRONTA (non esposta) | idem |
| updateOrders | assente nel core | — (estensione) | 04g | BLOCKED_CORE | Core |
| MANUAL a doppia conferma | assente nel core | `POST /v1/preview` + `POST /v1/orders` | 04c | BLOCKED_CORE | Core: handle legato all'operazione |
| Ingresso automatico (principal automation) | — | (stessi comandi) | 04f | fermo in attesa decisione (MCP#1, 22/10) | Riordino dopo 04b/04e |
| Cashout (target/fraction/Void…) | presente; CSH-01..12 in #586 (F-05/F-06 mergiate) | `POST /v1/cashout` | 05b | SCHEDA PRONTA (non esposta) | Core: PR43–45 |
| Stop-loss / take-profit / trailing | presente (`_monitor_sl_tp_trailing`, F-01 mergiata) | nessuna route dedicata: stato dentro `/v1/positions`; impostazioni in `/v1/config` | — | NON PREVISTO come tool | Decisione: confermare che basta config + lettura |
| STOP / PAUSE / RISK_STOP / EMERGENCY / resume | presente | `POST /v1/stop`, `/v1/resume` | 05a | SCHEDA PRONTA (non esposta) | Core: barriera PR37 |
| Strategie | **nessuna strategia nel core** (nessuna classe, nessun CRUD) | nessuna | — | SOSPESO per decisione owner (nessuna strategia predefinita; CRUD futuro) | Contratto CRUD strategie da definire prima nel core |
| Segnali | solo Telegram | nessuna | — | SOSPESO (Telegram/Copy/Mirror sospesi) | — |
| Diagnostica | `runtime_io_snapshot`, `observability/` | `GET /v1/status` | 02a | SCHEDA PRONTA | — |
| Superficie Betfair personale #495 (market P/L, stream…) | parziale | estensione delle route esistenti | 02f | BLOCKED_CORE | — |
| LIVE | gate presenti | stessi tool | 06a/06b | BLOCKED_OWNER (mandato LIVE) | — |
| Packaging/installazione MCP | — | — | 07a | SCHEDA PRONTA | — |

Conteggi (tool del catalogo): **1/25 esposto**, 13/25 letture con scheda pronta, 11/25 comandi
bloccati per costruzione. Copertura **reale** verso Pickfair: **0/25** (nessuna Control API).

## 4. Dipendenze dalla roadmap V2 (#586)

Il piano ordinato di #586 (t117u) e il mandato owner del 29/10 fissano
**Core → Control API → MCP**: la Control API è la fase **E** (B-CTL-01, «inventario Control
API», P3) e l'MCP la fase **F** (B-MCP-01, dipendenza «Control API certificata»). Prima vengono
i blocchi P0/P1/P2/P3 del core. Sul main di oggi sono mergiate F-01, F-05, F-06, F-08, F-09,
F-10, F-13a e CB-586-FI-03Z; il resto del piano è aperto.

Anche la sequenza #491 mette PF-API-0 → PF-API-1 → PF-API commands **dopo** PR26-a…PR47, e dice
che un passo bloccato «non autorizza API trading in anticipo».

Conseguenza pratica:

1. **MCP lato adapter**: si può avanzare subito sulle 13 schede di sola lettura e sulla preparazione
   dei comandi, tutto su adapter simulato e con schemi PROVISIONAL (mandato Fase A, già vigente).
2. **Control API nel core**: scriverla oggi contraddice l'ordine Core → Control API → MCP del 29/10.
   È un conflitto fra il nuovo incarico e una decisione owner precedente: serve la conferma
   esplicita dell'owner (domanda in §6). Nel frattempo è ammessa solo **progettazione**
   (questo documento e la bozza di §5), nessun codice nel core.

## 5. Bozza di progettazione PF-API-0 / PF-API-1 (non vincolante)

Vincoli già decisi, riportati: in-process nel runtime Pickfair; bind **solo** su loopback
letterale con porta esplicita; autenticata; versionata; letture dai servizi autorevoli;
mutazioni solo via command contract del runtime; nessun accesso diretto Betfair/DB dal layer
API; nessuna copia di MM/risk/cashout/reconciliation.

Proposta di struttura (nel core, a GO ricevuto):

```
control_api/
  contract.py     # descrittore canonico + schema hash (condiviso con pickfair_mcp.contract.version)
  readiness.py    # readiness MCP-aware (PF-API-0): Telegram disconnesso non è blocker se l'ingresso è MCP
  commands.py     # neutral command contract: request_id → operation_id → correlation_id → customer_ref
  operations.py   # registro durevole delle operazioni (stessa risorsa per /operations/{id} e ?status=pending)
  read_views.py   # proiezioni di sola lettura dai servizi del §2, mai calcoli propri
  server.py       # HTTP loopback, auth, rifiuto campi extra / NaN / Inf / bool numerici
```

Ordine di consegna proposto: (a) `/v1/meta` + descrittore canonico condiviso; (b) `/v1/status` e
`/v1/reconciliation/status`; (c) le altre letture; (d) PF-API-0 command contract; (e) comandi.
Punti da ratificare in PF-API-0 (già censiti): campi definitivi di `/v1/meta`, algoritmo dello
schema hash, D-07, D-10 (chiave idempotenza dal client), D-11 (auth MCP ↔ Control API), durata
dell'handle MANUAL, collocazione dei tavoli Roserpina.

## 6. Domande owner (minime)

1. **Ordine Control API.** Il mandato del 29/10 (#586) e #491 mettono la Control API *dopo* il core.
   Il nuovo incarico chiede di completarla. Opzioni:
   (a) mantenere l'ordine: Claude C fa solo MCP su adapter simulato + progettazione della Control API;
   (b) autorizzare ora PF-API-1 **di sola lettura** su un branch del core, senza comandi (nessun effetto
       finanziario), restando i comandi dopo il core;
   (c) autorizzare l'intera Control API in parallelo (sconsigliato: i comandi poggerebbero su schede
       core ancora FAIL in #586).
   Raccomandazione: **(b)**.
2. **Serialità in Pickfair-nogui.** Le regole vigenti ammettono una sola PR attiva per repository e oggi
   ci sono #606 e #607 di Claude B. Un branch Control API resterebbe senza PR fino al vostro GO e fino
   alla chiusura delle PR di Claude B: confermare.
3. **SL/TP/trailing e tavoli Roserpina**: nessuna route dedicata nelle 25 approvate. Confermare che
   bastano lettura (positions/exposure/status) e `PATCH /v1/config`, senza nuove route.

## 7. Prima fase di sviluppo proposta (MCP, senza PR fino al GO)

Sequenza Fase A, aggiornata (01b e 01c fatte, 04f ferma):
**02a → 02d → 02b → 02c → 02e → 05a → 03a → 03b → 04a → 04b → 04d → 04e → 05b → 05c → 04f → 07a**.

Prima scheda: **MCP-02a** (#7) — `get_status`, `get_reconciliation_status`.

- File: `tools/status.py`, modelli strict in `contract/models.py`, metodi raw nell'adapter
  (`get_status_raw`, `get_reconciliation_status_raw`) e scenari nell'adapter simulato
  (SIM pronto, LIVE bloccato, STOP attivo, riconciliazione in corso, risposta malformata).
- Regole: handshake compatibile prima della chiamata; campo mancante/tipo errato ⇒
  `UPSTREAM_INVALID_RESPONSE`; modalità solo SIM/LIVE; testo dei blocker restituito come dato;
  nessun default silenzioso; retry solo lettura (`read_with_retry`).
- Prove HT-1: RED → GREEN, unit + integration L2 + L3, injection/campi extra/NaN/payload enormi,
  mutanti critici estesi al 100 %, mutmut ≥ 85 %, regressione completa.
- Gate: branch, nessuna PR finché non arriva il GO; poi `independent-review` sulla head esatta.

Stima per arrivare alla copertura funzionale completa, partendo da oggi:
- MCP su adapter simulato (13 letture + preparazione comandi): ~15 schede, eseguibili ora.
- Control API nel core: ~4–6 passi (stima #1), dopo la decisione al §6.
- Integrazione reale e certificazione: 01d, 02g, 04h, 05d, 07b (dipendono dalla Control API);
  LIVE 06a/06b/07c solo con mandato owner.
