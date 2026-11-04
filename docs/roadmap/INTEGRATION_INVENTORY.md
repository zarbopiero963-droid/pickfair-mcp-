# INTEGRATION INVENTORY — copertura MCP + Control API per area funzionale

Aggiornato 04/11/2026 · MCP-01f · base core `ada40765` (Pickfair-nogui `main`) · Claude C.

Livelli (cumulativi, ognuno richiede un'evidenza; senza evidenza il livello NON è raggiunto):

| Livello | Significato | Evidenza richiesta |
|---|---|---|
| `CORE_AVAILABLE` | il core possiede il dato o la funzione e si può leggere senza effetti | riferimento file:riga sul `main` |
| `CONTROL_API_IMPLEMENTED` | route servita dal ponte del core + `pickfair_control_api` | patch/branch con SHA, test del ponte |
| `MCP_IMPLEMENTED` | tool MCP registrato, contratto e schema hash | commit MCP, descrittore |
| `TESTED` | unit + integrazione + negativi + mutazioni + E2E fra processi col core reale (in SIM) | conteggi e SHA |
| `INTEGRATED` | ponte mergiato in Pickfair-nogui `main` | SHA di merge (Claude B, merge owner) |
| `CERTIFIED` | review indipendente + verifica d'integrazione di Claude B + certificazione #586 | dossier |

Oggi **nessuna area è INTEGRATED né CERTIFIED**: i ponti MCP-01d, MCP-01e e MCP-01f sono patch consegnate a
Claude B, da integrare dopo #608 e #606 con una PR indipendente e safety-critical.

## Stato per area (priorità owner)

| # | Area | Livello raggiunto | Route / tool | Evidenza | Prossimo passo |
|---|---|---|---|---|---|
| 1 | Stato del sistema | `TESTED` | `GET /v1/status` · `get_status` | MCP-01d `647d5e8d`; patch core `505f579c…`; E2E core reale 9/9 ×3 | integrazione (Claude B) |
| 2 | Diagnostica Trading Engine | `TESTED` | `GET /v1/status` (`engine`) · `get_status` | MCP-01f; `TradingEngine.readiness()` (salute calcolata all'avvio del motore), connessione Betfair dagli attributi del servizio, feed, I/O, bus, code; test core + mutazioni 37/37; E2E 10/10 ×3 | integrazione (Claude B); in headless il `TradingEngine` è iniettato da `headless_main`, nei test d'integrazione è assente e dichiarato indisponibile |
| 3 | Inventario tavoli Roserpina | `TESTED` | `GET /v1/exposure` · `get_exposure` | MCP-01e (questo branch); `TableManager.snapshot()` sotto lock; test core 22 + mutazioni 24/24; E2E 9/9 ×3 | integrazione (Claude B) |
| 4 | Posizioni aperte e ordini | posizioni `TESTED` · ordini `CORE_AVAILABLE` (parziale) | `GET /v1/positions` · `list_positions`; `GET /v1/orders` | MCP-01f: `PositionLedger` Decimal sotto il lock del `PnLEngine`; ordini SIM `list_current_orders()` puro; **LIVE: nessuno stato in memoria** (solo DB o rete) | MCP-01g: ordini SIM + AMBIGUOUS dal reconciliation engine; ordini LIVE da progettare con Claude B/D |
| 5 | Bankroll, riserve, esposizione | `TESTED` (bankroll, esposizione) · `CORE_AVAILABLE` (riserve) | `GET /v1/account`, `GET /v1/exposure` | MCP-01e; `RiskDesk.debug_snapshot()`/`cash_basis()` sotto lock; riserve pendenti: `TableManager.pending_exposure()` **non è puro** (pota i tombstone, `table_manager.py:480`) | chiedere a Claude B una lettura pura delle riserve |
| 6 | Stato Money Management | `TESTED` (desk mode) · `CORE_AVAILABLE` (parametri) | `GET /v1/account` (`desk_mode`), `GET /v1/config` | `determine_desk_mode` puro (`core/money_management.py:131`); parametri in `RoserpinaConfig` (`core/system_state.py:61`) | MCP-01g: `get_config` redatto |
| 7 | Configurazioni operative | `CORE_AVAILABLE` | `GET /v1/config` · `get_config` | `RuntimeController.config` (dataclass); segreti da redigere: `database._SECRET_FIELDS` (`database.py:22-38`), `core/redaction.py` | MCP-01g |
| 8 | Strategie e segnali | strategie: **assenti nel core** · segnali: `CORE_AVAILABLE` (parziale) | nessuna route approvata | `CAP-STR-*` CORE_BLOCKED; `last_signal_at`; `duplication_guard.snapshot()` **non è puro** (TTL, `core/duplication_guard.py:217`); `signal_queue` non raggiungibile dal runtime | **decisione owner K3** (route) + core (Claude D) |
| 9 | Mercati, quote, liquidità | `CORE_AVAILABLE` | `GET /v1/markets`, `GET /v1/markets/{id}/book`, `GET /v1/events` | `MarketTracker.snapshot()`/`get_market()` puri (`core/market_tracker.py:107-109`); `liquidity.py` funzioni pure | MCP-01h (dipende da F-23 di Claude D per lo stato dei mercati) |
| 10 | Simulazioni e risultati | `TESTED` (saldo SIM via `get_account`, `execution_mode=SIM`) · `CORE_AVAILABLE` (settlement) | `GET /v1/account`; risultati: `GET /v1/orders` (cleared) o K3 | `SimulationBroker.list_settlements()` puro sotto lock (`simulation_broker.py:1267`); `snapshot()` del broker NON puro (cache) | MCP-01f/g |
| 11 | Stato delle protezioni | `TESTED` | `GET /v1/status` (`protections`) | MCP-01f: 22 protezioni, UNKNOWN/UNAVAILABLE mai «sicuro»; regole del core chiamate direttamente; freschezza fondi = gate attuale del core (120 s); stato negoziabile del mercato `UNAVAILABLE` (F-23) | integrazione; aggiornare quando arrivano F-16/F-11/F-12/F-23 di Claude D |
| 12 | Audit, eventi, riconciliazione | riconciliazione `TESTED` · audit `CORE_AVAILABLE` (parziale) | `GET /v1/reconciliation/status`, `GET /v1/audit/{correlation_id}` | MCP-01d; audit per correlazione: solo `get_recent_audit_events_for_diagnostics()` (DB, `database.py:2528`), nessun indice per `correlation_id`; log: K3 | audit: progettare con Claude B; log: K3 |
| 13 | Stato suite e certificazione | non è stato del runtime | nessuna (K3) | registro #586 e CI vivono su GitHub, non nel processo Pickfair | **decisione owner K3**: route dedicata o lettura fuori banda |

## Note di metodo

- «Puro» = nessuna rete, nessuna scrittura su DB, nessun publish sul bus, nessuna mutazione di stato;
  verificato leggendo il codice sul `main` e, per le aree `TESTED`, con prove di assenza di effetti
  sul runtime reale avviato in SIM (DB, bus, saldi, chiamate a broker/Betfair, stato profondo).
- I livelli `TESTED` valgono per il codice dei branch indicati, non per Pickfair-nogui `main`.
- Le aree che dipendono da correzioni in corso di Claude D (AMBIGUOUS P0, F-16 freschezza fondi,
  F-11 equity peak, F-12 drawdown, F-23 stato mercati) restano a `CORE_AVAILABLE` finché il codice non
  arriva su `main`: il MCP non duplica la logica finanziaria e non simula ciò che il core non ha.
