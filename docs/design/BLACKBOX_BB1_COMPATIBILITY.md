# Scatola nera — compatibilità con BB-1 (MCP-01q, contratto 1.15.0)

Da: Claude C · Per: Claude B · mandato owner PF-CLAUDE-C-MCP-BLACKBOX-INTEGRATION-20261109.
Riferimenti: `docs/design/BLACKBOX_READ_CONTRACT.md` (vista), `pf_blackbox_01.md` §3 e §4-bis di Claude B
(motore), controllo statico di B su `core.blackbox_query.BlackBoxReader` (pfab-b-20261109-adapter-check-001),
decisione C/B pfab-c-20261109-bb1-normative-001.

**Regola di forma.** La forma del lettore è quella di BB-1, ed è normativa: si adatta l'adapter, non il motore.
La vista esterna resta quella del contratto MCP (1.15.0).

**Nessun PASS end-to-end sul motore reale finché BB-1 non è integrata.** Due livelli di prova:
- **fixture reali di B**: output di `BlackBoxReader` (BB-1 locale 9626f95, `external=True`, dati sintetici),
  salvati in `tests/contract/fixtures/bb1_reader_74be0f92.json`, sha256
  `74be0f92274b5dda252061148c82a0c54329be2d50e1d1ddd23e31691a36f6df` (20.484 byte, uguale a quello dichiarato da
  B). Il JSON è estratto parola per parola dal messaggio di B; il testo del messaggio ha una `}` in più prima di
  `"e_request_hook_return"`, la stessa nei due invii, e tolta quella riproduce l'hash. Esito: **VERIFIED sulle
  fixture**. Storia: c11e4108… (0df7a411) dava RED 7 su 907423e → GREEN 10 su df044fc; b275d7ea… (46e722b) ha
  aggiunto TRACE, ATTEMPT dell'hook e `returned`; questa aggiunge lo schema D1–D2;
- **lettore finto** (`tests/contract/fake_engine_blackbox.py`), nelle stesse forme, per gli scenari che la
  fixture non copre: filtri, paginazione, record non mappabili, hook rifiutato.

Restano **NOT_RUN** `check_reader` e gli scenari sulla classe reale integrata (§10).

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
| `status()` | — | `{ok, degraded, dropped_non_critical, as_of_seq, count, buffered, session_id, not_reported}` | mappato (§5), verificato sulla fixture |
| `sessions()` | — | lista di `{session_id, pid, started, last_ts, first_seq, last_seq, clean_shutdown}` | mappato (§6), verificato sulla fixture |
| `query(filters, after_seq, limit, *, external)` | filtri del motore (§4), cursore, 1–500; sempre `external=True` | `{records, next_after_seq, gaps_in_range, as_of_seq}` | mappato, verificato sulla fixture |
| `get(event_id, chain_depth, *, external)` | 32 hex minuscoli senza trattini, profondità 32, `external=True` | il record con `causation_chain`, oppure `None` | mappato, verificato sulla fixture |
| `request_hook(record)` | record dell'hook (§7) | `True` solo se scritto; qualunque altro valore = non registrato | verificato sulla fixture (`true`) |

Il lettore **non** espone `record`, `delete`, `update`, `write`, `purge` o `truncate`: `check_reader` lo rifiuta.

### 2-bis. Fail-closed su ogni forma diversa

- `gaps_in_range` assente, non lista, oltre 64 voci, o con una voce fuori forma: errore, mai una pagina mostrata
  come completa. Fuori forma vuol dire: esito diverso da UNKNOWN, estremi invertiti o non UTC, seq < 1,
  `reason_code` mancante.
- `get` che non restituisce un dict con `causation_chain` (lista), o `None`: errore. La vecchia coppia
  `(record, chain)` non è accettata.
- `sessions()` con `clean_shutdown` falso e `status()` senza `session_id`: errore. Senza la sessione corrente,
  un crash non si distingue dalla sessione in corso.
- `not_recorded` del record con un nome sconosciuto o con un valore non nullo: record non mappabile (lacuna
  CORRUPT), mai un valore nascosto.

## 3. Record del motore → vista

| Motore | Vista | Regola |
|---|---|---|
| `seq` (int ≥ 1) | `seq` | obbligatorio; senza seq la risposta non è attribuibile (errore) |
| `event_id`, `causation_id`, `correlation_id` | uguali | 32 hex senza trattini (anche la forma con trattini è normalizzata) |
| `ts_utc` ISO-8601 UTC fino al ns (`Z` o `+00:00`) | `ts_utc` al ms | troncato, mai arrotondato; altro fuso = record non mappabile |
| `source` | `origin` | USER, SYSTEM, MCP, CONTROL_API, STRATEGY, EXCHANGE, TELEGRAM, CLI |
| `type`, `category`, `severity` | `event_type`, `category`, `severity` | maiuscoli; livelli TRACE…CRITICAL |
| `not_recorded` (BB-1: i campi a null) | `not_recorded` | i campi della vista che il motore elenca, più quelli assenti dal record |
| `phase`, `outcome` | uguali | ATTEMPT ⇒ PENDING; AMBIGUOUS dell'exchange = UNKNOWN con `reason_code` AMBIGUOUS |
| `pid` | `process_id` | |
| `component` | `component` | ASCII stampabile, 1–64 caratteri (`thread:<nome>` di BB-1 compreso) |
| `state_*`, `reason` | uguali | `reason` oltre 256 caratteri: non mostrata, contata in `omitted_values` |
| `reason_code` | uguale | `^[A-Za-z][A-Za-z0-9_]{0,63}$`: anche il nome di un'eccezione (`KeyError`) |
| `values_before`, `values_after`, `data` (dict o JSON) | mappe piatte con nomi puntati | vedi nota sotto |
| `table_id`, `selection_id` (testo di cifre in BB-1, o int) | `refs`, come interi | testo non di cifre = record non mappabile |
| `order_id` | `refs.order_id` | solo l'alias opaco `ord_<32 hex>` (D1); un id interno (intero o uuid) rende il record non mappabile |
| `exchange_ts` | `exchange_ts` | ora dichiarata dall'exchange (D2), al ms come `ts_utc`; null = non registrata |
| `market_id`, `bet_id`, `strategy` | `refs` | |
| `order_ref` / `customer_ref` | — | **mai** nella vista; `external=True` li esclude già, la vista li ignora comunque; in `data` diventano `[REDACTED]` |
| `mono`, `session_seq`, `prev_hash`, `hash` | — | interni |
| campo **assente** dal record | `null` + `not_recorded` | in BB-1 ogni colonna esiste; il null va in `not_recorded` |

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
| `order_id` | uguale | alias `ord_<32 hex>`: l'id interno non è un filtro esterno |
| `session_id`, `market_id`, `bet_id`, `strategy`, `correlation_id`, `causation_id`, `category`, `severity`, `outcome`, `phase` | uguali | testo |

`severity` e `phase` sono uguaglianze esatte. `severity_min` e `q` non esistono in BB-1: dal 1.15.0 il server li
rifiuta con `QUERY_PARAM` e il tool MCP non li offre. I valori sono già validati dalla whitelist della Control
API.

## 5. `status()` → stato della vista

L'adapter legge anche `sessions()`.

| BB-1 | Vista | Regola |
|---|---|---|
| `ok`, `degraded` | `available`, `degraded` | `available` solo se `ok` è letteralmente True e `degraded` non è True |
| `dropped_non_critical` | uguale | |
| `as_of_seq` + il minimo `first_seq` delle sessioni | `last_seq`, `first_seq` | `as_of_seq` 0 = registro vuoto; senza `first_seq`: `seq_range` in `not_reported` |
| numero delle sessioni | `sessions` | |
| `session_id` | `current_session_id` | |
| `not_reported` con `last_error_detail` | `last_write_error_code` in `not_reported` | |
| `count`, `buffered` | — | non mostrati |
| chiavi che BB-1 non ha: `gaps`, `corrupt_records`, `last_durable_write_at`, `retention_days`, `last_write_error_code` | `not_reported` | `gaps` vuota per forma, ma dichiarata non riportata: mai «nessuna lacuna» |

## 6. `sessions()` → sessioni della vista

| BB-1 | Vista |
|---|---|
| `session_id`, `pid`, `first_seq`, `last_seq` | `session_id`, `process_id`, `first_seq`, `last_seq` |
| `started` | `started_at` (al ms) |
| `last_ts` | `last_event_at` (al ms) |
| `clean_shutdown` true | `end_reason` CLEAN_STOP, `ended_at` = `last_ts` |
| `clean_shutdown` false, sessione = `status().session_id` | RUNNING, `ended_at` null |
| `clean_shutdown` false, altra sessione | CRASH_DETECTED, `ended_at` null: l'ora vera non è nota, `last_event_at` è il limite inferiore |

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
| `gaps_in_range` per tempo (fixture) | `unrecorded_windows`, esito sempre sconosciuto | fixture, mutanti R12 e R19 |
| `get`: record con `causation_chain`, anello `{event_id, missing}`, `None` (fixture) | catena, `chain_broken_at`, NOT_FOUND | fixture, mutante R16 |
| `status` `{ok, degraded, …}` (fixture) | §5, `degraded` e `dropped_non_critical` nuovi | fixture, mutanti R15 e R20 |
| `sessions` con `clean_shutdown` (fixture) | §6, `last_event_at` nuovo; per un crash, nessuna ora di fine | fixture, mutanti R21 e R22 |
| `not_recorded` del motore (fixture) | usato; mai un valore nascosto | fixture, mutanti R17 e R18 |
| `reason_code` `KeyError` (fixture): prima diventava un record CORRUPT | pattern anche minuscolo | fixture, mutante R23 |
| `table_id`/`selection_id` come testo di cifre | vista: testo → int; filtro: int → testo | RED (0 righe invece di 3) → GREEN, mutante R11 |
| `order_id` alias opaco (D1) | vista e filtro solo `ord_<32 hex>` | fixture, test dei filtri, mutanti R14 e R24 |
| `exchange_ts` (D2) | nuovo campo dell'evento | fixture, mutante R25 |
| `component` `thread:<nome>` | pattern ASCII stampabile 1–64 | test `thread_component…` |
| filtri: 17 di BB-1, senza `severity_min` e `q` | whitelist 1.15.0 (19 parametri con `after_seq` e `limit`) | test di query e di route |

## 9. Cosa NON fa il lettore

Non scrive, non cancella, non ripara lacune e non ricalcola importi. La decisione di stake di Roserpina (bankroll
verificato, percentuale MM, stake teorico e autorizzato, riserve, commissioni, valuta, motivo del rifiuto) è
mostrata come il motore l'ha registrata in `data`, con il suo `correlation_id`. Nessuna logica finanziaria
nell'MCP.

## 10. Ancora da verificare sulla classe reale (NOT_RUN)

- `check_reader(BlackBoxReader(...)) == []` e gli scenari dei contract test sulla classe reale, una volta
  integrata BB-1 (#615, a merge dell'owner);
- se la fixture cambia, B rigenera file e sha256 e qui si aggiorna `FIXTURE_SHA256`.

## 11. Richieste a B dalle fixture: chiuse (pfab-b-20261109-bb1-fixtures-002, BB-1 46e722b)

- **`returned`**: aggiunto da B nel `data` di `CONTROL_API_REQUEST` (seq 15 della fixture: `returned: 13`).
- **ATTEMPT**: BB-1 lo registra con `phase=ATTEMPT`, `outcome=PENDING` (seq 14).
- **`request_id` dell'MCP** `mcp-<24 hex>`: resta invariato in `correlation_id` e in `data.request_id`; la
  normalizzazione di BB-1 compatta solo valori di 32 hex. Nessuna cifra inventata.
- **TRACE**: presente nella fixture (seq 13, `API_REQUEST`, categoria `BETFAIR`).
- Nota di B: la vista esterna di BB-1 toglie `order_ref`, `customer_ref`, `customerOrderRef` e varianti a ogni
  profondità di `data` e `values_*`. La vista MCP li ignora e redige comunque.

## 12. Schema D1–D3 (pfab-b-20261109-bb1-schema-d1d3-001, BB-1 9626f95)

Decisione owner PF-BB1-IDENTITY-TIMESTAMP-SESSION-20261109, data in sessione a Claude B. Il testo integrale è
registrato da B in https://github.com/zarbopiero963-droid/Pickfair-nogui/issues/586#issuecomment-6740764129: la fonte è l'owner tramite B, non un commento scritto dall'owner. C la adotta: la forma di
BB-1 è normativa e la vista risulta più prudente.
- **D1**: alias opaco dell'ordine. Il campo interno `order_alias` non esce mai.
- **D2**: `exchange_ts`, con lo stesso formato RFC 3339 UTC di `ts_utc`.
- **D3**: lock di runtime unico. Riguarda solo chi scrive: il ponte Control API/MCP legge e non apre sessioni.
