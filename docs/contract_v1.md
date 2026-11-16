# Contratto Control API v1 — vista dell'adapter MCP

Stato: **PROVISIONAL**. La Control API di Pickfair non esiste ancora (PF-API-0/1/commands).
Questo documento descrive ciò che l'adapter si aspetta e come si comporta; non
crea route né semantiche di prodotto. Le 25 route sono quelle approvate in pickfair-mcp- #1, più le 4 di
sola lettura della scatola nera ratificate dalla decisione owner PF-BLACKBOX-01 (08/11/2026).

## Route approvate (copia verificata dai test)

| Tipo | Metodo | Route | Tool MCP | Stato |
|---|---|---|---|---|
| Read | GET | `/v1/meta` | `get_meta` | Esposto, adapter simulato |
| Read | GET | `/v1/status` | `get_status` | Esposto, adapter simulato (MCP-02a) |
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
| Read | GET | `/v1/reconciliation/status` | `get_reconciliation_status` | Esposto, adapter simulato (MCP-02a) |
| Read | GET | `/v1/audit/{correlation_id}` | `get_audit_trail` | Non esposto (MCP-02) |
| Read | GET | `/v1/blackbox/status` | `get_blackbox_status` | Esposto (MCP-01o, PF-BLACKBOX-01) |
| Read | GET | `/v1/blackbox/sessions` | `list_blackbox_sessions` | Esposto (MCP-01o, PF-BLACKBOX-01) |
| Read | GET | `/v1/blackbox/events` | `list_blackbox_events` | Esposto (MCP-01o, PF-BLACKBOX-01) |
| Read | GET | `/v1/blackbox/events/{event_id}` | `get_blackbox_event` | Esposto (MCP-01o, PF-BLACKBOX-01) |
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

## MCP-01c — Principal e scope

- Scope: `read`, `write`, `admin`, `owner`. Sono **insiemi** espliciti: nessuna gerarchia implicita (un principal `owner` senza `read` non può leggere).
- Mappa statica tool → scope minimo (`pickfair_mcp.auth.TOOL_SCOPES`, immutabile): le 14 letture → `read`; `preview_order`, `place_order`, `place_dutching`, `cancel_order`, `replace_order`, `cashout`, `stop`, `reconcile` → `write`; `set_mode`, `patch_config`, `resume` → `owner` (`resume` sempre owner-only per ogni tipo di stop, decisione owner 22/10, finding C1). `stop` con qualificatore `EMERGENCY` → `owner`. `admin` non è richiesto da alcun tool del catalogo attuale.
- Registrazione: ogni `ToolSpec` dichiara `scope`; scope assente (`SCOPE_UNDECLARED`) o diverso dalla mappa (`SCOPE_MISMATCH`) ⇒ registrazione rifiutata all'avvio.
- Server: il controllo di scope avviene subito dopo la risoluzione del nome, **prima** della validazione input e di qualunque handler/adapter. Rifiuto ⇒ errore `FORBIDDEN` (reason `PRINCIPAL_MISSING`, `PRINCIPAL_INVALID` o `SCOPE_MISSING`), non retryable, audit `tool_call` con `outcome=forbidden` e `principal_id`, zero chiamate upstream.
- Lo scope non è mai dedotto da argomenti della richiesta o da testo upstream.
- Principal: `id` `[a-z0-9][a-z0-9_-]{0,31}`, scope non vuoti; `parse_principal` accetta solo le chiavi `id` e `scopes` (chiavi extra, es. credenziali, ⇒ rifiuto); nessun campo credenziale esiste, quindi nessuna credenziale può comparire in stdout, stderr, audit o journal.
- Processo stdio (`pickfair-mcp serve`): principal fisso `local-stdio` con solo `read`; nessun flag/variabile/file lo eleva.
- Aperti: D-11 (autenticazione MCP ↔ Control API, MCP-01d); conferma MANUAL owner-only da agganciare quando il relativo tool sarà definito.

## MCP-02a — `get_status` e `get_reconciliation_status` (pickfair-mcp- #7)

Schemi PROVISIONAL, definiti sui dati che il core possiede davvero (verificato su
Pickfair-nogui `7a70062`, `RuntimeController` reale). Modelli strict in `contract/models.py`,
tool in `tools/status.py`.

Regole comuni alle due risposte:

- `source`: `"core"` o `"simulated"`. Il tool rifiuta (`UPSTREAM_INVALID_RESPONSE:SOURCE_MISMATCH`)
  una risposta la cui sorgente non coincide con l'adapter: un risultato simulato non passa mai per
  dato Pickfair. Il risultato porta anche `upstream.kind` / `upstream.certified`.
- `observed_at` (epoch s) e `age_s`: snapshot più vecchio di 30 s o nel futuro oltre 5 s ⇒
  `STALE_SNAPSHOT`.
- Un campo che il core non possiede è `null` **ed** è elencato in `unavailable`; le due condizioni
  si implicano (mai un default).
- Codici e motivi sono token `^[A-Z][A-Z0-9_]{0,63}$`: niente testo libero dall'upstream.
- Handshake compatibile con la capability della route prima di ogni lettura; retry solo per
  timeout/indisponibilità, al massimo 2 tentativi.

`GET /v1/status`: `runtime_state` (STOPPED/ACTIVE/PAUSED/LOCKDOWN), `execution_mode` (solo SIM/LIVE;
il core usa `SIMULATION` e la Control API lo mappa), `live_enabled`, `readiness` (`level`, `ready`,
`blockers`, `mcp_aware` — oggi sempre `false`: la readiness MCP-aware è di PF-API-0), `stop`
(`emergency_stopped`, `emergency_reason`, `risk_stop_reason`, `daily_loss_pending_stop`,
`kill_switch_active`).

`GET /v1/reconciliation/status`: `startup` (`NOT_RUN`/`OK`/`REQUIRED`, `reason`, `recovery_failure`),
`ambiguities_pending`, `ghosts` (`ghost_orders`, `suspected_ghosts`, `unconfirmed_inflight`),
`hedge_registry_unreliable`, `recovery_state` (`unreadable`, `persist_failed`).

Scenari dell'adapter simulato (`--sim-status-scenario`): `sim_ready`, `live_blocked`, `stop_active`,
`reconciliation_required`, `not_started` e i casi ostili (`malformed`, `extra_field`, `non_finite`,
`oversized`, `injection_text`, `inconsistent`, `wrong_source`, `stale`, `future`, `timeout`,
`unavailable`).

Limiti noti:

- lo schema hash condiviso copre ancora solo route e schema di `/v1/meta`: una modifica agli schemi
  di stato non cambia l'hash (algoritmo comune da ratificare in PF-API-0);
- l'adapter HTTP (MCP-01d) non esiste: le prove con il core reale usano un harness di test nel
  repository Pickfair-nogui (`tests/control_api/test_mcp_chain_crossrepo.py`) e non certificano MCP-01d.

## MCP-01d — adapter HTTP di prodotto e contratto 1.1.0

- **Adapter** `src/pickfair_mcp/adapters/http.py`: unico modulo con import di rete (`http.client`,
  `socket`), eccezione alle guardie circoscritta e verificata da `tests/guards/test_no_bypass.py`.
  Socket IPv4 diretto verso `127.0.0.1` (nessuna risoluzione di nomi), nessun proxy, nessun redirect,
  timeout, corpo letto al massimo fino a 64 KiB + 1, status 200 e `application/json; charset=utf-8`
  obbligatori. Errori tipizzati: `UPSTREAM_TIMEOUT`, `UPSTREAM_UNAVAILABLE` (ritentabili),
  `UPSTREAM_UNAUTHORIZED` (nuovo, non ritentabile), `UPSTREAM_INVALID_RESPONSE:HTTP_<n>|CONTENT_TYPE|…`.
  Ogni guasto, 401 o rilettura del token incrementa `connection_epoch` ⇒ nuovo handshake.
  Nessun fallback verso il simulato.
- **CLI**: `pickfair-mcp serve --adapter http --control-api-port <p> --control-api-token-file <path>`;
  configurazione errata ⇒ exit 2 con `CONFIG_ERROR: <codice>`, mai un adapter diverso.
  La sorgente è obbligatoria (C-AUD-10): senza `--adapter` ⇒ exit 2 con
  `CONFIG_ERROR: SOURCE_REQUIRED`, prima di costruire qualsiasi adapter; nessun default simulato.
- **Token (D-11, prima implementazione)**: file 0600 dello stesso utente, cartella non scrivibile da
  altri, niente symlink, alfabeto URL-safe 43–128 caratteri; su 401 una rilettura e un solo nuovo
  tentativo (rotazione). Su sistemi non POSIX il file è rifiutato (`TOKEN_PLATFORM_UNSUPPORTED`; dal 05/11/2026 anche in avvio, come errore d'uso della CLI e mai come traceback: prima `os.getuid` assente su Windows dava `AttributeError`. Lato Control API la scrittura del token su Windows fallisce ancora con un'eccezione non dichiarata, catturata dal launcher del core (`CONTROL_API_NOT_STARTED: AttributeError`, fail-closed); il codice dichiarato arriva con il prossimo cambio di versione del package)
  finché non esiste una verifica equivalente delle ACL.
- **Contratto 1.1.0**: descrittore canonico generato dal codice (`pickfair-mcp contract-descriptor`),
  due copie identiche (`src/pickfair_mcp/contract/descriptor_v1.json`,
  `src/pickfair_control_api/contract_v1.json`); lo schema hash copre route, schemi upstream,
  input/output dei tool, codici d'errore e semantica. Nuovo campo obbligatorio
  `consistency = "PER_FIELD_NON_ATOMIC"` nelle risposte di stato.
- **Control API** (`src/pickfair_control_api/`, solo libreria standard): server di sola lettura con
  provider del core, auto-verifica di ogni risposta (`CONTRACT_SELF_CHECK`), token nuovo a ogni avvio
  e rotazione a doppia accettazione. Il ponte verso il `RuntimeController` appartiene a Pickfair-nogui:
  consegnato a Claude B in `docs/handoff/`.

## MCP-01e — `get_account` e `get_exposure` (contratto 1.2.0)

Route già approvate (pickfair-mcp- #1), nessuna route nuova: per OWN-MCP-02F si estendono prima le
route esistenti. Il contratto sale a **1.2.0** (aggiunte compatibili nello schema, ma lo schema hash
cambia: MCP e Control API si aggiornano insieme, una 1.1.0 viene rifiutata con `CONTRACT_INCOMPATIBLE`).

| Tool | Route | Contenuto |
|---|---|---|
| `get_account` | `GET /v1/account` | `execution_mode` (base del denaro: SIM = saldo fittizio), `bankroll` (start, corrente, picco, equity, P&L realizzato/non realizzato, drawdown %), `cash` (verificata sì/no, cassa, impegnato, motivo), `exchange_funds` (ultimo snapshot registrato dal runtime: disponibile, impegnato, cassa, esito, sorgente, età), `desk_mode` |
| `get_exposure` | `GET /v1/exposure` | `tables` (tavoli Roserpina: id, stato, occupato, id mercato/selezione, esposizione, perdita da recuperare), `total_exposure` (valore del cap `max_open_exposure`), `recovery` (tavoli in recovery, massimo, recovery consentito) |

Regole aggiunte:
- **Consistenza `PER_SECTION_LOCKED`**: ogni sezione viene da una chiamata del core sotto il lock del
  componente che la possiede; nel ponte del core `bankroll`+`cash` condividono la stessa acquisizione
  del lock del RiskDesk e `tables`+`total_exposure`+`recovery` quella del lock dei tavoli (attesa
  massima 0,25 s, poi sezioni indisponibili: le letture non bloccano mai il motore).
- **Denaro**: float finiti in EUR come li tiene il core, limite ±1e9, mai arrotondati o sostituiti
  da default; un valore non finito o fuori tipo rende la sezione indisponibile.
- **Nessun testo libero**: nomi di eventi, `meta` dei tavoli e `customer_ref` non escono; gli
  identificativi di mercato/selezione devono rispettare `^[0-9A-Za-z._-]{1,32}$`.
- **Regole fra campi** (le applica il MCP; JSON Schema non le esprime e la Control API le rispetta per
  costruzione): cassa verificata ⇔ importo presente e nessun motivo; fondi `ok` ⇔ nessun motivo;
  `desk_mode` solo con `bankroll`; `table_id` unici. Elenco esplicito in
  `tests/unit/test_contract_descriptor.py::MCP_ONLY_RULES`.
- **`desk_mode`** usa la regola di `get_status` del core (bankroll corrente rispetto al picco) sui
  valori della sezione `bankroll`: le decisioni del Money Management sul singolo ordine considerano
  anche perdita giornaliera e crescita del ciclo e possono differire.
- **Route approvate non servite**: la Control API risponde `501 NOT_IMPLEMENTED`; il MCP restituisce
  `UPSTREAM_NOT_IMPLEMENTED` (nuovo codice, non ritentabile). Percorso fuori contratto `404`, metodo
  diverso da GET `405`: nessun comando è servito.
- **Un solo elenco di tool**: `tools.register_read_tools` alimenta sia il server reale sia il
  descrittore del contratto (guardia `tests/guards/test_tool_surface.py`; prima di MCP-01e il server
  aveva un elenco proprio e le due cose potevano divergere).

## MCP-01f — diagnostica, protezioni e posizioni (contratto 1.3.0)

Nessuna route nuova: `GET /v1/status` si estende (OWN-MCP-02F) e `GET /v1/positions` è già approvata.

**`get_status` → `engine`** (sezioni nullabili con `unavailable` proprio): `trading_engine` (stato e
componenti calcolati dal core all'avvio del motore, `evaluated_at = ENGINE_START`; READY solo se ogni
componente è READY), `betfair` (connesso, cliente, SIMULATION/LIVE, errore presente sì/no, keepalive;
mai credenziali né testo d'errore), `stream`, `io`, `event_bus`, `queues` (cashout in volo e incerti,
ordini DIRECT), `modes` (modalità configurata, flag SIM, LIVE abilitato, readiness LIVE, cliente
effettivo; `read_only_mode = "NOT_IN_CORE"`: il core non ha una modalità READ_ONLY), `last_signal_at`.

**`get_status` → `protections`**: 22 voci fisse (kill switch, emergency, lockdown del runtime e del
desk, stop drawdown % e assoluto, perdita di sessione e giornaliera, risk stop, stop di esposizione,
cap di esposizione, percentuali obbligatorie, freschezza dei fondi, book, stato negoziabile, anti-
duplicazione, circuit breaker degli ordini, stato di recovery). Ogni voce: `state`, `reason`, `source`,
`limit` (Decimal), `as_of` (epoch). Regole:
- `ACTIVE` è l'unico stato senza motivo (nello schema: unione di due forme, la verifica anche la
  Control API); `INACTIVE` dice perché (non configurata, disattivata, applicata solo in LIVE);
- `UNKNOWN`: il core ha la protezione ma il valore non è leggibile (lettura fallita, lock occupato,
  limite illeggibile); `UNAVAILABLE`: il core non la espone ancora. **Nessuno dei due vale come
  sicuro**; gli elenchi derivati `disabled` e `unverifiable` devono coincidere con le voci;
- le regole sono quelle del core chiamate direttamente; nessun limite nuovo, nessun ricalcolo.

**`list_positions`**: `market_id`, `selection_id`, `side` (BACK/LAY/FLAT), `table_id`, `open_size`,
`avg_entry_price`, `realized_pnl`, `unrealized_pnl` (ultimo mark-to-market del core), `exposure`,
`liability`. `amounts_source = LEDGER_DECIMAL` (registro Decimal, senza perdita) o `CORE_FLOAT`
(solo prezzo e size dal float del core, il resto indisponibile). Nomi di eventi e riferimenti interni
non escono.

**Decimal**: stringa canonica `^(?:-?[1-9]\d{0,14}(\.\d{1,28})?|0(\.\d{1,28})?|-0\.\d{0,27}[1-9])$`
(niente esponente, «+», zeri iniziali o zero negativo). Il MCP non fa aritmetica su questi valori. Gli
importi di `get_account`/`get_exposure` (1.2.0) restano float: migrarli è una modifica di contratto
separata, non retroattiva.

## MCP-01g — `list_orders` (contratto 1.4.0)

Route già approvata `GET /v1/orders`. Fonte: il ledger durevole `orders` del core, letto dalla
Control API con una connessione SQLite separata e in **sola lettura** (`mode=ro` + `query_only`) in
una sola transazione (`consistency = SINGLE_READ_TRANSACTION`). Nessuna chiamata di rete.

Ogni ordine: `local_id`, `bet_id`, `role` (ENTRY / HEDGE del cashout / DUTCHING_LEG), `core_status`
(stato reale del core) e `status` (contratto), `market_id`, `selection_id`, `side`, `price`, `stake`,
`size_matched`, `avg_price_matched`, `size_remaining` (Decimal), `table_id`, `created_at`,
`updated_at`, `reconciliation` (`in_reconciliation`, `in_engine_queue`, `finalized`,
`ambiguity_reason`), `broker_view` (SIM: PRESENT/ABSENT nel broker simulato; LIVE: NOT_CHECKED).
L'esposizione per ordine non è nel ledger: non è riportata (nessun ricalcolo).

Mappa degli stati (`ORDER_STATUS_MAP`, pubblicata nella semantica del contratto e quindi nell'hash):
INFLIGHT, HEDGE_PENDING → PENDING; SUBMITTED, ACCEPTED_FOR_PROCESSING, HEDGE_PLACED → ACCEPTED oppure
UNMATCHED / PARTIALLY_MATCHED / MATCHED solo con quantità abbinata e residua esplicite e coerenti;
HEDGE_UNMATCHED → UNMATCHED; COMPLETED → MATCHED; FAILED, HEDGE_FAILED → FAILED; DENIED → REJECTED;
DUPLICATE_BLOCKED; AMBIGUOUS, HEDGE_AMBIGUOUS → AMBIGUOUS; ogni altro → UNKNOWN. APPROVED, CANCELLED e
SETTLED non esistono nel ledger e non compaiono.

`snapshot.state`: OK; PARTIAL (righe illeggibili contate in `omitted`, o elenco troncato); STALE
(letto, ma la riconciliazione d'avvio del core non è conclusa); UNKNOWN (database occupato);
UNAVAILABLE (non leggibile). Solo con OK l'elenco è completo; con UNKNOWN/UNAVAILABLE non c'è elenco
(mai un elenco vuoto «rassicurante»). Valori mancanti null, mai zero; betId mai inventato.

## MCP-01h — SL/TP, settlement, barriere di cashout (contratto 1.5.0)

Estensioni di route già approvate (OWN-MCP-02F), nessuna route nuova.

- **`get_exposure` → `tables[].sl_tp`**: `state` (NOT_ARMED / ARMED / TRIGGERED / UNKNOWN),
  `stop_loss`, `take_profit` (importi), `stop_loss_pct`, `take_profit_pct`, `trailing_stop_pct`
  (Decimal non negativi). Letto dal `meta` del tavolo nelle chiavi che il core usa; il resto del `meta`
  (nomi di eventi, riferimenti) non esce. NOT_ARMED ⇔ nessun importo; ARMED/TRIGGERED ⇒ almeno un
  importo; valore presente ma illeggibile ⇒ UNKNOWN (mai «non armato»). **Sul `main` attuale del core
  nessun percorso arma SL/TP**: ogni tavolo è NOT_ARMED, ed è lo stato reale. La forma scritta da F-02
  (Claude D, non ancora integrato) è provata compatibile. Il trailing compare solo come percentuale: il
  core non ha logica di trailing.
- **`get_reconciliation_status` → `settlement`** (solo conteggi): `unrecorded_settlements`,
  `held_batches`, `effects` (`settlement_effects`: `held`, `not_realized`, `by_outcome`),
  `checkpoints` (`cycle_recovery_checkpoints` per fase, fase sconosciuta UNKNOWN, `cycle_ambiguous`,
  `submit_ambiguous`), `sim_settlements` (null in LIVE). Nessun payload, riferimento o nome di evento.
- **`get_status` → `engine.queues.cashout_barriers`**: barriere di cashout attive. Gli hedge dei cashout
  sono in `list_orders` (`role = HEDGE`).

## MCP-01j — `get_config` (contratto 1.6.0)

Route già approvata (`GET /v1/config`, scope READ), nessuna route nuova; mandato owner del 05/11/2026
(«sola lettura, segreti e credenziali sempre oscurati»).

- **Fonte**: `RoserpinaConfig` del runtime (`rc.config`), letta con un solo riferimento
  (`reload_config` la sostituisce intera): consistenza `SINGLE_REFERENCE_READ`.
- **Allowlist chiusa** di 42 chiavi (`models.CONFIG_KEYS`, ripetuta in `semantics.config.keys`): percentuali
  di rischio, cap assoluti opzionali, soglie di drawdown, moltiplicatori, profilo di rischio, numero di
  tavoli, recovery, anti-duplicazione, guardie di book e liquidità, commissione, stake e quota minimi,
  avvisi max_win/stake/epsilon, auto-green. Le voci sono tutte presenti, una volta, nell'ordine del
  contratto.
- **Valore**: `kind` DECIMAL (stringa decimale esatta), BOOL, INT o ENUM (CONSERVATIVE/BALANCED/
  AGGRESSIVE); `state` SET (valore presente), NOT_SET (solo per i 16 campi `Optional` del core: non
  configurato; per le percentuali di rischio il core nega ogni nuova entrata, per i cap significa non
  attivo) o INVALID (valore presente ma illeggibile: mai convertito in zero).
- **Segreti**: credenziali Betfair e Telegram, certificati, token e impostazioni persistite non sono
  mai letti dalla vista. Un campo del core fuori allowlist compare solo per **nome** in `unlisted`
  (massimo 64, mai il valore); un nome sensibile o non canonico è soltanto contato in `redacted`. Il
  MCP rifiuta un `unlisted` che contiene un frammento di `SENSITIVE_NAME_FRAGMENTS` (seconda
  barriera rispetto a `core.redaction.is_sensitive_key` del core).
- **Sola lettura**: nessun parametro di input, nessuna scrittura. `patch_config` resta un comando non
  esposto (design in `docs/design/WRITE_OPERATIONS_DESIGN.md`).

## MCP-01k — compatibilità con le correzioni di Claude D (contratto 1.7.0)

Nessuna route nuova. Regola nuova del contratto: un ordine con esito non confermato (`status` AMBIGUOUS o
PENDING) non porta mai `size_matched`, `avg_price_matched` o `size_remaining`; il `bet_id` resta (identità della
riconciliazione del core). Motivo: il fix P0 di Claude D conserva sulla riga AMBIGUOUS la risposta senza esito,
che può contenere un report con `sizeMatched`. Quel numero non è un dato confermato. Lo schema lo ammette, la
regola è applicata dal MCP (`UNCONFIRMED_ORDER_STATUSES`) e dal ponte del core (`UNCONFIRMED_STATUSES`).

`protections.funds_freshness.limit`: il ponte non ricalcola la soglia del core. Con F-16 (soglia owner 30 s)
il limite è `null` finché il core non espone un accessore unico; sul `main` attuale resta 120 s.

## MCP-01l — `list_markets` e `get_market_book` (contratto 1.8.0)

Route già approvate (`GET /v1/markets`, `GET /v1/markets/{id}/book`), nessuna route nuova. Fonte: il
`MarketTracker` del core, cioè l'ultimo book che Pickfair ha ricevuto per ogni mercato, copiato in una sola
lettura (`SINGLE_REFERENCE_READ`). Nessuna chiamata di rete: un mercato che Pickfair non segue risponde
`state = NOT_TRACKED`.

- `list_markets`: `market_id`, `book_status` (dato Betfair OPEN/SUSPENDED/CLOSED/INACTIVE, altrimenti UNKNOWN),
  `inplay`, numero di `runners`, `total_matched`, `last_match_time`; elenco ordinato, al più 256 (`truncated`),
  voci illeggibili contate in `omitted`.
- `get_market_book` (`market_id` obbligatorio, `^[0-9]{1,4}\.[0-9]{1,15}$`): per ogni runner `status`,
  `last_price_traded`, `total_matched` e i tre migliori livelli `back` (prezzo decrescente) e `lay` (crescente)
  come stringhe decimali; runner illeggibili contati in `omitted_runners`. Il MCP rifiuta un book di un mercato
  diverso da quello richiesto.
- Prima route con parametro: la Control API accetta solo l'id nel pattern stretto (altrimenti 404, nessuna
  chiamata al core) e passa al provider il valore già validato; l'adapter HTTP ricontrolla prima di costruire
  il percorso.

Limiti dichiarati: `book_status` non è un giudizio di negoziabilità (quello è la protezione
`market_tradability`, F-23); l'età del book è nota solo con `last_match_time` (il tracker non registra
l'istante di ricezione); `list_events` resta 501: il core non ha un catalogo degli eventi senza rete.

## MCP-SEC-01 — irrobustimento di sicurezza (contratto 1.9.0)

Revisione di sicurezza indipendente del 05/11/2026 (sola lettura, riproduzioni eseguibili) sul package
`pickfair_control_api` e sul server MCP. Nessun bypass dell'autenticazione, nessun percorso di scrittura, nessuna
fuga di token o di testo d'eccezione. Corrette quattro debolezze riprodotte (test RED → GREEN in
`tests/control_api/test_security_hardening.py`):

| # | Debolezza | Correzione |
|---|---|---|
| 1 | `TokenStore` accettava un token vuoto o corto (`MIN_TOKEN_CHARS` definito ma non usato) | token di 43–256 caratteri URL-safe, altrimenti `WeakTokenError` (messaggio senza il token) |
| 2 | due rotazioni concorrenti con una scrittura fallita: token revocato di nuovo valido, token del file rifiutato | rotazione serializzata per intero da un lock dedicato |
| 3 | connessioni senza token tenute aperte all'infinito (un thread ciascuna nel processo Pickfair) | al più 16 connessioni servite insieme (le altre chiuse senza thread); scadenza complessiva di 10 s per connessione |
| 4 | errori di protocollo della libreria standard in HTML con l'eco dell'input; traceback su stderr alla disconnessione | `400 BAD_REQUEST` / `405 METHOD_NOT_ALLOWED` in JSON fisso; nessun traceback per richiesta |

Codice d'errore nuovo nel contratto: `BAD_REQUEST`. Rischio residuo accettato e dichiarato: i campi codice
(`^[A-Z][A-Z0-9_]{0,63}$`) arrivano all'agente come il core li produce (alfabeto ristretto, 64 caratteri, mai
testo libero); le descrizioni dei tool dichiarano che sono dati, non istruzioni.
## MCP-01i — stato della chiusura SL/TP (contratto 1.10.0, dipende da F-04)

Estensione di una route già approvata (`GET /v1/exposure` · `get_exposure`), nessuna route nuova. La sezione
`sl_tp_closes` è sempre presente:

- `OK`/`PARTIAL` (record illeggibili contati in `omitted`, elenco oltre 64 `truncated`) con `closes`;
- `UNAVAILABLE` `CORE_PENDING_F04` (core senza F-04) o `DB_UNREADABLE`; `UNKNOWN` `DB_BUSY`.

Ogni chiusura riporta solo dati **persistiti** dal core (record F-04 `risk.sl_tp_close.<customer_ref>`, ordini
della posizione, righe d'hedge del ledger, una transazione di sola lettura): tavolo, mercato, selezione, lato,
`trigger` (STOP_LOSS/TAKE_PROFIT/UNKNOWN), `close_state` (CLAIMED/ROUTED/NOT_EXECUTED/UNCERTAIN/UNKNOWN),
`retryable` (dal core: solo NOT_EXECUTED, e solo con un nuovo scatto), `detail` (codice), `recorded_at`,
`bet_ids` della posizione, `position` (ordini, parzialmente abbinati, in riconciliazione, ambigui, illeggibili:
stessa mappa di `list_orders`), `residual_exposure` solo se il tavolo porta ancora la posizione
(`residual_source` TABLE / TABLE_RELEASED / UNAVAILABLE), `hedges`: le righe d'hedge legate alla chiusura dal
record di F-04 (`cashout_request_ids` → `cashout_request_id` della riga), con `requests` e `not_in_ledger`
(richieste senza riga nel ledger); `null` se il record non porta il legame.

Limiti dichiarati: le chiusure respinte prima della rivendicazione
(es. `ORDER_STATE_UNCERTAIN`) non sono persistite dal core e non compaiono; il `customer_ref` non esce mai.
**Non integrabile finché F-04 non è su `main`.**

## MCP-01m — trailing stop (F-03), percentuali F-02, impostazioni non valide F-18 (contratto 1.11.0)

Preparato offline sopra MCP-01i: **non integrabile finché F-03 (`claude/d-f03-trailing-stop`, che contiene F-02 e F-04)
non è su `main`**. Nessuna route nuova.

- `get_exposure.tables[].sl_tp.trailing`: `state` NOT_IN_CORE (core senza la logica di trailing: la percentuale, se
  c'è, non è applicata), OFF, WAITING_PROFIT, ARMED, TRIGGERED, UNKNOWN (picco persistito illeggibile: il core non
  decide); `pct`, `peak`, `threshold` (calcolata da `core.trailing_stop.threshold`), `peak_source` MEMORY (dal `meta`)
  o PERSISTED (`risk.trailing_peak.<customer_ref>`, letto fuori dal lock dei tavoli finché il runtime non lo carica).
  Uno scatto del trailing non cambia lo stato di SL/TP.
- `get_exposure.sl_tp_closes[].trigger`: anche `TRAILING_STOP` (chiusura di F-04 scattata dal trailing).
- `get_config`: `stop_loss_pct`, `take_profit_pct`, `trailing_stop_pct` (F-02) nell'allowlist (45 chiavi);
  `invalid_persisted` (F-18): le impostazioni persistite illeggibili per nome (`roserpina.<nome>`), nomi sensibili solo
  contati, `null` senza F-18. Chiude il limite dichiarato in MCP-01j.
- `get_status.protections.config_validity` (23 protezioni): TRIGGERED `CONFIGURAZIONE_NON_VALIDA` quando il core ha
  impostazioni non valide e nega ogni nuova entrata; UNAVAILABLE `CORE_PENDING_F18` senza F-18.
- `resolve_git_sha` supporta i git worktree (prima la Control API rifiutava di partire con `GIT_SHA_UNRESOLVABLE`).


## MCP-01n — età del book (contratto 1.12.0, dipende da `claude/d-market-book-age`)

Preparato offline sopra MCP-01m: **non integrabile finché `claude/d-market-book-age` (Claude D, `ea81e93e`,
`MarketTracker.book_age_s`) non è su `main`**. Nessuna route nuova.

- `list_markets.markets[].book_age_s` e `get_market_book.book.book_age_s`: secondi trascorsi da quando Pickfair ha
  ricevuto l'ultimo book del mercato, presi da `MarketTracker.book_age_s` (istante monotono di ricezione del core; il
  ponte non ricalcola nulla). Stringa decimale non negativa, campo **obbligatorio** e nullable.
- L'età si legge **prima** dei book: il tracker scrive book e istante in due passi, quindi un aggiornamento concorrente
  può solo farla sembrare più vecchia del reale, mai più fresca.
- `null` quando non è dimostrabile: core senza `book_age_s` (forma attuale di `main`), mercato senza istante di
  ricezione, orologio monotono all'indietro, errore del tracker o valore non rappresentabile. Mai `0` al posto di
  un'età ignota, mai dedotta da `last_match_time`.

Chiude il limite dichiarato in MCP-01l («l'età del book è nota solo con `last_match_time`»), solo con il core di D.

## MCP-01o — lettura della scatola nera (contratto 1.13.0, PF-BLACKBOX-01)

Decisione owner PF-BLACKBOX-01 del 08/11/2026: quattro route di **sola lettura** oltre le 25 approvate
(`GET /v1/blackbox/status`, `/sessions`, `/events`, `/events/{event_id}`) e i quattro strumenti MCP
`get_blackbox_status`, `list_blackbox_sessions`, `list_blackbox_events`, `get_blackbox_event`. Nessuna route
di scrittura: l'MCP non può modificare, cancellare o falsificare il registro. Contratto di lettura e motivazioni
in `docs/design/BLACKBOX_READ_CONTRACT.md`.

- Record: `seq` persistente, `event_id`, `ts_utc` al millisecondo, sessione e PID, `origin`, `category`,
  `event_type`, `severity`, `phase` ATTEMPT/RESULT/OBSERVATION (un tentativo ha sempre esito `PENDING`),
  `outcome` (AMBIGUOUS dell'exchange = `UNKNOWN`), stati e valori prima/dopo, `reason_code`, `correlation_id`,
  `causation_id`, `refs` (mai `customer_ref`), `not_recorded`.
- Lacune `LOST`/`CORRUPT`/`RETENTION` riportate, mai riparate; sessione senza arresto registrato = `UNRECORDED`.
- Unica query string del server, solo su `/v1/blackbox/events`, in whitelist chiusa: 400 con codice fisso senza
  chiamare il core. Tutte le altre route restano «nessuna query».
- Ogni richiesta Control API è registrata dal ponte tramite `request_hook` (una volta per richiesta, mai per evento
  letto, con l'`X-Request-Id` dell'MCP); una richiesta non registrabile riceve `503 BLACKBOX_UNAVAILABLE`, tranne
  `/v1/blackbox/status`, che riporta `requests_unrecorded`.
- Valori di nomi sensibili sempre `[REDACTED]`: redatti dal motore, ri-redatti dal server, rifiutati dal modello
  MCP se arrivassero in chiaro.

Stato: offline. Il ponte del core si scrive sopra l'interfaccia di lettura di Claude B (§7 del contratto di
lettura); fino ad allora la suite crossrepo con il core reale è BLOCKED.

## MCP-01p — lettura della scatola nera pronta per BB-1 (contratto 1.14.0)

Allineamento al record reale del motore (`pf_blackbox_01.md` §3 di Claude B) prima dell'integrazione:
- `origin` comprende anche `TELEGRAM` e `CLI`; `severity` anche `TRACE` (filtri compresi);
- `refs.selection_id`; `data` (dettagli redatti dell'evento, per esempio la decisione di stake di Roserpina) e
  `omitted_values` (voci non rappresentabili, contate e non mostrate);
- il cursore di pagina può superare l'ultimo evento restituito quando gli ultimi record erano corrotti (lacuna
  CORRUPT), mai oltre `as_of_seq`;
- `/v1/meta` è servito anche se la richiesta non si può registrare (come `/v1/blackbox/status`): senza handshake
  l'MCP non raggiungerebbe lo stato del registro guasto;
- redazione precisa: i frammenti brevi (`auth`, `authorization`, `pem`, `otp`) contano solo come segmento intero
  del nome, così `stake_authorized` (G7) resta leggibile e `auth_header` no.

Adapter puro motore → vista `pickfair_control_api.blackbox_bridge` (`make_providers`, `make_request_hook`,
`check_reader`); condizioni di compatibilità in `docs/design/BLACKBOX_BB1_COMPATIBILITY.md`; contract test in
`tests/contract/` (suite G8 `mcp-contract`).

## MCP-01q — forma normativa di BB-1 (contratto 1.15.0)

La forma del lettore reale di Claude B (`core.blackbox_query.BlackBoxReader`) è normativa (decisione C/B del
09/11/2026). Cosa cambia nella vista:
- filtri di `list_blackbox_events` / `GET /v1/blackbox/events`: quelli di BB-1;
  - nuovi: `severity` (uguaglianza), `phase`, `selection_id`, `causation_id`;
  - tolti: `severity_min` e `q`, che il lettore del motore non ha: ora sono rifiutati con `QUERY_PARAM`;
- `order_id`, nei filtri e in `refs`: alias opaco `ord_<32 hex>` di BB-1 (schema D1, vedi sotto);
- `component`: ASCII stampabile, 1–64 caratteri (`thread:<nome>`);
- `not_reported` dello stato può comprendere `gaps`: una lista vuota non riportata dal motore non significa
  «nessuna lacuna».

Adapter:
- legge con `external=True`;
- passa `table_id`, `selection_id` e `order_id` come testo, perché BB-1 confronta per uguale con il testo
  registrato;
- usa l'hook `request_hook`;
- dà errore, mai una risposta parziale, su lacune per tempo, `get` in forma dict e qualunque forma non ancora
  mappata.

Dalle fixture reali di B (sha256 `74be0f92…36f6df`, in `tests/contract/fixtures/`), cosa cambia nella vista:
- eventi:
  - `not_recorded` è quello del motore (in BB-1 ogni null è «non registrato»);
  - `reason_code` può essere il nome di un'eccezione (`KeyError`);
  - `unrecorded_windows` `{seq, from_ts, to_ts, reason_code}` riporta le finestre di tempo non registrate
    (per esempio dopo un arresto non pulito); l'esito di una finestra è sempre sconosciuto;
- stato:
  - nuovi `degraded` e `dropped_non_critical`; un registro degradato non è mai disponibile;
  - `not_reported` può comprendere `degraded`, `dropped_non_critical` e `last_write_error_code`;
- sessioni:
  - nuovo `last_event_at`;
  - `ended_at` solo per CLEAN_STOP: per CRASH_DETECTED l'ora vera della fine non è nota.

Mappature verificate sulle fixture (RED 7 → GREEN 10). La prova sulla classe reale integrata resta NOT_RUN
(`docs/design/BLACKBOX_BB1_COMPATIBILITY.md` §10).

Schema BB-1 D1-D3, decisione owner PF-BB1-IDENTITY-TIMESTAMP-SESSION-20261109. L'owner l'ha data in sessione a
Claude B; il testo integrale è registrato da B in https://github.com/zarbopiero963-droid/Pickfair-nogui/issues/586#issuecomment-6740764129.
- **D1**: `refs.order_id` e il filtro `order_id` accettano solo l'alias opaco `ord_<32 hex>` (HMAC dell'id
  interno, stabile e non enumerabile). Un id interno, intero o uuid, in un record lo rende non mappabile (lacuna
  CORRUPT): mai mostrato.
- **D2**: nuovo `exchange_ts`, cioè l'ora dichiarata dall'exchange, distinta da `ts_utc` (ora osservata da
  Pickfair). Se manca è null e figura in `not_recorded`. L'ordine fa fede su `seq`.
- **D3**: un solo runtime per registro (lock del motore). Il lettore non apre sessioni: nessun cambiamento nella
  vista.
