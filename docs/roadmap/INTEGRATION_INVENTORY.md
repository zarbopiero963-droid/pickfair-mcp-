# INTEGRATION INVENTORY — copertura MCP + Control API per area funzionale

Aggiornato 05/11/2026 · MCP-01l · base core `ada40765` (Pickfair-nogui `main`) · Claude C.
Aggiornato 05/11/2026 · MCP-01i · base core `ada40765` (Pickfair-nogui `main`) · Claude C.

Livelli (cumulativi, ognuno richiede un'evidenza; senza evidenza il livello NON è raggiunto):

| Livello | Significato | Evidenza richiesta |
|---|---|---|
| `CORE_AVAILABLE` | il core possiede il dato o la funzione e si può leggere senza effetti | riferimento file:riga sul `main` |
| `CONTROL_API_IMPLEMENTED` | route servita dal ponte del core + `pickfair_control_api` | patch/branch con SHA, test del ponte |
| `MCP_IMPLEMENTED` | tool MCP registrato, contratto e schema hash | commit MCP, descrittore |
| `TESTED` | unit + integrazione + negativi + mutazioni + E2E fra processi col core reale (in SIM) | conteggi e SHA |
| `INTEGRATED` | ponte mergiato in Pickfair-nogui `main` | SHA di merge (Claude B, merge owner) |
| `CERTIFIED` | review indipendente + verifica d'integrazione di Claude B + certificazione #586 | dossier |

Oggi **nessuna area è INTEGRATED né CERTIFIED**: i ponti MCP-01d … MCP-01h, MCP-01j, MCP-01k e MCP-01l sono patch consegnate a
Claude B, da integrare dopo #608 e #606 con una PR indipendente e safety-critical.

## Stato per area (priorità owner)

| # | Area | Livello raggiunto | Route / tool | Evidenza | Prossimo passo |
|---|---|---|---|---|---|
| 1 | Stato del sistema | `TESTED` | `GET /v1/status` · `get_status` | MCP-01d `647d5e8d`; patch core `505f579c…`; E2E core reale 9/9 ×3 | integrazione (Claude B) |
| 2 | Diagnostica Trading Engine | `TESTED` | `GET /v1/status` (`engine`) · `get_status` | MCP-01f; `TradingEngine.readiness()` (salute calcolata all'avvio del motore), connessione Betfair dagli attributi del servizio, feed, I/O, bus, code; test core + mutazioni 37/37; E2E 10/10 ×3 | integrazione (Claude B); in headless il `TradingEngine` è iniettato da `headless_main`, nei test d'integrazione è assente e dichiarato indisponibile |
| 3 | Inventario tavoli Roserpina | `TESTED` | `GET /v1/exposure` · `get_exposure` | MCP-01e (questo branch); `TableManager.snapshot()` sotto lock; test core 22 + mutazioni 24/24; E2E 9/9 ×3 | integrazione (Claude B) |
| 4 | Posizioni aperte e ordini | `TESTED` (posizioni e ordini del ledger) | `GET /v1/positions` · `list_positions`; `GET /v1/orders` · `list_orders` | MCP-01f (posizioni Decimal); MCP-01g: ledger `orders` in sola lettura (SQLite `mode=ro` + `query_only`), mappa esplicita degli stati, hedge dei cashout, test core + mutazioni 51/51, E2E 11/11 ×3 | ordini LIVE sull'exchange (`listCurrentOrders`) restano fuori: richiederebbero rete; allineare alla correzione P0 AMBIGUOUS/betId di Claude D |
| 5 | Bankroll, riserve, esposizione | `TESTED` (bankroll, esposizione) · `CORE_AVAILABLE` (riserve) | `GET /v1/account`, `GET /v1/exposure` | MCP-01e; `RiskDesk.debug_snapshot()`/`cash_basis()` sotto lock; riserve pendenti: `TableManager.pending_exposure()` **non è puro** (pota i tombstone, `table_manager.py:480`) | chiedere a Claude B una lettura pura delle riserve |
| 6 | Stato Money Management | `TESTED` (desk mode, parametri) | `GET /v1/account` (`desk_mode`), `GET /v1/config` · `get_config` | `determine_desk_mode` puro (`core/money_management.py:131`); parametri di `RoserpinaConfig` (`core/system_state.py:61`) esposti da MCP-01j | integrazione (Claude B) |
| 7 | Configurazioni operative | `TESTED` (lettura redatta) | `GET /v1/config` · `get_config` | MCP-01j: allowlist di 42 chiavi, SET/NOT_SET/INVALID, credenziali mai lette, nomi sensibili solo contati (`core.redaction.is_sensitive_key` + frammenti del contratto); test core + mutazioni 75/75; E2E 13/13 | integrazione (Claude B); scrittura (`patch_config`) solo design, non esposta |
| 8 | Strategie e segnali | strategie: **assenti nel core** · segnali: `CORE_AVAILABLE` (parziale) | nessuna route approvata | `CAP-STR-*` CORE_BLOCKED; `last_signal_at`; `duplication_guard.snapshot()` **non è puro** (TTL, `core/duplication_guard.py:217`); `signal_queue` non raggiungibile dal runtime | **decisione owner K3** (route) + core (Claude D) |
| 9 | Mercati, quote, liquidità | `TESTED` (mercati, book) · eventi: non nel core | `GET /v1/markets` · `list_markets`, `GET /v1/markets/{id}/book` · `get_market_book`; `GET /v1/events` resta 501 | MCP-01l: `MarketTracker` copiato in una sola lettura, tre livelli per lato in Decimal, id del mercato validato in modo stretto (route con parametro); test core + mutazioni, E2E | integrazione (Claude B); età del book solo via `lastMatchTime` (richiesta non bloccante: istante di ricezione nel tracker); stato negoziabile = F-23 |
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

## Aggiunte MCP-01h (SL/TP, cashout, settlement)

| Area | Livello | Route / tool | Evidenza | Nota |
|---|---|---|---|---|
| SL/TP per tavolo | `TESTED` (lettura) | `GET /v1/exposure` · `get_exposure` | test core 11 + mutazioni 62/62; E2E 12/12 ×3 | sul `main` SL/TP non è mai armato (nessun percorso lo scrive); F-02 di Claude D lo introduce, contratto già compatibile; trailing assente nel core |
| Cashout in corso | `TESTED` | `GET /v1/status` (barriere, in volo, incerti) + `list_orders` (hedge) | idem | storico dei cashout: nessuna tabella dedicata nel core (solo righe hedge e `audit_events`) |
| Settlement | `TESTED` (conteggi) | `GET /v1/reconciliation/status` | idem | storico P/L di settlement con importi: da progettare (route K3 o estensione di `get_orders`) |

## Aggiunte MCP-01k (compatibilità con le correzioni di Claude D)

| Area | Livello | Route / tool | Evidenza | Nota |
|---|---|---|---|---|
| Ordini AMBIGUOUS dopo il fix P0 | `TESTED` | `GET /v1/orders` · `list_orders` | sonda sulla catena reale del branch P0 RED → GREEN; test core e E2E | importi del report non confermato mai esposti; betId mantenuto. Rapporto: `docs/handoff/compat_claude_d_20261105.md` |
| Freschezza dei fondi dopo F-16 | `TESTED` | `GET /v1/status` (`protections.funds_freshness`) | sonda sul codice reale di F-16 RED → GREEN | limite null finché il core non espone `funds_max_age_s()` |

## Aggiunte MCP-01i (stato della chiusura SL/TP, dipende da F-04)

| Area | Livello | Route / tool | Evidenza | Nota |
|---|---|---|---|---|
| Chiusura SL/TP per tavolo | `TESTED` (offline, su `main` + F-04 locale) | `GET /v1/exposure` (`sl_tp_closes`) · `get_exposure` | test core sulla catena reale di F-04 (scenari di D: tre tavoli, SL instradato, SL non eseguito); E2E fra processi | **non integrabile** finché F-04 (`claude/d-f04-sl-tp-close` @ `2d0cf4ca`) non è su `main`; hedge legati alla chiusura per id di richiesta (campo aggiunto da D su richiesta di MCP-01k); su un core senza F-04 la sezione è UNAVAILABLE `CORE_PENDING_F04` |

## Aggiunte MCP-01m (trailing F-03, F-02, F-18 — dipende da F-03)

| Area | Livello | Route / tool | Evidenza | Nota |
|---|---|---|---|---|
| Trailing stop per tavolo | `TESTED` (offline, su fusione locale di F-03) | `get_exposure` (`sl_tp.trailing`) | test core sulla logica reale `core.trailing_stop`; picco in memoria e persistito | non integrabile finché F-03 non è su `main` |
| Impostazioni non valide (F-18) | `TESTED` (offline) | `get_config` (`invalid_persisted`), `get_status` (`config_validity`) | test core con un valore persistito illeggibile reale | chiude il limite F-18 di MCP-01j |

## Aggiunte MCP-01n (età del book — dipende da `claude/d-market-book-age`)

| Area | Livello | Route / tool | Evidenza | Nota |
|---|---|---|---|---|
| Età del book per mercato | `TESTED` (offline, su fusione locale di `ea81e93e`) | `GET /v1/markets`, `GET /v1/markets/{id}/book` · `list_markets`, `get_market_book` (`book_age_s`) | test core sull'istante monotono reale del `MarketTracker` (orologio iniettato), ordine età→book provato; E2E fra processi | non integrabile finché il branch di D non è su `main`; senza, `book_age_s` è `null` |
