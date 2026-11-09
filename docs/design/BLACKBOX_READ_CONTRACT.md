# Scatola nera — contratto di lettura MCP / Control API (PF-BLACKBOX-01, lato Claude C)

Stato: **lato MCP e Control API implementato offline** (contratto 1.13.0, branch
`ccr-edf04c7d-e7vtj1-mcp01o-blackbox-read`); vista nel core **in attesa dell'interfaccia di Claude B** (§7). B possiede l'architettura e la scrittura nel motore; C possiede
la lettura sicura. Questo documento fissa ciò che il lettore si aspetta, così le due parti possono procedere in
parallelo senza una seconda struttura di registrazione. Nessun codice del motore è qui.

Autorizzazione: direttiva owner PF-BLACKBOX-01 del 08/11/2026, punto 4. Le route `/v1/blackbox/*` e gli strumenti
MCP qui sotto sono di **sola lettura** e sono ratificati da quella direttiva; nessun'altra route nuova.

## 1. Il record (vista di lettura)

Il lettore non inventa nulla: un campo che il motore non ha registrato vale `null` e compare in `not_recorded`
dell'evento; un `null` fuori elenco vuol dire «non applicabile» (es. nessuna causa). Un valore mancante non diventa
mai zero o stringa vuota. (Nel contratto `unavailable` ha già un significato fisso — null se e solo se elencato —
che il validatore del server applica a ogni oggetto: per questo l'evento usa `not_recorded` e lo stato
`not_reported`.)

| Campo | Tipo | Regola |
|---|---|---|
| `seq` | intero ≥ 1 | progressivo persistente globale, mai riusato; un buco è una lacuna dichiarata (§4) |
| `event_id` | stringa `^[0-9a-f]{32}$` | univoco |
| `ts_utc` | stringa `YYYY-MM-DDTHH:MM:SS.mmmZ` | UTC al millisecondo; l'ora locale la calcola chi visualizza |
| `session_id`, `process_id` | stringa / intero | sessione di avvio e PID |
| `component` | stringa `^[a-z][a-z0-9_.]{0,63}$` | modulo che registra |
| `origin` | `USER` \| `SYSTEM` \| `MCP` \| `CONTROL_API` \| `STRATEGY` \| `EXCHANGE` | |
| `category` | stringa `^[A-Z][A-Z0-9_]{0,31}$` | es. SESSION, CONFIG, UI, ORDER, RISK, MONEY, DUTCHING, MARKET, TABLE, RECOVERY |
| `event_type` | stringa `^[A-Z][A-Z0-9_]{0,63}$` | vocabolario chiuso del motore |
| `severity` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL` | |
| `phase` | `ATTEMPT` \| `RESULT` \| `OBSERVATION` | separa ciò che Pickfair **tenta** da ciò che **risulta**: una richiesta inviata non è mai un'operazione confermata |
| `outcome` | `VERIFIED` \| `PENDING` \| `UNKNOWN` \| `REJECTED` \| `FAILED` \| `NOT_APPLICABLE` | AMBIGUOUS dell'exchange = `UNKNOWN`, mai `FAILED` |
| `state_before`, `state_after` | stringa \| null | |
| `values_before`, `values_after` | oggetto piatto \| null | solo scalari già redatti dal motore; il lettore li ri-redige (§5) |
| `reason`, `reason_code` | stringa \| null | `reason_code` `^[A-Z][A-Z0-9_]{0,63}$` |
| `correlation_id`, `causation_id` | stringa \| null | `causation_id` = `event_id` dell'evento che ha causato questo |
| `refs` | oggetto | `table_id`, `market_id`, `order_id` (id locale del ledger), `bet_id`, `strategy`; mai `customer_ref` né segreti |
| `not_recorded` | lista di nomi di campo | campi non registrati dal motore |

## 2. Route Control API (GET, sola lettura)

| Route | Contenuto |
|---|---|
| `GET /v1/blackbox/status` | stato del registro: disponibile o no, primo e ultimo `seq`, lacune (§4), record corrotti, sessioni, retention, errori di scrittura, ultimo fsync |
| `GET /v1/blackbox/sessions` | sessioni: id, PID, inizio, fine (o `null` se terminata senza arresto registrato = crash), intervallo di `seq` |
| `GET /v1/blackbox/events` | eventi ordinati per `seq`, con filtri (§3) e paginazione per cursore |
| `GET /v1/blackbox/events/{event_id}` | un evento più la catena causale verso l'alto (`causation_id`, al più 32 passi) |

Il «ciclo di un ordine», la «cronologia di un tavolo» e la «cronologia di una sessione» sono filtri di
`/v1/blackbox/events`; la «motivazione di una decisione o di un rifiuto» è `/v1/blackbox/events/{event_id}` con la
catena causale.

## 3. Parametri (unica eccezione alla regola «nessuna query»)

Solo su `/v1/blackbox/events`, con una whitelist chiusa. Parametro sconosciuto o ripetuto, valore fuori pattern,
`since` > `until` o un intervallo oltre 31 giorni danno **400 senza chiamare il core**. Tutto il resto del server
resta «nessuna query».

| Parametro | Pattern |
|---|---|
| `since`, `until` | `YYYY-MM-DDTHH:MM:SS(.mmm)?Z` (UTC) |
| `after_seq` | intero ≥ 0 (cursore) |
| `limit` | 1–500, default 200 |
| `session_id`, `table_id`, `market_id`, `selection_id`, `bet_id`, `strategy`, `correlation_id` | pattern dei rispettivi campi |
| `order_id` | id del ledger (intero) oppure uuid canonico minuscolo con trattini |
| `causation_id` | 32 hex minuscoli |
| `category`, `origin`, `severity`, `event_type`, `outcome`, `phase` | vocabolari del §1 (uguaglianza esatta) |

Dal contratto 1.15.0 (MCP-01q) i filtri sono quelli del lettore di BB-1: `severity_min` e `q` non esistono più
(il lettore del motore non li ha) e sono rifiutati con `QUERY_PARAM`.

Risposta: `events`, `next_after_seq` (ultimo `seq` restituito; `0` se non ci sono altre pagine), `truncated`,
`gaps_in_range` (§4), `as_of_seq` (ultimo `seq` scritto al momento della lettura; `0` = registro vuoto),
`redacted`. Su tutte le route `/v1/blackbox/*`: `consistency = SINGLE_READ_SNAPSHOT` (lo stato:
`PER_FIELD_NON_ATOMIC`).

## 4. Lacune e integrità

Il lettore riporta, mai ripara:
- **lacuna**: `seq` mancanti in un intervallo → `gaps` come intervalli `[from, to]`;
- **record corrotto**: illeggibile o con checksum errato → contato, mai mostrato come se fosse valido;
- **finestra non registrata** (lacuna per tempo di BB-1, per esempio dopo un arresto non pulito):
  `unrecorded_windows` `{seq, from_ts, to_ts, reason_code}`. Cosa sia successo nella finestra è sconosciuto, mai
  «niente»;
- **sessione senza chiusura**: `ended_at` `null`, con `end_reason`:
  - `CRASH_DETECTED`: il motore ha rilevato l'arresto non pulito al riavvio. L'ora vera della fine non è nota;
    `last_event_at` ne è solo il limite inferiore;
  - `UNRECORDED`: nessuna rilevazione;
- **registro degradato** (BB-1: una scrittura non critica fallita): `degraded = true`,
  `dropped_non_critical`, `available = false`;
- **registro non disponibile**: `status.available = false` con `last_write_error_code` o `not_reported`; eventi
  `null` con `unavailable: ["events", "as_of_seq"]`.

Un buco dovuto alla retention è dichiarato come tale (`retained_from_seq`), non come perdita.

## 5. Segreti e dati sensibili

Il motore registra già redatto. Il lettore applica comunque una seconda redazione, per difesa in profondità: nomi
di campo sensibili (token, password, secret, key, credential, auth, session, cookie, `customer_ref`) → valore
sostituito da `"[REDACTED]"` e conteggiato in `redacted`. Nessun valore sensibile può uscire dalla Control API,
nemmeno se il motore ne avesse registrato uno per errore.

## 6. Ogni richiesta è registrata, senza ricorsione

- Il server Control API invoca un **hook** del ponte (`request_hook`, obbligatorio: senza, il server non parte)
  per ogni richiesta HTTP, mai per evento restituito: un record `ATTEMPT` prima della lettura e un record `RESULT`
  dopo l'invio, con `route` (modello, mai il percorso grezzo), `params` (solo valori già validati), `status`,
  `code`, `request_id` (l'`X-Request-Id` dell'MCP), `duration_ms`, `returned` (quanti eventi, sessioni
  o anelli della catena sono stati letti: il «conteggio» del `READ_REQUEST` di B, mai il contenuto) e
  `coalesced_before`. Il cliente è uno solo per costruzione (token unico, solo loopback): il limite di ritmo è
  quindi per server. Una richiesta rifiutata
  (401, 400, 404, 405) produce il solo `RESULT`. Il ponte scrive il record nella scatola nera con
  `origin = CONTROL_API`.
- Gli strumenti MCP mandano `X-Request-Id` (`^[A-Za-z0-9-]{8,64}$`), così il comando MCP e la sua registrazione
  in Pickfair si collegano.
- **Nessuna ricorsione**: leggere la scatola nera produce un solo record (la richiesta), mai un record per ciascun
  evento letto.
- **Nessun sovraccarico**: oltre 20 record/s (raffica 40) le registrazioni non chiamano l'hook e si contano;
  il conteggio esce in `coalesced_before` del record successivo. Se quel record fallisce, i conteggi portati
  diventano `requests_unrecorded`. Nessuna richiesta sparisce senza contarla (limite dichiarato: un conteggio
  ancora in memoria si perde se il processo muore prima del record successivo).
- **Registra o rifiuta.** Se l'hook rifiuta (registro non disponibile), la richiesta riceve 503
  `BLACKBOX_UNAVAILABLE`. Fa eccezione `/v1/blackbox/status`: serve proprio a vedere il guasto. Lì il mancato
  record è contato in memoria e riportato.

## 7. Cosa serve dal motore (richiesta a Claude B)

Un'interfaccia di lettura pura, nel processo, senza scrittura:

```
blackbox.status() -> dict            # §2 status
blackbox.sessions() -> list[dict]
blackbox.query(filters, after_seq, limit, *, external=True)
    -> {records, next_after_seq, gaps_in_range, as_of_seq}
blackbox.get(event_id, chain_depth, *, external=True) -> evento con la catena (forma da fissare)
blackbox.request_hook(record) -> bool   # hook del §6; qualunque valore diverso da True = non registrato
```

Forma normativa: quella di BB-1 (`core.blackbox_query.BlackBoxReader`, decisione C/B del 09/11/2026); il
dettaglio e ciò che resta da verificare sono in `BLACKBOX_BB1_COMPATIBILITY.md`. I record restituiti sono quelli
del §1, con i nomi del motore mappati dal ponte. Le scelte di storage, sequenza
multi-processo, fsync, rotazione e retention restano di B.

## 8. Implementazione lato MCP / Control API (MCP-01o)

- `pickfair_control_api/blackbox_query.py`: whitelist chiusa (19 parametri dal contratto 1.15.0, prima 17) con codici fissi
  `QUERY_PARAM`, `QUERY_PARAM_REPEATED`, `QUERY_VALUE`, `QUERY_ENCODING`, `QUERY_TOO_LONG`, `QUERY_RANGE`.
- `pickfair_control_api/blackbox_redact.py`: seconda redazione su lista, catena ed evento; `redacted` aggiornato.
- `pickfair_control_api/server.py`: route, hook obbligatorio, «registra o rifiuta», aggregazione,
  `requests_unrecorded` iniettato nello stato; `schema_check` supporta `patternProperties`/`maxProperties`
  (chiave fuori pattern = violazione).
- MCP: `get_blackbox_status`, `list_blackbox_sessions`, `list_blackbox_events`, `get_blackbox_event` (scope
  READ, `readOnlyHint`); l'adapter HTTP manda `X-Request-Id: mcp-<24 hex>` e tratta il 503 come upstream non
  disponibile, mai come dato; un core che ignora il cursore è una risposta non valida.
- Ponte del core: i provider `blackbox_status`, `blackbox_sessions`, `blackbox_events`, `blackbox_event` e
  `request_hook` sopra l'interfaccia del §7, **dopo** che B la pubblica. Fino ad allora la suite crossrepo con il
  core reale è BLOCKED (il ponte fissa la 1.12.0).

## 9. Da decidere con B

- La forma dei campi del §1 nel vocabolario reale del motore (`event_journal`, `session_recorder`, `audit_events`).
- `session_recorder` dichiara «non solleva MAI» (best-effort). La direttiva chiede fail-closed prima delle
  operazioni finanziarie critiche quando il registro non è disponibile: la scelta d'architettura è di B.
- La soglia di aggregazione del §6.
