# Scatola nera — condizioni di compatibilità con BB-1 (MCP-01p, contratto 1.14.0)

Da: Claude C · Per: Claude B · mandato owner PF-CLAUDE-C-MCP-BLACKBOX-INTEGRATION-20261109.
Riferimenti: `docs/design/BLACKBOX_READ_CONTRACT.md` (vista), `pf_blackbox_01.md` §3 e §4-bis di Claude B
(motore). Nessun PASS sul motore reale finché BB-1 non è integrata: i contract test girano su un lettore finto
nella forma del motore (`tests/contract/fake_engine_blackbox.py`).

## 1. Come si verifica la classe reale

```python
from pickfair_control_api.blackbox_bridge import check_reader, make_providers, make_request_hook
assert check_reader(core.blackbox_query.<Reader>(...)) == []           # firme e assenza di scritture
```

Poi gli stessi scenari di `tests/contract/test_blackbox_bb1_contract.py` con il lettore reale al posto del
finto: il ponte del core usa `make_providers(reader)` e `make_request_hook(reader)` e nient'altro. Ogni differenza
è un'incompatibilità da correggere nel repository di chi la causa, prima dell'integrazione.

## 2. Interfaccia (firme verificate da `check_reader`)

| Metodo | Parametri (in quest'ordine) | Ritorno |
|---|---|---|
| `status()` | — | dict (§5) |
| `sessions()` | — | lista di dict (§6) |
| `query(filters, after_seq, limit)` | filtri con i nomi del motore (§4), cursore, limite 1–500 | `(records, next_after_seq, gaps_in_range, as_of_seq)` |
| `get(event_id, chain_depth)` | id nella forma del motore (uuid in 32 hex minuscoli, senza trattini), profondità 32 | `(record \| None, chain)` |
| `record_control_api_request(fields)` | record dell'hook (§7) | `True` solo se scritto; qualunque altro valore = non registrato |

Il lettore **non** espone `record`, `delete`, `update`, `write`, `purge`, `truncate`: `check_reader` lo rifiuta.

## 3. Record (pf_blackbox_01 §3) → vista

| Motore | Vista | Regola |
|---|---|---|
| `seq` (int ≥ 1) | `seq` | obbligatorio; senza seq la risposta non è attribuibile (errore) |
| `event_id`, `causation_id`, `correlation_id` (uuid in 32 hex senza trattini, ACK di B del 09/11) | uguali | anche la forma con trattini è accettata e normalizzata |
| `ts_utc` ISO-8601 UTC fino al ns (`Z` o `+00:00`) | `ts_utc` al ms | troncato, mai arrotondato; altro fuso = record non mappabile |
| `source` | `origin` | USER, SYSTEM, MCP, CONTROL_API, STRATEGY, EXCHANGE, TELEGRAM, CLI |
| `type`, `category`, `severity` | `event_type`, `category`, `severity` | maiuscoli; livelli TRACE…CRITICAL (event_journal.LEVELS) |
| `phase`, `outcome` | uguali | ATTEMPT ⇒ PENDING; AMBIGUOUS dell'exchange = UNKNOWN |
| `pid` | `process_id` | |
| `component`, `state_*`, `reason_code`, `reason`, `correlation_id`, `causation_id` | uguali | `reason` oltre 256 caratteri: non mostrata, contata in `omitted_values` |
| `values_before`, `values_after`, `data` (dict o JSON) | mappe piatte con nomi puntati | float finito → stringa decimale esatta; liste, testi oltre 256, nomi fuori `^[a-z][a-z0-9_.]{0,63}$`, oltre 32 voci, NaN → contati in `omitted_values` |
| `table_id`, `market_id`, `selection_id`, `bet_id`, `strategy` | `refs` | |
| `order_id` (id locale del ledger) | `refs.order_id` | **richiesta a B**: includerlo nel record (indicizzato); senza, la cronologia di un ordine si filtra per `bet_id` |
| `order_ref` / `customer_ref` | — | **mai** nella vista; in `data` il valore è `[REDACTED]` |
| `mono`, `session_seq`, `prev_hash`, `hash` | — | interni |
| campo **assente** dal record | `null` + `not_recorded` | campo presente e nullo = «non applicabile» |

Un record con origine, livello, fase o esito fuori vocabolario, tipo o categoria fuori pattern, ora non UTC o
id non valido **non è mai mostrato «aggiustato»**: diventa una lacuna `CORRUPT` per il suo seq.

## 4. Filtri passati a `query`

Nomi della vista tradotti nei nomi del motore: `origin` → `source`, `event_type` → `type`, `since` → `from_ts`,
`until` → `to_ts` (stringhe ISO UTC `YYYY-MM-DDTHH:MM:SS.mmmZ`); gli altri invariati (`session_id`, `table_id`,
`market_id`, `order_id`, `bet_id`, `strategy`, `correlation_id`, `category`, `severity_min`, `outcome`, `q`).
Valori già validati dalla whitelist della Control API. Il lettore di BB-1 rifiuta un filtro sconosciuto: **da
confermare da B** che accetti esattamente questi 15 nomi (il lettore finto li accetta e rifiuta gli altri).

## 5. `status()`

Chiavi lette: `available` (True solo se letteralmente True), `first_seq`, `last_seq`, `retained_from_seq`,
`gaps` (lista di `(from, to, kind)` o dict, kind LOST/CORRUPT/RETENTION), `corrupt_records`, `sessions`,
`current_session_id`, `last_write_error_code`, `last_durable_write_at`, `retention_days`. Una chiave
**assente** diventa `not_reported`; con `available` falso serve `last_write_error_code`.

## 6. `sessions()`

Per sessione: `session_id`, `pid`, `started_at`, `ended_at` (`None` se non chiusa), `end_reason` in RUNNING,
CLEAN_STOP, CRASH_DETECTED, UNRECORDED, `first_seq`, `last_seq`.

## 7. Hook `record_control_api_request(fields)`

Campi: `phase` (ATTEMPT prima della lettura, RESULT dopo l'invio; solo RESULT per una richiesta rifiutata),
`route` (modello), `params` (valori validati), `request_id` (`X-Request-Id` dell'MCP, `mcp-<24 hex>`), `status`,
`code`, `duration_ms`, `returned` (elementi letti), `coalesced_before` (richieste contate e non scritte oltre
20 record/s, raffica 40). Il `READ_REQUEST` di B si ricava dal RESULT. Con `False` o un'eccezione la Control API
risponde 503 `BLACKBOX_UNAVAILABLE`, tranne `/v1/blackbox/status` e `/v1/meta` (handshake senza dati): così lo
stato del guasto resta raggiungibile anche via MCP.

## 8. Differenze contratto simulato ↔ BB-1 trovate e corrette (ACK di B, 09/11/2026)

| Differenza | Correzione (MCP-01p, repository MCP) | Prova |
|---|---|---|
| id del motore in 32 hex senza trattini (non uuid con trattini) | `engine_id` passa 32 hex a `get`; il lettore finto usa la forma reale | RED 3 → GREEN sui contract test |
| tempo filtrato con `from_ts`/`to_ts`; filtro sconosciuto = errore | `since`/`until` tradotti; il lettore finto rifiuta i filtri sconosciuti | idem |

Ancora da verificare sulla classe reale: `check_reader` (NOT_RUN finché B non ha l'adapter), elenco esatto dei
filtri accettati, TRACE in `event_journal.LEVELS` di BB-1, `order_id` nel record (accolto da B per BB-1).

## 9. Cosa NON fa il lettore

Non scrive, non cancella, non ripara lacune, non ricalcola importi: la decisione di stake di Roserpina (bankroll
verificato, percentuale MM, stake teorico e autorizzato, riserve, commissioni, valuta, motivo del rifiuto) è
mostrata come il motore l'ha registrata in `data`, con il suo `correlation_id`.
