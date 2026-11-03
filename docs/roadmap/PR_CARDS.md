# PR CARDS — schede PF-MCP-001 … PF-MCP-037

Versione **0.1-DRAFT** · 03/11/2026. Una scheda ≠ una PR: ogni scheda diventa una o più PR solo con GO owner,
una PR aperta alla volta per repository. Gli ID storici (MCP-xx in pickfair-mcp- #3–#32; PF-API-0/1/commands,
PRxx in #461/#491; B-xxx in #586) restano validi: ogni scheda dichiara quali assorbe o da quali dipende.

## 0. Standard comune (vale per ogni scheda salvo deroga scritta)

**STD-TEST** — batteria minima (MCP-HT-1 di pickfair-mcp- #1 + CLAUDE.md di Pickfair-nogui):
RED prima della modifica e GREEN dopo; unit + integration + regressione completa; ruff/format/mypy strict
(MCP) o py_compile + pytest mirato + suite (core); mutanti critici 100 % KILLED, mutmut ≥ 85 % (MCP);
test negativi e ostili (campi extra, NaN/Inf, bool numerici, payload enormi, injection nei dati upstream);
timeout e connessione persa; prove L3 sul processo reale quando la scheda tocca tool o trasporto.
Livelli L1–L6 mai equivalenti (L2 simulato ≠ L4 Control API reale ≠ L5 core SIM).

**STD-EVID** — evidenza di ogni PASS: SHA esatti (entrambi i repository quando cross-repo), comando,
ambiente (OS, Python, versioni, modalità, key Delayed/Live), numero di esecuzioni, risultato, log, limiti.
Stati ammessi: PASS / FAIL / BLOCKED_ENV / NOT_RUN / NOT_VERIFIED. Riproduzione: comando unico documentato
nel dossier. In corsia certification: esecuzione via catalogo e dispatcher (#606), evidenza firmata.

**STD-GATE** — Q1–Q6 di `CERTIFICATION_GATES.md`; review indipendente sullo SHA esatto (MCP: status
`independent-review`; core: Sol + Grok + Codex triagiato, §0.7 spec); nessun thread irrisolto; fix loop
≤ 10 cicli. **Merge: solo owner** (direttiva 03/11, conflitto K7). File protetti (workflow, `scripts/pr_*`,
`review_gate.py`, AGENTS/CLAUDE/spec) = merge owner manuale sempre.

**STD-ROLLBACK** — revert del commit di merge; nessuna migrazione di dati irreversibile senza piano di
ritorno scritto; per il core: config esistente intatta, DB compatibile all'indietro, STOP persistente
mantenuto; per il MCP: tool rimosso dal registro = capacità di nuovo non esposta (fail-closed).

**Branch:** il lavoro di progettazione vive su `ccr-edf04c7d-e7vtj1`. Per ogni PR, dopo GO: branch
`pf-mcp-<NNN>-<slug>` dal `main` aggiornato del repository interessato.

**Stati scheda:** READY (eseguibile ora), READY_SIM (eseguibile solo su adapter simulato: non certificabile
come integrazione), BLOCKED_CORE, BLOCKED_CONTROL_API, BLOCKED_OWNER, BLOCKED_INFRA (#606 non attivo).

---

## FASE 00 — Inventario e contratti

### PF-MCP-001 — Inventario esaustivo delle capacità
- **Obiettivo:** portare il catalogo da v0.1 (222 voci) a inventario esaustivo e difendibile.
- **Repo/branch:** pickfair-mcp- (`docs/roadmap/`); lettura di Pickfair-nogui senza modifiche.
- **Core/dipendenze:** dossier B1 di #506 (A 872, B 344, **1.062 differenze aperte**, 125 righe Control API —
  oggi non nel repository: #606 lo marca `NOT_IMPORTED`), #586 (84 righe + 42 chiavi GUI), #495, #461.
- **Funzionalità:** tutte le aree; aggiunge GUI riga per riga, strategie storiche, streaming, sicurezza core.
- **Invarianti:** nessuna voce sparisce senza stato motivato; nessuna voce inventata senza file:riga o fonte.
- **Test:** controllo automatico di unicità degli ID e di presenza di fonte per riga (in 037).
- **PASS:** ogni comportamento del dossier B1 e di #586 mappato a un CAP-ID o a un N/A motivato; revisore
  indipendente concorda sul denominatore. **FAIL:** voci orfane, fonti mancanti.
- **Evidenze:** diff del catalogo, tabella di riconciliazione fonte→CAP-ID, hash del dossier importato.
- **Reviewer:** istanza indipendente (Grok), non l'autore. **Rollback:** documentale.
- **Stato:** READY per la parte su fonti accessibili; **BLOCKED_OWNER** per il dossier B1 (serve che
  l'owner renda disponibile l'archivio o ne autorizzi la ricostruzione dai 44 chunk di #461).
- **Schede esistenti:** B-CTL-01 (#586, «inventario Control API»), Gate A #506.

### PF-MCP-002 — Matrice Core → Control API → MCP → Test → Evidenza
- **Obiettivo:** tracciabilità bidirezionale per ogni CAP-ID, con i tre livelli di readiness.
- **Repo/branch:** pickfair-mcp- docs. **Dipendenze:** 001.
- **Funzionalità:** colonne test (file/test id), evidenza (dossier), certificazione (verdetto).
- **PASS:** ogni CAP applicabile ha almeno un test pianificato e un criterio; nessun test senza CAP.
- **Evidenze:** matrice generata da 037. **Stato:** READY (v0.1 in `FUNCTIONAL_COVERAGE_MATRIX.md`).
- **Schede esistenti:** #586 A.2 (tracciabilità 84 righe), #506 Gate A.

### PF-MCP-003 — Catalogo versionato dei contratti
- **Obiettivo:** per ogni route e tool: schema input/output, errori, identificativi, idempotenza, scope,
  criteri di accettazione; versione e schema hash.
- **Repo/branch:** pickfair-mcp- (`docs/contract_v1.md` esteso) e, a GO, descrittore canonico condiviso.
- **Dipendenze:** decisioni tecniche D-07, D-10, D-11, handle MANUAL, campi `/v1/meta` (PF-API-0).
- **Invarianti:** nessun payload mutante congelato prima della stabilizzazione del core (#491).
- **Test:** il test esistente `test_contract_doc_table_matches_code` esteso agli schemi.
- **PASS:** 25 route + candidate RC ratificate descritte; hash calcolato da descrittore unico.
- **Stato:** READY per letture (PROVISIONAL); BLOCKED_OWNER per i punti D-xx.
- **Schede esistenti:** PF-API-0 (parte contratto), MCP-01a.

## FASE 01 — Fondamenta Control API

### PF-MCP-004 — Control API versionata, schemi e adapter reali
- **Obiettivo:** Control API in-process nel core, loopback, versionata; adapter HTTP reale nel MCP.
- **Repo/branch:** Pickfair-nogui (`control_api/`) + pickfair-mcp- (`adapters/http.py`).
- **Core/dipendenze:** **PF-API-0** (command contract neutro, readiness MCP-aware, `operation_id`,
  provenienza) e **PF-API-1** (letture); #586 P0–P3 per le capacità servite; risposta owner all'ordine
  Control API (opzione a/b/c dell'audit).
- **Funzionalità:** CAP-MET-01…03, 13, 16; CAP-SEC-01, 06.
- **Invarianti:** nessun accesso Betfair/DB dal layer API; nessuna copia di MM/risk/cashout; solo IP
  loopback letterale; redirect rifiutati; campi extra/NaN/Inf/bool rifiutati.
- **Test:** STD-TEST + server reale su porta effimera loopback; bind su indirizzo non loopback ⇒ rifiuto;
  re-handshake a ogni riconnessione; version mismatch ⇒ CONTRACT_INCOMPATIBLE e zero mutazioni.
- **PASS:** MCP-01d e MCP-02g a L4 sulla Control API reale. **FAIL:** qualsiasi lettura da mock in L4.
- **Stato:** **BLOCKED_CORE** + **BLOCKED_OWNER** (ordine Control API).
- **Schede esistenti:** PF-API-0, PF-API-1, MCP-01d (#6), MCP-02g (#13), PR36 (API legacy).

### PF-MCP-005 — Autenticazione, autorizzazione per tool e per operazione
- **Obiettivo:** auth MCP ↔ Control API (D-11); scope per tool già presenti (MCP-01c) estesi per operazione.
- **Repo/branch:** entrambi. **Dipendenze:** 004, 034 (modello privilegi), D-11.
- **Funzionalità:** CAP-SEC-01…04, CAP-AUD-09.
- **Invarianti:** scope mai dedotti da argomenti o testo upstream; nessuna credenziale in stdout/stderr/
  audit/journal; principal `local-stdio` resta solo `read`; revoca immediata.
- **Test:** read principal invoca write ⇒ FORBIDDEN prima dell'upstream; token scaduto/alterato/replay ⇒
  rifiuto; mutante «scope ignorato» KILLED.
- **Stato:** READY_SIM per la parte MCP già fatta (MCP-01c); **BLOCKED_CORE** per l'auth della Control API.
- **Schede esistenti:** MCP-01c (fatta), MCP-01d, MCP-04f.

### PF-MCP-006 — Idempotenza, correlazione, timeout, errori tipizzati
- **Obiettivo:** catena request_id → operation_id → correlation_id → customer_ref → bet_id; nessuna doppia
  esecuzione su retry/timeout.
- **Repo/branch:** entrambi. **Dipendenze:** PF-API-0 (operation_id), PR26-a (fatta), F-13a (fatta), D-10.
- **Funzionalità:** CAP-MET-04…09, 11…15.
- **Invarianti:** stessa chiave logica ⇒ stessa operazione, zero publish aggiuntivi; timeout dopo invio ⇒
  AMBIGUOUS, mai retry; retry di lettura non implica retry di scrittura.
- **Test:** due processi concorrenti con la stessa richiesta; kill fra `sent` e `outcome`; risposta persa;
  risposta duplicata; riavvio con journal integro e corrotto.
- **Stato:** READY_SIM lato MCP (MCP-01b fatta); **BLOCKED_CORE** lato operation_id.
- **Schede esistenti:** MCP-01b, PF-API-0, PR47.

### PF-MCP-007 — Audit append-only, tracciabilità, osservabilità
- **Obiettivo:** audit immutabile per ogni operazione privilegiata; traccia end-to-end ricostruibile.
- **Repo/branch:** entrambi. **Dipendenze:** PR47 (correlation/audit), 006.
- **Funzionalità:** CAP-MET-07, CAP-AUD-01, 10, 11, CAP-CFG-10, CAP-MOD-07.
- **Invarianti:** append-only con checksum; redazione; nessun dato sensibile; audit separato dai log operativi.
- **Test:** manomissione di una riga ⇒ rilevata; traccia completa per ordine, cashout, config, mode switch.
- **Stato:** READY_SIM lato MCP (audit stderr esistente); **BLOCKED_CORE** per PR47.
- **Schede esistenti:** MCP-02e (#11), PR47.

### PF-MCP-034 — Modello dei privilegi a sei livelli (nuova, addendum §6)
- **Obiettivo:** READ, SIMULATE, CONFIGURE, OPERATE, EMERGENCY, ADMIN con least privilege e no escalation.
- **Repo/branch:** pickfair-mcp- (`auth/`), poi Control API. **Dipendenze:** decisione owner **K4**.
- **Mappatura proposta (da ratificare):**

  | Livello | Scope MCP attuale | Tool |
  |---|---|---|
  | READ | `read` | 14 letture |
  | SIMULATE | (nuovo) | `preview_order`, preview dutching/cashout |
  | CONFIGURE | `owner` | `patch_config` |
  | OPERATE | `write` | place/dutching/cancel/replace/cashout/stop non-EMERGENCY/reconcile |
  | EMERGENCY | `owner` | `stop` EMERGENCY |
  | ADMIN | `admin` | nessun tool finanziario; mai trading reale implicito |
  | (owner-only invariato) | `owner` | `resume`, `set_mode` |

- **Invarianti:** `resume` e `set_mode` restano owner-only (decisione C1, 22/10); ADMIN non implica OPERATE;
  nessuna gerarchia implicita (insiemi espliciti, come oggi).
- **Test:** matrice completa livello × tool, PASS e BLOCK; mutanti su ogni riga della mappa.
- **Stato:** **BLOCKED_OWNER** (K4). **Schede esistenti:** MCP-01c, MCP-04f.

## FASE 02 — Lettura integrale (solo sorgenti reali del core; campo assente ⇒ «indisponibile», mai default)

### PF-MCP-008 — Stato runtime, SIM/LIVE, STOP, readiness, health, riconciliazione
- **Repo:** entrambi. **Core:** `RuntimeController.get_status`, `evaluate_live_readiness`,
  `get_effective_execution_mode`, `get_deploy_gate_status`, `ReconciliationEngine`.
- **Funzionalità:** CAP-RT-01…08, CAP-MOD-01, CAP-REC-01, CAP-STP-08/10.
- **Invarianti:** modalità solo SIM/LIVE (HYBRID riconosciuta come disabilitata); nessuna modalità dedotta
  dalla App Key; testo dei blocker restituito come dato; nessuna cache che maschera uno stato più recente.
- **Test:** scenari SIM pronto, LIVE bloccato, STOP attivo, riconciliazione in corso, risposta malformata,
  injection nei blocker, campi extra.
- **PASS:** L2 ora; L4/L5 quando PF-API-1 serve `/v1/status`.
- **Stato:** **READY_SIM** (= MCP-02a #7, prima scheda consigliata); BLOCKED_CORE per CAP-RT-05.
- **Schede esistenti:** MCP-02a, PF-API-0 (readiness MCP-aware).

### PF-MCP-009 — Eventi, mercati, quote, liquidità, ricerca, aggiornamenti
- **Core:** `CatalogSyncService`, `DeterministicResolver` (PR08), `betfair_service`, `streaming_feed` (PR11).
- **Funzionalità:** CAP-MKT-01…11, CAP-RT-11.
- **Invarianti:** risoluzione per nome deterministica o errore esplicito (mai LIMIT 1 ambiguo); freshness
  sempre dichiarata; dati stantii marcati, mai presentati come attuali.
- **Test:** nomi ambigui ⇒ errore; book stantio ⇒ freshness scaduta; mercato sospeso; injection nei nomi.
- **Stato:** **READY_SIM** (= MCP-02c #9); BLOCKED_CORE per stream (PR11) e Order Stream.
- **Schede esistenti:** MCP-02c, MCP-02f, PR08, PR11.

### PF-MCP-010 — Strategie, segnali, attivazioni, configurazioni, diagnostica (dove implementati)
- **Core:** nessuna strategia nel core; segnali solo Telegram (sospeso); `signal_dedupe`, `signal_queue`.
- **Funzionalità:** CAP-STR-01…05 (CORE_BLOCKED), CAP-SIG-02…05, 07.
- **Invarianti:** nessuna strategia inventata, nessuna strategia predefinita; Telegram resta sospeso.
- **Test:** lettura dello stato «non disponibile» esplicita; nessun tool di attivazione Telegram.
- **Stato:** **BLOCKED_CORE** (K2) + **BLOCKED_OWNER** (K3, K6).
- **Dipendenza nuova (Corsia B):** scheda core «contratto CRUD strategie» da creare in #586/#461.

### PF-MCP-011 — Roserpina: tavoli singoli, aggregati, eventi, esposizione, stato
- **Core:** `TableManager` (`snapshot_table`, `allocate`, `activate`), `risk_desk`, `RoserpinaConfig`.
- **Funzionalità:** CAP-ROS-02…04, 06…08, 11, 12; CAP-RT-02.
- **Invarianti:** il MCP non calcola nulla di Roserpina; snapshot coerente (letto sotto il lock del core).
- **Test:** 2/5/10 tavoli; tavolo in recovery; tombstone; snapshot durante allocazione concorrente.
- **Stato:** **BLOCKED_OWNER** (K3: dentro `/v1/exposure` o route `GET /v1/tables`) + BLOCKED_CONTROL_API.
- **Schede esistenti:** ROS-01/02 (#586), proposta in `contract_v1.md` punto 2.

### PF-MCP-012 — Bankroll, MM, stake, commissioni, limiti, motivi di rifiuto
- **Core:** funds, `SimulationBroker`, `money_management`, `risk_gate`, `loss_limits`, `daily_loss_store`.
- **Funzionalità:** CAP-BKR-01…17, CAP-ROS-13.
- **Invarianti:** saldo SIM e LIVE separati (PR15); nessun cap predefinito; freschezza fondi dichiarata
  (decisione 30 s; codice oggi 120 s ⇒ conflitto C2 #586 da chiudere nel core).
- **Test:** saldo stantio ⇒ indisponibile; SIM non contamina LIVE; commissione 4,5 %; microstake 0,10 €
  in Decimal; motivi di rifiuto stabili.
- **Stato:** **READY_SIM** per esposizione/posizioni (= MCP-02b #8); BLOCKED_CORE per FUNDS/DD/PR15.

### PF-MCP-013 — Posizioni, ordini, settlement, cashout, SL/TP/trailing, anomalie
- **Core:** `position_ledger`, `listCurrentOrders/listClearedOrders`, `pnl_engine`, `observability/`.
- **Funzionalità:** CAP-ORD-09/10/14/15, CAP-MET-14/15, CAP-SET-01…03, CAP-SLT-06, CAP-AUD-14.
- **Invarianti:** AMBIGUOUS visibile come tale; nessuna posizione «chiusa» con esposizione residua.
- **Test:** ordine parziale, unmatched oltre TTL, ordine ghost, settlement incerto.
- **Stato:** **READY_SIM** (= MCP-02d #10, MCP-02e #11); BLOCKED_CORE per operation_id e SET-01/02.

### PF-MCP-033 — Accesso a log e diagnostica (nuova, addendum §5)
- **Obiettivo:** ricerca, filtri, paginazione, correlazione, esportazione autorizzata e redatta.
- **Repo:** entrambi. **Core:** `event_log`, `event_journal`, `safety_logger`, `observability/`.
- **Funzionalità:** CAP-AUD-02…09, 12, 15.
- **Invarianti:** solo log redatti prodotti dal core; nessun log Betfair grezzo; log operativi ≠ evidenze
  immutabili; il contenuto dei log è dato, mai istruzione.
- **Test:** segreti fittizi iniettati nei log ⇒ assenti dall'output; paginazione stabile; filtri ostili.
- **Stato:** **BLOCKED_OWNER** (K3: route `GET /v1/logs`, K8) + BLOCKED_CONTROL_API.

## FASE 03 — Controllo operativo (solo SIM; nessun comando real-money; comandi esposti solo dopo PF-API commands)

### PF-MCP-014 — Modifica sicura delle configurazioni, validazione, rollback
- **Core:** `config_store`, `atomic_io`, `settings_service`, `reload_config` (PR28).
- **Funzionalità:** CAP-CFG-01…10, CAP-ROS-01/07, CAP-BKR-16.
- **Invarianti:** nessuna mutazione parziale; config malformata ⇒ zero effetti; reload preserva tavoli,
  esposizione, pending, identità; segreti mai leggibili né scrivibili via MCP; solo owner.
- **Test:** patch concorrenti; save fallito; crash durante write; patch con chiave sconosciuta; dry-run.
- **Stato:** READY_SIM lato MCP (= MCP-03a #14, comando non esposto); BLOCKED_CORE (PF-API commands, CFG-01..07).

### PF-MCP-015 — Gestione autorizzata di strategie, segnali e tavoli Roserpina
- **Funzionalità:** CAP-STR-01…05, CAP-ROS-01, 05, 09, 10; CAP-RT-10.
- **Invarianti:** nessuna strategia predefinita; STOP per tavolo solo se il core lo implementa.
- **Stato:** **BLOCKED_CORE** (strategie, STOP per tavolo) + **BLOCKED_OWNER** (K2, K3).

### PF-MCP-016 — Preview, validazione e invio ordini BACK/LAY via gateway esistente
- **Core:** `trading_engine`, `order_router`, MM, `risk_gate`, `safety_layer`, microstake, F-13a.
- **Funzionalità:** CAP-ORD-01…08, 11…19, 22; CAP-BKR-07/08.
- **Invarianti:** un segnale = un ordine; preview a zero effetti; stake esatto o rifiuto; LAY liability
  stake×(price−1); fondi insufficienti = blocco; mercato sospeso = nessun ingresso; timeout ⇒ AMBIGUOUS.
- **Test:** STD-TEST + due agenti stesso ordine ⇒ una esecuzione; quota cambiata ⇒ rivalidazione secondo
  policy (CAP-ORD-16 oggi assente ⇒ test RED atteso); saldo insufficiente senza effetti; microstake 0,10 €.
- **Stato:** READY_SIM lato MCP (= MCP-04a #16, 04b #17, 04d #19, non esposti); **BLOCKED_CORE** (PF-API commands).

### PF-MCP-017 — Cashout, chiusure, posizioni parziali e riconciliazione (base)
- **Funzionalità:** CAP-REC-02, 05, 06; percorso base `POST /v1/cashout` (dettaglio integrale in 035).
- **Stato:** READY_SIM lato MCP (= MCP-05b #25, 05c #26); BLOCKED_CORE (PR43–45).

### PF-MCP-018 — Stop-loss, take-profit, trailing e parametri MM
- **Core:** `_monitor_sl_tp_trailing`, `sl_tp_pnl`, PR24, PR25.
- **Funzionalità:** CAP-SLT-01…07, CAP-CSH-17, 20.
- **Invarianti:** SL/TP non propagato ⇒ il test fallisce e la config non è dichiarata applicata; il monitor
  non dipende solo dalla callback stream senza rilevare la perdita dello stream.
- **Stato:** **BLOCKED_CORE** (PR24/25, stream).

### PF-MCP-019 — STOP d'emergenza, pausa, resume, cambio modalità, controlli privilegiati
- **Core:** `pause`, `stop`, `risk_stop`, `emergency_stop`, `resume`, `reset_*`, `force_lockdown`,
  `set_simulation_mode`, PR37.
- **Funzionalità:** CAP-STP-01…10, CAP-MOD-04, CAP-RT-09.
- **Invarianti:** semantica PAUSE/STOP/RISK_STOP/EMERGENCY del contratto; RESUME solo dopo nuova readiness;
  EMERGENCY senza eccezioni; nessuna nuova esposizione dopo STOP; resume/set_mode owner-only.
- **Test:** STOP durante operazione in volo; STOP + riavvio; resume da non-owner ⇒ FORBIDDEN.
- **Stato:** READY_SIM lato MCP (= MCP-05a #24, MCP-03b #15); BLOCKED_CORE (PR37, PF-API commands).

### PF-MCP-032 — Macchina a stati formale delle modalità (nuova, addendum §4)
- **Obiettivo:** stati, transizioni legali, precondizioni, conferma owner, atomicità, audit.
- **Proposta (da ratificare, K1):** due assi invece di nuove modalità.

  | Asse | Valori | Note |
  |---|---|---|
  | Sorgente dati | `REPLAY` (solo test), `DELAYED`, `LIVE_FEED` | la key non decide l'esecuzione |
  | Esecuzione | `SIM` (virtuale), `REAL` | `REAL` solo con mandato LIVE o GO REAL-EXECUTION per caso |

  Combinazioni: DELAYED×SIM = REAL-DATA SIM (unico programma autorizzato, 27/10); REPLAY×SIM = solo test;
  LIVE_FEED×SIM = **vietato** (LIVE_DATA_SIM, 07/10) finché l'owner non revoca; ×REAL = LIVE gated;
  HYBRID_REAL_EXECUTION riconosciuta e rifiutata. Transizioni: richiesta → precondizioni (posizioni aperte,
  pending, riconciliazione coerente, credenziali presenti senza esporle) → conferma owner → commit atomico
  o rollback → audit con motivazione.
- **Invarianti:** nessun tool disattiva il gate LIVE; prezzi Delayed mai usati per decisioni real-money.
- **Test:** switch con posizioni aperte, durante riconciliazione, durante STOP; transizione illegale
  ⇒ BLOCKED; mutanti su ogni guardia.
- **Stato:** **BLOCKED_OWNER** (K1) + BLOCKED_CORE (CAP-MOD-02/05/06).
- **Schede esistenti:** MCP-03b, MCP-06a, PR15.

### PF-MCP-035 — Cashout integrale (nuova, addendum §2)
- **Funzionalità:** CAP-CSH-01…20, CAP-DUT-12.
- **Invarianti:** mai CLOSED con esposizione non riconciliata; nessun secondo hedge cieco; P/L netto con
  commissione; nessun importo fisso; liquidità/spread verificati dal core.
- **Test:** completo, parziale, tavolo, multiplo, all, Void, BACK/LAY misto, crash durante cashout,
  risposta persa, cashout duplicato, liquidità insufficiente.
- **Stato:** **BLOCKED_CORE** (PR43/44/45, CSH-01..12 #586; fatti F-01/F-05/F-06 da certificare).
- **Schede esistenti:** MCP-05b, MCP-05d, PR43–45, B-CSH-*.

### PF-MCP-036 — Dutching integrale e MANUAL a doppia conferma (nuova, addendum §3 e §7)
- **Funzionalità:** CAP-DUT-01…15, CAP-ORD-20, CAP-SEC-04.
- **Invarianti:** MM centrale, mai motore parallelo; Decimal; parziale ribilanciato/coperto/sospeso
  (PF-EXEC-02); MANUAL: preview → operation_id + handle breve → secondo comando owner; handle non
  riusabile; timeout = nessun ordine; conferma verificata fuori dall'agente (K5).
- **Test:** crash durante dutching multi-selezione; fill parziali; quote cambiate; handle scaduto,
  riusato, alterato.
- **Stato:** READY_SIM lato MCP (= MCP-04e #20); **BLOCKED_CORE** (MANUAL nel core, MCP-04c #18) +
  **BLOCKED_OWNER** (K5).

## FASE 04 — Robustezza estrema

### PF-MCP-020 — Recovery da crash di MCP, Control API e core
- **Funzionalità:** CAP-MET-10, CAP-REC-03, 04, 07…10, CAP-CFG-06, CAP-ORD-19, CAP-STP-08, CAP-ROS-12.
- **Test:** kill in ogni punto di HARD_TEST_CAMPAIGN §C; riavvio con STOP persistente; journal corrotto.
- **PASS:** zero ordini duplicati, zero esposizioni nascoste, nessun ACTIVE prima della riconciliazione.
- **Stato:** READY_SIM lato MCP (già coperto da MCP-01b); BLOCKED_CORE per PR33/PR34 e Control API.

### PF-MCP-021 — Concorrenza, race condition, richieste duplicate, ordering
- **Funzionalità:** CAP-ORD-11, CAP-CSH-14, CAP-RT-08, CAP-STP-09.
- **Test:** N agenti, stesso comando; config patch concorrente a ordine; STOP concorrente; fencing (PR32).
- **Stato:** BLOCKED_CORE (PR29/PR32, Control API).

### PF-MCP-022 — Guasti REST/stream, timeout, risposte ambigue, disconnessioni
- **Funzionalità:** CAP-MKT-08/09, CAP-ORD-12/22, CAP-REC-05, CAP-SLT-04, CAP-MET-13.
- **Test:** fault injection sul gateway simulato; perdita stream con SL/TP attivo; Control API giù a metà.
- **Stato:** BLOCKED_CORE (PR11, Order Stream, PF-API).

### PF-MCP-023 — Security hardening, segreti, autorizzazioni, comandi malevoli
- **Funzionalità:** CAP-SEC-05…11, CAP-CFG-09, CAP-MOD-08, CAP-MET-11.
- **Test:** HARD_TEST_CAMPAIGN §D; fuzzing degli schemi; secret scan; matrice OWASP API Top 10.
- **Stato:** READY_SIM lato MCP (guard esistenti); BLOCKED_CONTROL_API per il resto.

## FASE 05 — Test hard e certificazione

### PF-MCP-024 — End-to-end MCP → Control API → Core → Broker
- **Test:** processo MCP reale (stdio) + Control API reale + core SIM (SimulationBroker, Delayed reale in
  lettura via gateway read-only) su SHA esatti. Nessun mock nel percorso certificato.
- **Stato:** BLOCKED_CORE + BLOCKED_INFRA (#606). **Schede esistenti:** MCP-07b (#31), MCP-T01…T08.

### PF-MCP-025 — Campagne Roserpina multitavolo e Money Management
- **Test:** 2, 5, 10 tavoli e oltre entro i limiti dell'infrastruttura; vedi HARD_TEST_CAMPAIGN §B.
- **Stato:** BLOCKED_CORE (ROS-01/02, MM-01/02). **Esistente:** `SIM_MULTITABLE_CERTIFY` (catalogo #606).

### PF-MCP-026 — Fault injection, crash/restart, riconciliazione avversaria
- **Stato:** BLOCKED_CORE + BLOCKED_INFRA. **Esistente:** `tests/chaos`, `tests/failure`, `tests/recovery` del core.

### PF-MCP-027 — Test ostili, fuzzing, mutazioni
- **Stato:** READY_SIM lato MCP; BLOCKED_CONTROL_API. **Esistente:** `critical_mutations.py`, mutmut,
  catalogo mutazioni del core (`guardrails/mutation_catalog.json`).

### PF-MCP-028 — Certificazione di copertura, tracciabilità, verdetto indipendente
- **PASS:** le cinque dimensioni al 100 % (`CERTIFICATION_GATES.md` §5) sui SHA congelati; verdetto di un
  revisore diverso dall'esecutore. Qualunque FAIL/BLOCKED/NOT_TESTED su requisito obbligatorio ⇒ niente certificato.
- **Stato:** BLOCKED (dipende da 001–027).

### PF-MCP-037 — Registro automatico della copertura (nuova, roadmap §4)
- **Obiettivo:** `catalog/capabilities.json` versionato + generatore della matrice + calcolo delle cinque
  dimensioni; integrazione con `tests/catalog/behaviour_coverage.json` di #606, **senza** seconda infrastruttura.
- **Invarianti:** una capacità obbligatoria non esce dal denominatore senza decisione owner citata;
  `SKIPPED`/`BLOCKED`/`NOT_TESTED`/`INFRA_ERROR` contano come non-PASS.
- **Test:** mutanti «escludi voce dal denominatore», «conta SKIPPED come PASS» KILLED.
- **Stato:** READY (parte MCP); il collegamento al ledger dipende da #606 (BLOCKED_INFRA).

## FASE 06 — Rilascio controllato

### PF-MCP-029 — Compatibilità versioni, packaging, installazione verificabile
- **Stato:** READY_SIM per il packaging MCP (= MCP-07a #30); compat reale dopo 004.

### PF-MCP-030 — Collaudo sull'infrastruttura autorizzata, healthcheck, rollback
- **Vincolo:** nessun accesso VPS di Claude C; esegue chi l'owner autorizza. **Stato:** BLOCKED_OWNER.

### PF-MCP-031 — Audit finale indipendente e certificato di copertura funzionale
- **Stato:** BLOCKED (dipende da 028–030). LIVE: certificazione distinta (MCP-06a/06b/07c, mandato owner).

---

## Riepilogo stato delle 37 schede

| Stato | Schede |
|---|---|
| READY (documentale) | 001 (parziale), 002, 003 (letture), 037 (parte MCP) |
| READY_SIM (adapter simulato, non certificabile come integrazione) | 008, 009, 012 (parte), 013, 005/006/007 (parte MCP), 014/016/017/019/036 (preparazione, comandi non esposti), 020/023/027 (parte MCP), 029 (packaging) |
| BLOCKED_CORE / CONTROL_API | 004, 010, 011, 015, 018, 021, 022, 024, 025, 026, 035 |
| BLOCKED_OWNER | 032 (K1), 034 (K4), 033 (K3/K8), 011 (K3), 010/015 (K2), 036 (K5), 030, 001 (dossier B1) |
| BLOCKED a valle | 028, 031 |

Corrispondenza con le 30 schede MCP esistenti: tutte assorbite (MCP-01a…07c). Nessuna rinumerata o cancellata.
