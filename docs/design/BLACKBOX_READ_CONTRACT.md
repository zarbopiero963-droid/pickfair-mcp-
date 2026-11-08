# Scatola nera — contratto di lettura MCP / Control API (PF-BLACKBOX-01, lato Claude C)

Stato: **BOZZA per l'allineamento con Claude B**. B possiede l'architettura e la scrittura nel motore; C possiede
la lettura sicura. Questo documento fissa ciò che il lettore si aspetta, così le due parti possono procedere in
parallelo senza una seconda struttura di registrazione. Nessun codice del motore è qui.

Autorizzazione: direttiva owner PF-BLACKBOX-01 del 08/11/2026, punto 4. Le route `/v1/blackbox/*` e gli strumenti
MCP qui sotto sono di **sola lettura** e sono ratificati da quella direttiva; nessun'altra route nuova.

## 1. Il record (vista di lettura)

Il lettore non inventa nulla: un campo che il motore non ha registrato vale `null` e compare in `unavailable`
dell'evento. Un valore mancante non diventa mai zero o stringa vuota.

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
| `unavailable` | lista di nomi di campo | campi non registrati dal motore |

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
| `session_id`, `table_id`, `market_id`, `order_id`, `bet_id`, `strategy`, `correlation_id` | pattern dei rispettivi campi |
| `category`, `origin`, `severity_min`, `event_type`, `outcome` | vocabolari del §1 |
| `q` | ricerca testuale su `event_type`, `reason_code`, `reason`: 1–64 caratteri `[A-Za-z0-9 _.:-]` |

Risposta: `events`, `next_after_seq` (`null` se finiti), `truncated`, `gaps_in_range` (§4), `as_of_seq`
(ultimo `seq` scritto al momento della lettura).

## 4. Lacune e integrità

Il lettore riporta, mai ripara:
- **lacuna**: `seq` mancanti in un intervallo → `gaps` come intervalli `[from, to]`;
- **record corrotto**: illeggibile o con checksum errato → contato, mai mostrato come se fosse valido;
- **sessione senza chiusura**: `ended_at` `null` + `end_reason` `UNRECORDED` (crash o arresto non registrato);
- **registro non disponibile**: `status.available = false`, eventi `null` con `unavailable: ["events"]`.

Un buco dovuto alla retention è dichiarato come tale (`retained_from_seq`), non come perdita.

## 5. Segreti e dati sensibili

Il motore registra già redatto. Il lettore applica comunque una seconda redazione, per difesa in profondità: nomi
di campo sensibili (token, password, secret, key, credential, auth, session, cookie, `customer_ref`) → valore
sostituito da `"[REDACTED]"` e conteggiato in `redacted`. Nessun valore sensibile può uscire dalla Control API,
nemmeno se il motore ne avesse registrato uno per errore.

## 6. Ogni richiesta è registrata, senza ricorsione

- Il server Control API invoca un **hook** del ponte una volta per richiesta HTTP, mai per evento restituito:
  route, parametri validati (senza valori sensibili), esito (`ACCEPTED` / `REJECTED` + `reason_code` /
  `SERVED` / `FAILED`), `X-Request-Id` dell'MCP, durata. Il ponte lo scrive nella scatola nera con
  `origin = CONTROL_API`.
- Gli strumenti MCP mandano `X-Request-Id` (`^[A-Za-z0-9-]{8,64}$`), così il comando MCP e la sua registrazione
  in Pickfair si collegano.
- **Nessuna ricorsione**: leggere la scatola nera produce un solo record (la richiesta), mai un record per ciascun
  evento letto.
- **Nessun sovraccarico**: oltre una soglia (es. 20 richieste/s) le registrazioni si aggregano in un record di
  conteggio. Nessuna richiesta sparisce senza contarla.
- **Registra o rifiuta.** Se l'hook rifiuta (registro non disponibile), la richiesta riceve 503
  `BLACKBOX_UNAVAILABLE`. Fa eccezione `/v1/blackbox/status`: serve proprio a vedere il guasto. Lì il mancato
  record è contato in memoria e riportato.

## 7. Cosa serve dal motore (richiesta a Claude B)

Un'interfaccia di lettura pura, nel processo, senza scrittura:

```
blackbox.status() -> dict            # §2 status
blackbox.sessions() -> list[dict]
blackbox.query(filters, after_seq, limit) -> (records, next_after_seq, gaps_in_range, as_of_seq)
blackbox.get(event_id, chain_depth) -> (record | None, chain)
blackbox.record_control_api_request(fields) -> bool   # hook del §6; False = non registrato
```

I record restituiti sono quelli del §1, con i nomi del motore mappati dal ponte. Le scelte di storage, sequenza
multi-processo, fsync, rotazione e retention restano di B.

## 8. Da decidere con B

- La forma dei campi del §1 nel vocabolario reale del motore (`event_journal`, `session_recorder`, `audit_events`).
- `session_recorder` dichiara «non solleva MAI» (best-effort). La direttiva chiede fail-closed prima delle
  operazioni finanziarie critiche quando il registro non è disponibile: la scelta d'architettura è di B.
- La soglia di aggregazione del §6.
