# Osservabilità MCP dei difetti finanziari Roserpina — matrice (PF-ROSERPINA-MCP-OBSERVABILITY-CLAUDE-C-20261109)

Autore: Claude C, 09/11/2026. Analisi in sola lettura. Nessuna modifica a codice, contratti o schema.

## Basi esaminate

- **Motore:** Pickfair-nogui PR #617 @ `dd7b7369`, cioè main `6519794` più BB-1. Lo stesso codice della campagna di Grok,
  con in più la scatola nera.
- **Contratto MCP:** pickfair-mcp-, branch congelato `869d2c0` e patch BB-1 `75e7280`.
- **Difetti di riferimento:** campagna Grok PF-ROSERPINA-5T-OFFLINE-20261109, Pickfair-nogui #586 c.6747305390.
  - B-1: riconciliazione dopo un crash con l'ordine in volo.
  - B-2: tavoli fermi in RECOVERY.
  - B-3: nessun controllo del prezzo stale.
  - S04/S05: SL/TP non collegati ai tavoli Roserpina; trailing assente.
  - D-1: drawdown non bloccato (auto-reset del picco; picco calcolato sul disponibile).
  - D-2: `drawdown_pct` conta l'esposizione aperta come perdita.
  - D-3: confronti in float.

## Fatti che valgono per tutta la matrice

1. **La scatola nera BB-1 registra solo il ciclo di vita.** Gli eventi scritti sono `PROCESS_START`, `COMPONENT_INIT`,
   `SHUTDOWN`, `UNCLEAN_TERMINATION`, `BLACKBOX_GAP`, `CRASH_RECOVERY`, `UNCAUGHT_EXCEPTION`, `TASK_EXCEPTION`,
   `EMERGENCY_STOP` e `CONTROL_API_REQUEST`. I tipi finanziari (`BANKROLL_READ`, `FUNDS_RESERVED`, `RISK_GATE_DENY`,
   `EXPOSURE_UPDATE`, `SL_TRIGGERED`, `RECONCILIATION_DIFF`, …) esistono solo nel vocabolario
   (`core/event_vocabulary.py`). Il motore non li emette: arrivano con BB-3, il percorso del denaro.
2. **Nemmeno il vecchio giornale riceve eventi finanziari.** `event_journal.append_event` ha un solo chiamante,
   `core/session_recorder.py:346`, e `SessionRecorder` non viene istanziato da nessuna parte. Oggi la storia
   finanziaria vive solo:
   - nel logger Python;
   - nel bus in memoria;
   - in alcune tabelle del DB: `audit_events`, `orders`, `order_saga`, `outbox`, `risk_position_history`, `settings`.

   L'MCP non legge nessuna di queste.
3. **Lo stato corrente esiste nel contratto MCP ma non è integrato.** I tool `get_account`, `get_exposure`,
   `list_positions`, `list_orders`, `get_status`, `get_reconciliation_status`, `get_config` e `get_market_book`
   esistono sui branch MCP. Il ponte del core che li alimenta è consegnato a B (13 handoff DURABLE), ma non è
   integrato su main. **Nel Pickfair che gira oggi non si osserva nulla via MCP.**
4. **L'MCP non calcola nulla di finanziario.** Mostra i valori del motore come il motore li ha calcolati. Quindi
   rende visibile un difetto solo se il valore errato, o la sua contraddizione con un altro valore, viene esposto.

## Legenda

- **DISPONIBILE:** già esposto da un tool MCP nel contratto, stato corrente. Va letto con il fatto 3: il contratto
  c'è, l'integrazione nel core no.
- **NON REGISTRATO:** il motore lo calcola o lo conserva, ma né l'MCP né la scatola nera lo leggono.
- **ASSENTE:** il motore non lo calcola, oppure non esiste un tipo di evento o un campo adatto.
- **BB-2/BB-3:** serve un'estensione futura del registro, nel repository di B.

## Matrice

| Area | DISPONIBILE via MCP (stato corrente) | NON REGISTRATO (motore) | ASSENTE | BB-2/BB-3 richiesto | Difetto Grok osservabile? |
|---|---|---|---|---|---|
| **1. Bankroll ed equity** | `get_account`: `bankroll_start`, `bankroll_current`, `equity_peak`, `equity_current`, `realized_pnl`, `unrealized_pnl`, `drawdown_pct`, `verified`, `cash_equity`; `exchange_funds` (available, committed, cash_equity, age_s) | storia delle letture (`risk_desk.py:95,131,200`): nessun log | — | `BANKROLL_READ` a ogni lettura verificata, con bankroll, cassa, impegnato ed età | **D-2 sì, come stato.** `bankroll_current` (il disponibile) e `cash_equity` sono esposti insieme, quindi la divergenza si vede. Storia: no |
| **2. Riserve ed esposizione** | `get_exposure`: per tavolo `current_exposure`, `loss_amount`, `status`, `in_recovery`; `total_exposure`; `list_positions`: `exposure`, `liability`; `exchange_funds.committed` | `reservation_id` (`table_manager.py:163`); `pending_exposure` (`:472`); importo riservato per ordine (`order_saga.stake`) | esposizione persistita: oggi è solo in memoria | `FUNDS_RESERVED`/`FUNDS_RELEASED` con `table_id`, `order_id` alias e importo; `EXPOSURE_UPDATE` | **D-3 in parte.** Il contratto MCP trasporta questi importi come float (`Money`), quindi un valore tipo `0.9987999999999999` uscirebbe com'è. È anche un limite del contratto MCP (vedi G6). S2: verificabile come stato |
| **3. Picco e drawdown** | `get_account`: `equity_peak`, `drawdown_pct`; `get_status.protections`: `drawdown_pct_hard_stop`, `drawdown_abs_hard_stop`; `get_config`: `max_drawdown_abs`, `auto_reset_drawdown_pct`, `defense_drawdown_pct`, `lockdown_drawdown_pct`, `max_drawdown_hard_stop_pct` | picco di cassa `_cash_equity_peak` (`runtime_controller.py:6433`) e `_cash_drawdown_pct` (`:6780`): calcolati, non esposti; il picco non è persistito (si ricostruisce dalla prima lettura dopo un riavvio) | **evento di auto-reset del picco** (`_maybe_auto_reset`, `:6746`): nessun tipo di evento adatto nel vocabolario; drawdown per tavolo: il motore non lo calcola | evento di ribasamento del picco (tipo da creare, decide B) con picco prima e dopo, drawdown al reset e soglia; `BANKROLL_READ` con il picco di cassa | **D-1 solo in parte.** Si vedono `equity_peak` (che segue il disponibile) e la config `auto_reset_drawdown_pct 15`. Non si vedono il reset né la perdita cancellata: manca la storia. Serve BB-3 e un nuovo tipo di evento |
| **4. Rifiuti per limiti** | `get_status.stop`: `risk_stop_reason`, `daily_loss_pending_stop`, `emergency_reason`, `kill_switch_active`; `readiness.blockers`; protezioni | motivi per segnale: `money_management` (`supera_max_single_bet`, `supera_max_total_exposure`, …), `risk_gate` (`RISK_*`), `_reject_signal` (`nessun_tavolo_disponibile`, `max_drawdown_abs_active`, `drawdown_hard_stop_active`, `duplicato_bloccato`, …). Finiscono solo nel logger e nel bus | — | `SIGNAL_REJECTED`/`RISK_GATE_DENY` con `reason_code`, `table_id`, e lo stake richiesto e calcolato. I tipi esistono già | **B-2 come stato:** tavoli `RECOVERY` con `loss_amount` e `allow_recovery=false` in `get_exposure`. **Come storia, no:** gli 11 rifiuti `nessun_tavolo_disponibile` non si vedono |
| **5. SL/TP e trailing** | `get_exposure.tables[].sl_tp`: `state`, `stop_loss`, `take_profit`, `trailing_stop_pct`, `trailing.state` (`NOT_IN_CORE`, …) | soglie in `table.meta` (memoria); invio della chiusura sul bus (`REQ_EXECUTE_CASHOUT`) | trailing nel motore (manca la logica); latch del trigger (il motore può ripubblicare a ogni tick) | `SL_TRIGGERED`, `TP_TRIGGERED`, `SL_TP_CLOSE_*` con `table_id` e P&L liquidabile | **S04/S05 sì, come stato.** I tavoli Roserpina appaiono con `stop_loss`/`take_profit` null e `NOT_ARMED`, e il trailing con `NOT_IN_CORE`. È lo stato vero, non nascosto. Lo scatto di un trigger: no |
| **6. Ordini AMBIGUOUS** | `list_orders`: `status`, `ambiguity_reason`, `reconciliation` (`in_reconciliation`, `finalized`), `broker_view`, `stake` e `size_matched`; `get_reconciliation_status.ambiguities_pending` | `audit_events` (FINAL_AMBIGUOUS, `trading_engine.py:1186`) nel DB, non nella scatola nera; mappe `_uncertain_*` (`runtime_controller.py:5037`) solo in memoria | — | `ORDER_PLACE_RESPONSE` con `outcome=UNKNOWN` e `reason_code=AMBIGUOUS` (la vista MCP lo mostra già così, verificato sulla classe reale); `RECONCILIATION_DIFF` | **B-1 come stato:** riga INFLIGHT, uncertain e in riconciliazione, con `broker_view` se il ponte la valorizza. Che l'exchange mostri l'ordine in EXECUTION_COMPLETE si vede solo se il ponte legge il broker. Storia: no |
| **7. Riconciliazione** | `get_reconciliation_status`: `startup` (`state`, `reason`, `recovery_failure`), `ghosts`, `recovery_state`, `settlement`; `get_status.readiness` | `outbox` ed eventi del bus (`RECONCILIATION_BATCH_DONE`, `GHOST_ORDERS`, …) | — | `RECONCILIATION_RUN`/`DIFF`/`RESOLVED` (tipi esistenti) | **B-1 in parte:** si vede `startup.state=REQUIRED` o un'ambiguità pendente che non si chiude. L'«uncertain» assegnato a ogni riavvio: no |
| **8. Prezzi stale** | `get_market_book.book_age_s` (MCP-01n, se il core lo fornisce); `exchange_funds.age_s` | età dei fondi (`LIVE_FUNDS_MAX_AGE_S=30`); deriva del prezzo (`direct_best_price.py:39`) | **nessun controllo dell'età del book nel motore**; nessun campo con il prezzo o l'età del book al momento della decisione | `ORDER_PLACE_REQUEST` con il prezzo richiesto e il miglior prezzo e l'età del book alla decisione; `PRICE_SNAPSHOT` (tipo esistente) | **B-3 solo per deduzione:** si vede l'età del book corrente e l'ordine unmatched riservato, non l'età del book quando l'ordine è partito. Serve BB-3 con il campo nuovo |
| **9. Crash e recovery** | **Scatola nera (BB-1, verificato sulla classe reale #617):** `UNCLEAN_TERMINATION`, finestre non registrate (`BLACKBOX_GAP`, esito UNKNOWN), `CRASH_RECOVERY`, `UNCAUGHT_EXCEPTION`/`TASK_EXCEPTION`, `EMERGENCY_STOP`, sessioni `CRASH_DETECTED`. Stato: `get_status.stop`, `get_reconciliation_status` | ripristino finanziario: tavoli e riserve ricostruiti, `risk_stop_state`, `daily_loss_state`, `roserpina.recovery_tables_state` (settings) | picco e drawdown non persistiti: dopo un riavvio la base è persa | evento di riepilogo del ripristino finanziario (tavoli, riserve, stop, perdita giornaliera) | **S8/S9 (PASS di Grok) verificabili:** il crash si vede nella scatola nera, il risultato nello stato. Che ricostruzione sia avvenuta: no |
| **10. Correlazione fra ≥5 tavoli** | `get_exposure.tables` (fino a 256), con `table_id` su ordini, posizioni e tavoli; filtri della scatola nera per `table_id`, `correlation_id`, `order_id` alias, `strategy` (verificati sulla classe reale) | `orders.correlation_id`, `order_saga.table_id`, `risk_position_history.table_id` | equity e drawdown per tavolo (il motore li calcola solo globali); serie storica per tavolo | eventi finanziari con `table_id` e `correlation_id` valorizzati (la vista e i filtri ci sono già, mancano gli eventi) | **Come stato sì:** 5 tavoli e il totale nella stessa lettura `PER_SECTION_LOCKED`. Come storia correlata: no, finché non arriva BB-3 |

## Lacune da consegnare a Claude B (proposte, schema NON modificato)

| # | Lacuna | Chi decide | Classe |
|---|---|---|---|
| G1 | Emissione nella scatola nera degli eventi finanziari già nel vocabolario: `BANKROLL_READ`, `STAKE_COMPUTED`, `SIGNAL_REJECTED`/`RISK_GATE_DENY` (con `reason_code`), `FUNDS_RESERVED`/`RELEASED`, `EXPOSURE_UPDATE`, `SL_/TP_TRIGGERED`, `SL_TP_CLOSE_*`, `RECONCILIATION_RUN`/`DIFF`/`RESOLVED`, `PRICE_SNAPSHOT`; sempre con `table_id`, l'alias di `order_id` e `correlation_id` | B (BB-3), oracolo D | BB-3 |
| G2 | Nuovo tipo di evento per il ribasamento del picco (auto-reset), con picco prima e dopo e perdita assorbita. Senza, D-1 non è ricostruibile | B, con approvazione owner sul vocabolario | ASSENTE → BB-3 |
| G3 | Prezzo ed età del book al momento della decisione in `ORDER_PLACE_REQUEST`. Senza, B-3 non è dimostrabile | B | ASSENTE → BB-3 |
| G4 | Picco di cassa e drawdown di cassa (`_cash_equity_peak`, `_cash_drawdown_pct`) esposti allo stato. Lato MCP serve un'estensione del contratto, da autorizzare | owner (estensione MCP), B (ponte) | NON REGISTRATO |
| G5 | Picco non persistito: la base del drawdown si perde al riavvio | B e D (correzione finanziaria, PR separata) | ASSENTE |
| G6 | Gli importi del contratto MCP per account ed esposizione sono float (`Money`); le posizioni sono `DecimalStr` | owner (versione del contratto MCP) | limite del contratto MCP |
| G7 | Equity e drawdown per tavolo: il motore non li calcola. Decidere se servono a Roserpina | owner e D | ASSENTE |

Nessuna di queste lacune dà all'MCP capacità monetarie: sono solo letture di valori che il motore calcola, o dovrebbe
registrare.

## Integrazione (mandato invariato)

Quando BB-1 sarà su main:
1. `check_reader` sulla classe reale e gli scenari dei contract test (harness v4, sha256 `8cbe584d…`);
2. le lacune G1–G3 diventano verificabili solo dopo BB-3.

Nessun PASS end-to-end prima dell'integrazione reale. Codice MCP congelato (`869d2c0`, patch `75e7280`). LIVE OFF,
nessun ordine reale.
