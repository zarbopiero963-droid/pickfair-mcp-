# Compatibilità del contratto MCP con le correzioni di Claude D — 05/11/2026

Da: Claude C · Per: Claude D e Claude B · mandato owner del 05/11/2026, punto 3.
Base: `main` `ada40765`; viste del ponte MCP-01d … MCP-01k. Nessuna modifica fatta sui branch di Claude D:
ogni prova gira su una fusione **locale** (mai spinta) fra il ponte e il branch di D.

## Esito per branch

| Branch di D (head) | Esito | Prova riproducibile |
|---|---|---|
| P0 AMBIGUOUS `claude/pickfair-core-audit-slu9su` (`47e2aaac`) | **Incompatibilità lato MCP, corretta in MCP-01k.** Stati invariati, betId compatibile. La riga AMBIGUOUS conserva la risposta senza esito: con `status_assente_report_success_con_betid` la vista ordini mostrava `size_matched = "5"` su un ordine AMBIGUOUS | sonda sulla catena reale di D (`BetfairClient` → `TradingEngine` → DB su file → `orders_view`): RED `assert ('5', None, None) == (None, None, None)` col ponte 01j; GREEN 4/4 col ponte 01k. Test nel ponte: `tests/control_api/test_compat_views.py`; E2E `test_e2e_p0_ambiguous_row_without_unconfirmed_amounts` |
| betId (P0 e F-04) | **Compatibile** per le forme prodotte dal codice reale. `_order_bet_id` (usato da F-04 in `find_orders_by_customer_ref`, `database.py:2188` del branch) e `_open_order_candidates` coincidono anche sulla forma P0 (`result.instructionReports[0].betId`) | divergenza solo su forme sintetiche (`{"result":{"betId":X}}`, `{"raw":{"betId":X}}`, betId top-level diverso dal report): nessun produttore reale le genera (sonda del 04/11, 8/8 concordi). Rischio latente, nessun BLOCKER |
| F-02 `keep/f02-sl-tp-path-20261103` (`80b00909`) | **Compatibile** con `sl_tp` di MCP-01h (stesse chiavi del `meta`). Limite noto e già dichiarato da D: `sl_tp_triggered` vive solo nel `meta` in memoria (`runtime_controller.py:7115` del branch); dopo un riavvio il `meta` è ricostruito dal payload (`:5192`, `:5410`) senza il segnale, quindi `get_exposure` torna a mostrare ARMED | lo stato reale della chiusura è nel record persistente di F-04: lo espone MCP-01i (in preparazione offline). Nessuna modifica chiesta a F-02 |
| F-03 (trailing) | nessun branch trovato; il core non ha logica di trailing | il contratto non riporta mai il trailing come attivo |
| F-04 `claude/d-f04-sl-tp-close` (`4c07f719`) | **Compatibile**; record `risk.sl_tp_close.<customer_ref>` letto da MCP-01i. **Lacuna di contratto:** nessun legame persistito fra la richiesta d'hedge e il tavolo/evento SL/TP (`build_cashout_request` non porta `table_id` né `sl_tp_event_id`; `_ledger_write_ahead` aggiunge solo `cashout_request_id`) | MCP-01i può contare gli hedge solo per **selezione**, dichiarandolo, mai attribuirli al tavolo. Richiesta a D (non bloccante): persistere `sl_tp_event_id` (o `table_id`) nella richiesta d'hedge e nella riga del ledger |
| F-16 `claude/d-f16-funds-freshness` (`9767232f`) | **Incompatibilità lato MCP, corretta in MCP-01k.** Il limite effettivo diventa `min(30, 120)`, la vista dichiarava 120 | sonda sul codice reale di F-16: RED `assert '120' is None` col ponte 01j; GREEN col ponte 01k (limite null, stato dalla regola del core). Richiesta a D (non bloccante): un accessore unico `funds_max_age_s()` così il ponte riporta il valore senza replicare la regola |
| F-23 `claude/d-f23-market-tradable` (`a13714f8`) | **Compatibile**: la protezione `market_tradability` è già dichiarata UNAVAILABLE (`CORE_PENDING_F23`) | quando F-23 arriva su `main`, il ponte la collega alla regola del core (nessuna logica duplicata) |
| Streaming, settlement | nessun branch di D tocca `settlement_effects`, `cycle_recovery_checkpoints`, `_unrecorded_settlements`, `_held_batch_ids`, i lock o le chiavi di stato dello stream letti dal ponte | — |

## Note

- Nessun difetto del motore finanziario trovato: nessun BLOCKER. Le due incompatibilità reali erano nel ponte
  MCP e sono corrette in MCP-01k con test RED → GREEN.
- Dettaglio minore: il motivo `fondi_non_verificabili:FUNDS_STALE` di F-16 diventa il codice
  `FONDI_NON_VERIFICABILI` (il dettaglio dopo «:» non esce mai come testo libero, per contratto).
