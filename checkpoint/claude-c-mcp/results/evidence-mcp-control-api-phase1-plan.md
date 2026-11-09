# Pickfair MCP + Control API — Fase 1 (read-only): piano implementativo verificabile

Claude C, 09/11/2026. Mandato owner «PICKFAIR MCP + CONTROL API — PHASE 1», GO progettazione, NO DEPLOY.
Solo piano: nessun codice scritto per questo mandato, nessun branch modificato, nessuna PR.

## 0. Correzione della premessa: la Control API esiste già, non è integrata

Cosa ha visto Grok: il **main** di pickfair-mcp- (`36bbef1`). Lì ci sono solo `get_meta` e il catalogo, sull'adapter
simulato. Ma non è tutto il lavoro fatto.

| Pezzo | Dove si trova | Stato |
|---|---|---|
| Control API (`pickfair_control_api`): server stdlib, bind solo su 127.0.0.1, `Authorization: Bearer` con file di token 0600 e rotazione, solo GET (ogni altro metodo → 405), controllo della risposta contro lo schema, errori a codice fisso | pickfair-mcp-, branch `ccr-edf04c7d-e7vtj1-*` (ultimo `75e7280`) | Pronto, non su main |
| Contratto condiviso versionato: 1.15.0 con hash dello schema, 18 rotte di lettura, 11 comandi **solo catalogati** e rifiutati | stesso branch (`contract_v1.json` + descrittore MCP) | Pronto |
| Tool MCP di lettura + client HTTP autenticato (timeout, `X-Request-Id`, 503 → UPSTREAM_UNAVAILABLE, nessuna query non validata) | stesso branch | Pronto |
| Ponte nel core (`control_api/bridge.py`, `views.py`, `launcher.py` disattivato di default) | Pickfair-nogui, `handoff/claude-c/mcp-core-20261105` (13 handoff DURABLE, ultimo `0a52903`) | Consegnato a B, **non su main** |
| Test E2E tra processi reali (core che gira → Control API → MCP) | pickfair-mcp- `tests/crossrepo/` | Esistono; rieseguibili quando il ponte è su main |
| Lettura della scatola nera (4 rotte) | branch MCP + PR #617 | Verificata sulla classe reale, 17/18 |

**Vincolo principale.** Il ponte sull'handoff poggia su 53 commit che non sono su main. Circa 40 sono funzioni di D e
di B non ancora mergiate: F-02, F-03, F-04, F-13a/b, F-18, età del book. Non si può mergiare «così com'è». La Fase 1
quindi **non è da costruire, ma da riportare su main**, in forma minima.

## 1. Copertura delle domande dell'owner

| Domanda («Pickfair, …») | Rotta → tool MCP | Fonte nel core | Stato |
|---|---|---|---|
| Stato del processo e modalità | `/v1/status` → `get_status`: `runtime_state`, `execution_mode`, `live_enabled`, `readiness` | RuntimeController | pronto |
| Kill switch, emergenza, stop di rischio | `/v1/status` → `stop` (`kill_switch_active`, `emergency_stopped`, `risk_stop_reason`, `daily_loss_pending_stop`), `protections` | runtime, risk_stop, daily_loss | pronto |
| Quanti tavoli aperti | `/v1/exposure` → `get_exposure.tables[]` (`status`, `occupied`, `in_recovery`, `loss_amount`) | TableManager | pronto |
| Posizioni | `/v1/positions` → `list_positions` | ledger | pronto |
| Saldo e capitale disponibile e impegnato | `/v1/account` → `get_account` (`bankroll`, `exchange_funds`, `cash`) | risk_desk, lettura dei fondi | pronto |
| Esposizione complessiva | `/v1/exposure` → `total_exposure`, per tavolo `current_exposure` | TableManager | pronto |
| Ordini, compresi AMBIGUOUS | `/v1/orders` → `list_orders` | orders, order_saga | pronto |
| Riconciliazione | `/v1/reconciliation/status` | state_recovery, riconciliazione | pronto |
| Diagnostica e componenti | `/v1/status` → `engine` (diagnostica), `readiness.blockers` | runtime | pronto |
| Configurazione (strategia Roserpina, limiti) | `/v1/config` → `get_config`, con redazione e chiavi in whitelist | settings | pronto |
| Mercati e book (età del book) | `/v1/markets`, `/v1/markets/{id}/book` | MarketTracker | pronto; l'età del book dipende da `ea81e93` (D) |
| **Segnali e strategie attive** | — | coda dei segnali, strategia attiva | **LACUNA**: nessuna rotta né tool. Da progettare con B (§3, passo B3) |
| Storia (cosa è successo) | `/v1/blackbox/*` | scatola nera | pronto, dopo il merge della #617; storia finanziaria solo con BB-3 |

Una funzione che il core su main non ha ancora non viene mai inventata: la vista la dichiara. Esempi: `NOT_IN_CORE`
per il trailing, `UNAVAILABLE CORE_PENDING_F04` per le chiusure SL/TP, `unavailable` per un campo. È già nel
contratto: così il ponte minimo è onesto anche senza le funzioni di D.

## 2. Sicurezza (già nel codice, da riverificare a ogni passo)

- **Rete:** bind solo su 127.0.0.1 e controllo dell'header `Host`. Nessuna porta pubblica, nessun proxy. Il server MCP
  è stdio e gira sulla stessa macchina. L'accesso remoto dei client (ChatGPT, Claude, Grok) è **fuori dalla Fase 1** e
  richiede una decisione separata.
- **Autenticazione:** token generato all'avvio, file 0600, proprietario verificato, rotazione, confronto a tempo
  costante.
- **Autorizzazione:** principal e scope MCP (già su main, MCP-01c). Un tool di comando risponde FORBIDDEN prima di
  chiamare la Control API.
- **Sola lettura:** solo GET; i comandi (`POST /v1/orders`, `stop`, `cashout`, …) sono catalogati e rifiutati con 405.
  Nessun `place_order` esposto.
- **Dati:**
  - `source` distingue `core` da `simulated`; `consistency` dice come è stata fatta la lettura;
  - `unavailable` e `not_reported` dichiarano ciò che manca, mai lo riempiono con uno zero;
  - gli errori hanno un codice fisso e non ripetono mai l'input.
- **Segreti:** redazione di chiavi e valori sensibili; `customer_ref` e `order_ref` non escono mai (verificato in
  MCP-SEC-01 e sulla scatola nera).
- **Fail-closed:** timeout, risposta che non rispetta il contratto → errore, versione del contratto diversa → rifiuto.
  Ogni lettura viene registrata nella scatola nera, e con il registro guasto la Control API risponde 503.

## 3. Passi, dipendenze, test e criteri di accettazione

Regola: **una PR attiva per repository.** Nel core la #617 ha la precedenza. Nel repository MCP la PR C1 può partire
in parallelo, se l'owner dà il GO.

| Passo | Chi | Dipende da | Contenuto | Test | Accettazione |
|---|---|---|---|---|---|
| **C1** | C | GO owner (repository MCP) | Una PR nel repository MCP che porta su main la catena 01d…01r (Control API, contratto 1.15.0, tool di lettura, client HTTP, lettura della scatola nera, patch BB-1 `75e7280`) | suite completa (oggi 2228 passed); contract test (72); mutanti critici (241/241 sul codice finale, più R26–R28); controllo dello schema; guard di scope | gate di merge MCP; nessun tool di comando registrato; hash del contratto fissato |
| **B1** | B | merge della #617 | **PF-API-1 ponte minimo** sul main del core: `control_api/{bridge,views,launcher}` dagli handoff, ribasato su main e senza i commit di D. Le viste che dipendono da F-02/03/04/13/18 o dall'età del book restano dichiarate assenti. Launcher **disattivato di default** (opt-in esplicito), solo loopback | test del ponte nel core; `tests/crossrepo` del repository MCP contro il core di main (SIM); hook della scatola nera (BB-1) collegato al `BlackBoxReader` del runtime, scope RUNTIME | gate del core; E2E in SIM: le domande del §1 ricevono risposte dal runtime reale (`source=core`); 0 rotte di comando servite |
| **J1** | B + C | B1, C1 | Fissare la versione del contratto: il core dichiara 1.15.0 e l'hash in `/v1/meta`, l'MCP rifiuta qualunque altra versione | test di handshake (versione e hash errati → rifiuto) | handshake verde nei due repository |
| **D1** | D | B1 | Oracolo indipendente: lo stato reale letto via MCP coincide con il runtime (bankroll, esposizione, tavoli, ordini) | scenari della campagna Grok in SIM | nessuna divergenza non dichiarata |
| **B2** | B | merge delle PR di D (F-02/03/04/13/18, età del book) | Attivare le viste corrispondenti nel ponte (dagli handoff esistenti) | test degli handoff 4–13 | viste da `NOT_IN_CORE`/`UNAVAILABLE` a dati reali |
| **B3/C2** | B + C | J1 | **Lacuna «segnali e strategie attive»**: progettare una rotta di sola lettura (coda dei segnali, strategia per tavolo, ultimo segnale accettato o rifiutato con `reason_code`). È un'estensione del contratto (1.16.0) | RED/GREEN, controllo dello schema, redazione del testo del segnale | contratto concordato B/C, autorizzato dall'owner |

Fuori dalla Fase 1:
- qualunque comando;
- accesso remoto e trasporto MCP non stdio;
- deploy sulla VPS;
- estensioni G4/G6 (picco e drawdown di cassa, importi Decimal);
- BB-3.

## 4. Coordinamento (senza nuova infrastruttura: vale il congelamento)

- **Contratto:** `contract_v1.json` più il descrittore MCP, con versione e hash. Una modifica passa da un aumento di
  versione nei due repository.
- **Comunicazione:** PF-AGENT-BRIDGE (`send_message`) per lo scambio puntuale; #586 (core) e #37 (MCP) come registro
  persistente; checkpoint `pfckpt` per lo stato di ciascun agente.
- **Consegne di dati:** solo file identificati da sha256, oppure branch. Mai JSON incollato (lezione delle fixture BB-1).

## 5. Decisioni richieste all'owner

1. **GO C1:** PR nel repository MCP che porta su main la Control API e i tool di lettura. Il codice resta congelato
   finché il GO non arriva.
2. **Ordine nel core:** ponte minimo B1 subito dopo la #617, con le funzioni di D dichiarate assenti. Oppure attendere
   le PR di D e integrare tutto insieme. Raccomando B1 minimo: dà subito le domande del §1 sui dati reali.
3. **Ambito B3/C2:** segnali e strategie, cioè cosa mostrare e con quale redazione.
4. **Più avanti:** modello di accesso dei client remoti (non nella Fase 1).

Nessun ordine reale, LIVE OFF, certificazione OFF, nessun deploy, nessuna porta pubblica, nessuna modifica alla #617,
nessun merge automatico.
