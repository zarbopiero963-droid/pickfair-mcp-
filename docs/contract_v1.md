# Contratto Control API v1 — vista dell'adapter MCP

Stato: **PROVISIONAL**. La Control API di Pickfair non esiste ancora (PF-API-0/1/commands).
Questo documento descrive ciò che l'adapter si aspetta e come si comporta; non
crea route né semantiche di prodotto. Le 25 route sono quelle approvate in pickfair-mcp- #1.

## Route approvate (copia verificata dai test)

| Tipo | Metodo | Route | Tool MCP | Stato in MCP-01a |
|---|---|---|---|---|
| Read | GET | `/v1/meta` | `get_meta` | Esposto, adapter simulato |
| Read | GET | `/v1/status` | `get_status` | Non esposto (MCP-02) |
| Read | GET | `/v1/account` | `get_account` | Non esposto (MCP-02) |
| Read | GET | `/v1/exposure` | `get_exposure` | Non esposto (MCP-02) |
| Read | GET | `/v1/config` | `get_config` | Non esposto (MCP-02/03) |
| Read | GET | `/v1/events` | `list_events` | Non esposto (MCP-02) |
| Read | GET | `/v1/markets` | `list_markets` | Non esposto (MCP-02) |
| Read | GET | `/v1/markets/{id}/book` | `get_market_book` | Non esposto (MCP-02) |
| Read | GET | `/v1/orders` | `list_orders` | Non esposto (MCP-02) |
| Read | GET | `/v1/positions` | `list_positions` | Non esposto (MCP-02) |
| Read | GET | `/v1/operations/{id}` | `get_operation` | Non esposto (MCP-02) |
| Read | GET | `/v1/operations?status=pending` | `list_pending_operations` | Non esposto (MCP-02) |
| Read | GET | `/v1/reconciliation/status` | `get_reconciliation_status` | Non esposto (MCP-02) |
| Read | GET | `/v1/audit/{correlation_id}` | `get_audit_trail` | Non esposto (MCP-02) |
| Command | POST | `/v1/preview` | `preview_order` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/orders` | `place_order` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/dutching` | `place_dutching` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/orders/{id}/cancel` | `cancel_order` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/orders/{id}/replace` | `replace_order` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/cashout` | `cashout` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/stop` | `stop` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/resume` | `resume` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/reconcile` | `reconcile` | Bloccato (BLOCKED_CORE) |
| Command | PATCH | `/v1/config` | `patch_config` | Bloccato (BLOCKED_CORE) |
| Command | POST | `/v1/mode` | `set_mode` | Bloccato (BLOCKED_CORE / owner) |

Il registro dei tool rifiuta la registrazione di qualunque comando finché
`MCP_MUTATION_EXPOSURE = BLOCKED_UNTIL_CORE_AUTHORITY_READY` (costante di codice
`pickfair_mcp.policy.exposure.MUTATION_EXPOSURE`).

## GET /v1/meta — forma attesa (PROVISIONAL)

La tabella approvata dice soltanto «Version/capabilities/git SHA/schema hash».
L'adapter si aspetta un oggetto JSON con esattamente questi campi:

| Campo | Tipo | Vincolo |
|---|---|---|
| `contract_version` | stringa | semver `MAJOR.MINOR.PATCH` |
| `capabilities` | array di stringhe | 1–64 elementi unici, forma `METODO /v1/...` |
| `git_sha` | stringa | 40 caratteri esadecimali minuscoli |
| `schema_hash` | stringa | 64 caratteri esadecimali minuscoli |

Parsing fail-closed: solo UTF-8, massimo 64 KiB, JSON standard senza NaN/Infinity,
nessuna chiave duplicata, nessun campo extra, nessuna coercizione di tipo.

## Handshake e compatibilità

- Capability = chiave di route approvata (`"GET /v1/meta"` …). Una capability fuori
  dalle 25 approvate rende il contratto incompatibile; il motivo restituito è il codice
  `CAPABILITY_NOT_APPROVED`, senza mai riportare il testo inviato dall'upstream.
- Compatibile solo se la coppia `(contract_version, schema_hash)` è nella compat matrix.
  Oggi: `1.0.0` con lo schema hash calcolato dal descrittore canonico (`pickfair-mcp contract-info`).
- L'handshake si ripete a ogni nuovo epoch di connessione; su contratto incompatibile i
  tool restano bloccati finché non avviene una riconnessione, anche se `get_meta` ripete
  l'handshake nello stesso epoch. Timeout e indisponibilità
  sono riprovabili solo per le letture.

Alternative documentate, non adottate:
- **A — tolleranza semver**: accettare minor superiori con lo stesso major. Scartata: un
  hash sconosciuto non dimostra compatibilità; fail-closed.
- **B — capability libere**: ignorare capability non riconosciute. Scartata: il MCP non
  deve esporre né presumere superfici fuori dalle 25 route.

Da ratificare in PF-API-0: nomi definitivi dei campi, algoritmo condiviso dello schema
hash (descrittore canonico comune ai due repository) e nomi delle capability.

## Punti aperti (fail-closed finché non ratificati)

1. **Conferma MANUAL** (decisione owner 08/10: preview → operation_id + handle breve →
   secondo comando owner). Alternative: (a) `POST /v1/orders` con `confirmation_handle`
   legato all'`operation_id` della preview — nessuna route nuova, proposta; (b) campo di
   conferma in `POST /v1/preview` — scartata perché la preview deve restare senza effetti.
   Finché non ratificata: nessun tool MANUAL.
2. **Tavoli Roserpina**: nessuna route dedicata. Proposta: snapshot di sola lettura dentro
   `GET /v1/exposure`; alternativa: dentro `GET /v1/status`. Nessuna logica MM nel MCP.
3. **SIM con ordini reali** (scelta B owner 13/10, conflitto contrattuale aperto in
   Pickfair-nogui #491): il MCP non deduce mai la destinazione di esecuzione; la legge
   solo dallo stato autorevole del core. Nessun campo o tool finché non ratificato.
4. **Ingresso automatico da servizi esterni** senza conferma per ordine
   (OWNER-MCP-AUTO-ORDER-01, futuro): richiede un principal dedicato in MCP-01b+ e la
   ratifica del contratto; nessuna implementazione ora.
5. **Journal di idempotenza (MCP-01b)**: il guard del core (`MCP_FORBIDDEN_RE`) vieta
   `sqlite3` nel codice MCP; il journal userà un file append-only proprio con fsync, mai
   il DB Pickfair.

## Limiti noti di MCP-01a (non bloccanti)

- **Tool sconosciuto o argomenti non validi**: restituiti come risultato di tool con
  `isError: true` e codice `UNKNOWN_TOOL` / `INVALID_REQUEST`, non come errore JSON-RPC
  -32602. Scelta deliberata: il client riceve sempre l'envelope strutturato. Da rivedere
  se il client di riferimento richiede l'errore di protocollo.
- **JSON malformato dal client**: l'SDK `mcp` 1.30.0 non risponde con -32700, ma invia una
  notifica generica «Internal Server Error». Nessun dato del client viene riportato e
  nessuna operazione viene eseguita.
- **Altri comportamenti dell'SDK**: metodo sconosciuto con -32602 invece di -32601;
  `notifications/cancelled` può produrre una risposta con codice 0; `structuredContent`
  inviato anche a client che negoziano 2024-11-05.
- **Chiusura**: chiusura di stdin ⇒ exit 0 con audit `server_stop` `ok`; SIGINT ⇒ exit 130
  con `server_stop` `interrupted`. Il thread di lettura di stdin dell'SDK non è
  interrompibile e non è daemon: con stdin lasciato aperto dal client né il Runner né la
  finalizzazione dell'interprete terminano prima della riga successiva o di EOF. Per questo
  ogni chiusura `interrupted` ignora i SIGINT successivi, scrive una sola riga di audit ed
  esce con `os._exit(130)` senza attendere stdin: subito se SIGINT ripetuti interrompono il
  Runner, altrimenti dopo il watchdog di 2 s (`INTERRUPT_GRACE_S`) armato dal primo SIGINT.
  Un SIGINT che interrompe `main` prima dell'uscita lascia il watchdog armato. Raffiche di
  SIGINT: dal secondo SIGINT i successivi sono ignorati (al più un altro KeyboardInterrupt
  del Runner); a fine loop il gestore resta installato ma non delega più al Runner, e appena
  `anyio.run` termina SIGINT è ignorato prima di decidere l'esito, perché in finalizzazione
  CPython riporterebbe il gestore a SIG_DFL (exit -2 senza riga di audit). La riga
  `server_start` è scritta solo dopo l'installazione del gestore. Finestra di avvio non
  coperta (limite noto, pochi ms): un SIGINT durante avvio dell'interprete e import termina
  con traceback ed exit -2; durante l'avvio del loop, prima che il Runner installi il suo
  gestore, con 130 e `server_stop` senza `server_start`; nel loop prima di `install`, il
  Runner annulla il task senza che il tracker lo registri e il server attende la chiusura
  di stdin, poi esce con 130 (riproducibile solo iniettando il segnale). A riposo il
  watchdog è il percorso normale, quindi un singolo SIGINT chiude in circa 2 s. L'uscita non
  svuota buffer pendenti: una risposta JSON-RPC in scrittura in quel momento può restare
  troncata (caso teorico, mai osservato). Un SIGINT ignorato dal processo padre resta
  ignorato. SIGTERM termina subito, senza riga di audit `server_stop`.
- **Handshake serializzato**: chiamate concorrenti a `get_meta` attendono in coda; con
  upstream lento l'attesa può arrivare a N × timeout, sempre fail-closed.

## MCP-01b — Identità delle richieste e journal (pickfair-mcp- #4)

- `request_id` (`req_` + 32 hex) generato dal MCP per ogni chiamata; `operation_id` e
  `correlation_id` sono quelli restituiti dall'upstream (formato accettato
  `[A-Za-z0-9_-]{1,64}`; la semantica definitiva resta da allineare in PF-API-0 / MCP-01d).
- Journal append-only JSON Lines (`src/pickfair_mcp/journal/`), nessun database. Record
  versionati (`v=1`), `seq` contiguo, checksum SHA-256 per riga; tipi `header`, `begin`,
  `sent`, `outcome`. `begin` e `sent` sono scritti con `fsync` prima dell'invio, `outcome`
  dopo l'esito. Il journal contiene solo identificativi e l'hash della chiave logica.
- Deduplica: stessa chiave logica ⇒ stessa voce, zero chiamate upstream aggiuntive (anche
  in parallelo e dopo il riavvio). La chiave è ancora interna (D-10 aperta: chiave fornita
  dal client non implementata).
- Recovery senza replay: `begin` senza `sent` ⇒ `NOT_SENT`; `sent` senza esito ⇒
  `AMBIGUOUS`, da verificare solo con letture (`get_operation`, MCP-02d). Timeout, errore
  o risposta non valida dopo l'invio ⇒ `AMBIGUOUS`, mai retry.
- Fail-closed (`JOURNAL_UNAVAILABLE`): file corrotto/troncato/manomesso, sostituito, lock
  detenuto da un altro processo, path non assoluto o con `..`, symlink, permessi, disco
  pieno o `fsync` fallito. Le letture restano consentite. Una scrittura parziale lascia
  una riga troncata: al riavvio il journal resta fail-closed fino a intervento owner.
- Retry solo per letture idempotenti (`read_with_retry`, max 5 tentativi).
- Nessun tool nuovo esposto: `MCP_MUTATION_EXPOSURE` invariato. Il server esegue la
  recovery all'avvio se riceve un journal (`build_server(..., journal=...)`); il cablaggio
  da CLI (percorso configurabile) non fa parte di questa scheda.
- Prove: adapter/upstream simulato deterministico. Non è integrazione Pickfair reale.
