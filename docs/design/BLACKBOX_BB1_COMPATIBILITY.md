# Scatola nera — condizioni di compatibilità con BB-1 (MCP-01q, contratto 1.15.0)

Da: Claude C · Per: Claude B · mandato owner PF-CLAUDE-C-MCP-BLACKBOX-INTEGRATION-20261109.
Riferimenti: `docs/design/BLACKBOX_READ_CONTRACT.md` (vista), `pf_blackbox_01.md` §3 e §4-bis di Claude B
(motore), controllo statico di B su `core.blackbox_query.BlackBoxReader` (pfab-b-20261109-adapter-check-001),
decisione C/B pfab-c-20261109-bb1-normative-001.

**Regola di forma.** La forma del lettore è quella di BB-1, ed è normativa: si adatta l'adapter, non il motore.
La vista esterna resta quella del contratto MCP (1.15.0).

**Nessun PASS sul motore reale finché BB-1 non è integrata.** I contract test girano su un lettore finto nella
forma di BB-1 (`tests/contract/fake_engine_blackbox.py`). La compatibilità con la classe reale resta
**NOT_VERIFIED** finché non girano gli stessi scenari sulle fixture JSON reali di B (§10).

## 1. Come si verifica la classe reale

```python
from pickfair_control_api.blackbox_bridge import check_reader, make_providers, make_request_hook
assert check_reader(core.blackbox_query.BlackBoxReader(...)) == []   # firme e assenza di scritture
```

Poi si eseguono gli scenari di `tests/contract/test_blackbox_bb1_contract.py` con il lettore reale al posto di
quello finto. Il ponte del core usa `make_providers(reader)` e `make_request_hook(reader)` e nient'altro. Ogni
differenza è un'incompatibilità: va corretta nel repository di chi la causa, prima dell'integrazione.

`check_reader` sulla classe reale: **NOT_RUN**. B non esegue codice di un'altra sessione per sua policy; il
controllo di B è stato statico.

## 2. Interfaccia (firme verificate da `check_reader`)

| Metodo | Parametri | Ritorno | Stato |
|---|---|---|---|
| `status()` | — | dict | forma BB-1 `{ok, degraded, as_of_seq, …}` **non ancora mappata**: §5 |
| `sessions()` | — | lista di dict (§6) | da confrontare con la fixture |
| `query(filters, after_seq, limit, *, external)` | filtri del motore (§4), cursore, 1–500; sempre `external=True` | `{records, next_after_seq, gaps_in_range, as_of_seq}` | adattato |
| `get(event_id, chain_depth, *, external)` | 32 hex minuscoli senza trattini, profondità 32, `external=True` | dict con la catena dentro | **non ancora mappato**: oggi errore (§2-bis) |
| `request_hook(record)` | record dell'hook (§7) | `True` solo se scritto; qualunque altro valore = non registrato | adattato |

Il lettore **non** espone `record`, `delete`, `update`, `write`, `purge` o `truncate`: `check_reader` lo rifiuta.

### 2-bis. Fail-closed su ciò che non è ancora mappato

- `query` con `gaps_in_range` non vuoto (lacune per tempo `{seq, from_ts, to_ts, outcome, reason_code}`):
  errore, mai una pagina mostrata come completa. La vista (`unrecorded_windows`) arriva con le fixture.
- `get` che non restituisce una coppia `(record, chain)`: errore. Un dict di due chiavi si spacchetterebbe nelle
  sue chiavi senza errore.
- `status()` senza `available`, `last_seq` o `gaps`:
  - il registro risulta non disponibile;
  - il campo assente va in `not_reported`, `gaps` compreso (nuovo in 1.15.0);
  - una lista vuota non significa mai «nessuna lacuna» se il motore non l'ha riportata.

## 3. Record del motore → vista

| Motore | Vista | Regola |
|---|---|---|
| `seq` (int ≥ 1) | `seq` | obbligatorio; senza seq la risposta non è attribuibile (errore) |
| `event_id`, `causation_id`, `correlation_id` | uguali | 32 hex senza trattini (anche la forma con trattini è normalizzata) |
| `ts_utc` ISO-8601 UTC fino al ns (`Z` o `+00:00`) | `ts_utc` al ms | troncato, mai arrotondato; altro fuso = record non mappabile |
| `source` | `origin` | USER, SYSTEM, MCP, CONTROL_API, STRATEGY, EXCHANGE, TELEGRAM, CLI |
| `type`, `category`, `severity` | `event_type`, `category`, `severity` | maiuscoli; livelli TRACE…CRITICAL |
| `phase`, `outcome` | uguali | ATTEMPT ⇒ PENDING; AMBIGUOUS dell'exchange = UNKNOWN con `reason_code` AMBIGUOUS |
| `pid` | `process_id` | |
| `component` | `component` | ASCII stampabile, 1–64 caratteri (`thread:<nome>` di BB-1 compreso) |
| `state_*`, `reason_code`, `reason` | uguali | `reason` oltre 256 caratteri: non mostrata, contata in `omitted_values` |
| `values_before`, `values_after`, `data` (dict o JSON) | mappe piatte con nomi puntati | vedi nota sotto |
| `table_id`, `selection_id` (testo di cifre in BB-1, o int) | `refs`, come interi | testo non di cifre = record non mappabile |
| `order_id` | `refs.order_id` | id del ledger (int o testo di cifre → int) oppure uuid canonico con trattini (`str(uuid4())` col DB degradato) |
| `market_id`, `bet_id`, `strategy` | `refs` | |
| `order_ref` / `customer_ref` | — | **mai** nella vista; `external=True` li esclude già, la vista li ignora comunque; in `data` diventano `[REDACTED]` |
| `mono`, `session_seq`, `prev_hash`, `hash` | — | interni |
| campo **assente** dal record | `null` + `not_recorded` | campo presente e nullo = «non applicabile» |

Nota sulle mappe piatte (`values_before`, `values_after`, `data`):
- un float finito diventa la sua stringa decimale esatta;
- sono contati in `omitted_values`, e non mostrati: le liste, i testi oltre 256 caratteri, i nomi fuori
  `^[a-z][a-z0-9_.]{0,63}$`, le voci oltre la trentaduesima, NaN.

Un record con valori fuori regola **non è mai mostrato «aggiustato»**: diventa una lacuna `CORRUPT` per il suo
seq. Sono fuori regola:
- origine, livello, fase o esito fuori vocabolario;
- tipo o categoria fuori pattern;
- ora non UTC;
- id non valido.

## 4. Filtri passati a `query` (1.15.0)

Sono i 17 filtri del lettore di BB-1 e nessun altro. Il lettore di BB-1 rifiuta un filtro sconosciuto; anche
quello finto lo fa.

| Vista (Control API / MCP) | Motore | Forma passata |
|---|---|---|
| `since`, `until` | `from_ts`, `to_ts` | `YYYY-MM-DDTHH:MM:SS.mmmZ` |
| `origin`, `event_type` | `source`, `type` | testo |
| `table_id`, `selection_id` | uguali | **testo di cifre**: BB-1 confronta per uguale con il testo registrato, e un intero darebbe una pagina vuota senza errore |
| `order_id` | uguale | testo: cifre, oppure uuid canonico minuscolo con trattini |
| `session_id`, `market_id`, `bet_id`, `strategy`, `correlation_id`, `causation_id`, `category`, `severity`, `outcome`, `phase` | uguali | testo |

`severity` e `phase` sono uguaglianze esatte. `severity_min` e `q` non esistono in BB-1: dal 1.15.0 il server li
rifiuta con `QUERY_PARAM` e il tool MCP non li offre. I valori sono già validati dalla whitelist della Control
API.

## 5. `status()`

Chiavi lette dall'adapter:
- `available`: vale True solo se è letteralmente True;
- `first_seq`, `last_seq`, `retained_from_seq`;
- `gaps`: lista di `(from, to, kind)` o di dict, con kind LOST, CORRUPT o RETENTION;
- `corrupt_records`, `sessions`, `current_session_id`, `last_write_error_code`, `last_durable_write_at`,
  `retention_days`.

Una chiave **assente** diventa `not_reported`. La forma di BB-1 `{ok, degraded, as_of_seq, …}` oggi produce
«non disponibile», con `seq_range` e `gaps` non riportati: è prudente, ma non è la mappatura. La mappatura si
scrive sulla fixture (§10).

## 6. `sessions()`

Per sessione:
- `session_id`, `pid`, `started_at`;
- `ended_at` (`None` se la sessione non è chiusa);
- `end_reason`: RUNNING, CLEAN_STOP, CRASH_DETECTED o UNRECORDED;
- `first_seq`, `last_seq`.

Da confrontare con la fixture di B.

## 7. Hook `request_hook(record)`

Campi del record:
- `phase`: ATTEMPT prima della lettura, RESULT dopo l'invio; una richiesta rifiutata ha solo il RESULT;
- `route` (il modello della route) e `params` (i valori validati);
- `request_id`: `X-Request-Id` dell'MCP, nella forma `mcp-<24 hex>`;
- `status`, `code`, `duration_ms`;
- `returned`: elementi letti;
- `coalesced_before`: richieste contate e non scritte oltre 20 record/s (raffica 40).

Il `READ_REQUEST` di B si ricava dal RESULT.

Se l'hook restituisce un valore diverso da `True`, o solleva un'eccezione, la Control API risponde 503
`BLACKBOX_UNAVAILABLE`. Fanno eccezione `/v1/blackbox/status` e `/v1/meta` (l'handshake, senza dati): così lo
stato del guasto resta raggiungibile anche via MCP.

## 8. Differenze contratto simulato ↔ BB-1 trovate e corrette

| Differenza (fonte) | Correzione nel repository MCP | Prova |
|---|---|---|
| id del motore in 32 hex senza trattini (ACK di B) | `engine_id` passa 32 hex a `get` | RED 3 → GREEN (43eba46) |
| tempo filtrato con `from_ts`/`to_ts`; filtro sconosciuto = errore (ACK di B) | `since`/`until` tradotti | idem |
| hook `request_hook(record)` (controllo statico di B) | `make_request_hook`, `check_reader` | contract test, mutante R04 |
| `query` con `external` e risultato dict | adapter con `external=True`, lettura del dict | contract test, mutante R13 |
| `gaps_in_range` per tempo | errore finché non è mappato | test `time_gaps_…`, mutante R12 |
| `get` restituisce un dict | errore finché non è mappato | test `get_in_bb1_dict_shape…`, mutante R16 |
| `status` senza `available`/`gaps` | `not_reported` comprende `gaps` | test `bb1_status_shape…`, mutante R15 |
| `table_id`/`selection_id` come testo di cifre | vista: testo → int; filtro: int → testo | RED (0 righe invece di 3) → GREEN, mutante R11 |
| `order_id` uuid | vista e filtro: int oppure uuid canonico | test dei filtri, mutante R14 |
| `component` `thread:<nome>` | pattern ASCII stampabile 1–64 | test `thread_component…` |
| filtri: 17 di BB-1, senza `severity_min` e `q` | whitelist 1.15.0 (19 parametri con `after_seq` e `limit`) | test di query e di route |

## 9. Cosa NON fa il lettore

Non scrive, non cancella, non ripara lacune e non ricalcola importi. La decisione di stake di Roserpina (bankroll
verificato, percentuale MM, stake teorico e autorizzato, riserve, commissioni, valuta, motivo del rifiuto) è
mostrata come il motore l'ha registrata in `data`, con il suo `correlation_id`. Nessuna logica finanziaria
nell'MCP.

## 10. NOT_VERIFIED: fixture JSON reali richieste a B

Servono le fixture di:
- a) `status()`;
- b) `sessions()`;
- c) una pagina di `query` con `gaps_in_range` non vuoto;
- d) `get` di un evento con la sua catena;
- e) un record per ognuna delle forme di `order_id` (intero e uuid).

Fino ad allora restano da verificare:
- la mappatura di `status`, `sessions` e `get`;
- `unrecorded_windows` (le lacune per tempo);
- `check_reader` sulla classe reale;
- TRACE in `event_journal.LEVELS` di BB-1;
- la forma registrata di `order_id`, cioè se è intero o testo di cifre.
