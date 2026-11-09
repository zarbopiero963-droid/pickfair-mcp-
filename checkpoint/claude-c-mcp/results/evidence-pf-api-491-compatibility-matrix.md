## PF-API-0 / PF-API-1 — inventario di Claude C e matrice di compatibilità (#491)

Direttive owner «PICKFAIR MCP / CONTROL API INTEGRATION — GO inventario» e «OWNER DECISION — PF-API-0 / PF-API-1».

- **Metodo:** solo lettura e prove in copie di lavoro locali. Nessun commit, nessun cherry-pick, nessun push, nessuna PR.
- **Basi:**
  - core `main` `6519794b`; PR #617 @ `8bfb96d3`;
  - MCP `main` `36bbef1e`; branch MCP fino a `75e7280`;
  - handoff `handoff/claude-c/mcp-core-20261105` @ `0a529035`.

### 1. Risposta alla domanda dell'owner: il lavoro si recupera senza rifarlo?

**Sì, per la parte read-only.** Ho applicato il ponte al **main di oggi** in una copia di lavoro, escludendo solo 3 file di registro, e ho eseguito:

- **Test del ponte nel core:** 211 PASS. Gli unici fallimenti, 6 FAIL e 7+2 ERROR, sono tutti in viste che usano funzioni di D non su main (F-18, F-03, F-04, età del book).
- **End-to-end tra processi reali** (core SIM avviato → Control API → server MCP via stdio): **14/17 PASS**. I 3 FAIL sono le stesse funzioni di D. Passano:
  - avvio, riconciliazione, emergency stop;
  - letture senza effetti sul core;
  - token invalido; principal non autorizzato fermato prima del core;
  - core giù, riavvio, timeout, versione incompatibile, snapshot stale;
  - nessun segreto esposto;
  - account ed esposizione, diagnostica e protezioni, posizioni, ordini dal ledger, AMBIGUOUS senza importi non confermati;
  - SL/TP, settlement e barriere del cashout;
  - mercati e book dal tracker reale.

I circa 40 commit di B e D **non servono** al funzionamento read-only. Servono solo ad attivare 3–4 viste, che senza di loro restano dichiarate assenti (`NOT_IN_CORE`, `UNAVAILABLE`), mai inventate.

### 2. Repository pickfair-mcp- (Control API + MCP)

| Elemento | SHA | Stato |
|---|---|---|
| `main` | `36bbef1` | `get_meta` + catalogo; MCP-01b (#33) e MCP-01c principal/scope (#36) già mergiati |
| Catena di integrazione | `36bbef1..75e7280` | **68 commit lineari**, `git merge-tree` con main **senza conflitti** |
| Incrementi nella catena (contratto) | `fcde366`, `6c75737` (01e), `3695da2` (01f), `181dd0e` (01g), `8f112f7` (01h), `305b843` (01j), `4cd3e75` (01k), `00978ef` (01l), `9958c75` (01m, 1.11.0), `f1b4b64` (01n, 1.12.0), `6580f91` (01o, 1.13.0), `869d2c0` (01p/q, 1.15.0), `75e7280` (patch BB-1) | pronti; suite 2228 passed; mutanti critici 241/241 KILLED (`540a932`) più R26–R28 |
| Fuori catena, solo documenti o superati | `eda3a95` (evidenze SEC-01), `06e9eda` (evidenze 01i-r2), `82514f3`/`3b25f96` (01i, superato da r2), `06a90c8` (PR di prova) | non da integrare |
| Fuori catena, **specifica utile** | `bad873b` K3: RC-10 **segnali**, RC-11 P&L, RC-12 (offline, non ratificate) | base per la lacuna «segnali e strategie» (§5) |

### 3. Repository Pickfair-nogui: i 13 handoff del ponte

| # | Base → handoff | Contenuto | Contratto | Dipende da D/B? | Su main di oggi |
|---|---|---|---|---|---|
| 1–9 | `ada40765` (**su main**) → `ae17bb8` … `4525b28` | `control_api/{bridge,views,launcher}`, `docs/control_api.md`, 13 file di test; launcher in `headless_main` (opt-in, spento) | 1.9.0 | **No**: 16 commit, tutti di Claude C | si applica: conflitti **solo** in `.guardrails/allowed_scope.json`, `CHANGELOG.md`, `guardrails/mutation_catalog.json`; con #617 @ `8bfb96d3` stessi 3 file, `headless_main.py` si fonde da solo |
| 10 | `772ab58` → `044af41` | vista chiusure SL/TP | 1.10.0 | F-04 (D) | codice applicato; test da F-04 |
| 11 | `a0a6013` → `0dca9d5` | vista trailing, F-02, F-18 | 1.11.0 | F-03, F-02, F-18 (D/B) | codice applicato; **escludere** l'hunk di `cashout_router.py`, che è la deduplica di una fusione di D, non codice del ponte |
| 12 | `2ea5187` → `f22d6bf` | età del book | 1.12.0 | `ea81e93` (D) | codice applicato; test da `ea81e93` |
| 13 | `f22d6bf` → `0a52903` | test compatibili con F-16 | 1.12.0 | — | applicato |

Commit di B e D sotto gli handoff 10–12 (non su main):
- F-04: `adf4271`, `7fae475`, `772ab58`, `aa7959a`, `4c07f71`, `2d0cf4c`;
- F-03: `e626057`, `c12ef15`;
- F-02: `80b0090`;
- F-18: `b52c871`, `94f52e1`;
- F-13a/b: `b6e82d2`, `e8015b3`, `9200468`, `b79c7cb`, `4c265c5`, `4049b5c`;
- età del book: `ea81e93`;
- fusioni locali: `65a84f5`, `cfcbf21`.

Lo stato delle loro PR va inventariato da B.

### 4. Matrice di compatibilità con i requisiti di #491

| Requisito (owner / piano B) | Codice esistente | Esito |
|---|---|---|
| Server nel processo Pickfair | `control_api/launcher.py` avviato da `headless_main` | **OK** |
| Solo loopback | `127.0.0.1` fisso (non configurabile) + controllo dell'header `Host` | **OK** |
| Spento di default | opt-in con `--control-api-port` e `--control-api-token-file` | **OK** |
| Token CSPRNG in file privato (D02) | `secrets.token_urlsafe`, file `O_EXCL\|O_NOFOLLOW` 0600, proprietario verificato, rotazione, confronto a tempo costante | **OK**; da allineare alla regola della cartella privata del ciclo 13 di #617 (riusare, non duplicare) |
| Libreria standard (D03) | `http.server.ThreadingHTTPServer`, nessuna dipendenza | **OK** |
| Sola lettura | solo GET; ogni altro metodo → 405; rotte non servite → 501; 11 comandi solo catalogati | **OK** |
| Snapshot senza I/O verso Betfair; vietato `get_status()` | `views.py` vieta esplicitamente `get_status`, `pending_exposure`, `read_funds_*` e lo snapshot del broker; Betfair solo da `keepalive_status()` in memoria; `test_side_effects.py` (letture senza effetti, senza attese sui lock, latenza limitata) **PASS su main** | **OK** |
| Provenienza dei dati | `source` (`core`/`simulated`) + `execution_mode` (`SIM`/`LIVE`) + `unavailable` per campo | **OK**. Nomi diversi dalla proposta B (`REAL/SIMULATED/UNAVAILABLE`): propongo di tenere quelli esistenti (contratto in pickfair-mcp- #1) |
| Freschezza | `observed_at` a ogni lettura; `exchange_funds.age_s` e `ok/reason` con `funds_max_age_s()` del core; snapshot `STALE` con motivo | **OK** |
| Audit nella scatola nera + fail-closed | `request_hook` (ATTEMPT/RESULT, aggregazione 20/s) e 503 `BLACKBOX_UNAVAILABLE` nel package; verificati sulla classe reale BB-1 (#617) 17/18 | **MANCA il collegamento nel core** al `BlackBoxReader` del runtime (piccolo: `make_providers` + `make_request_hook`), dopo #617 |
| Nessuna interferenza con trading, STOP, recovery | letture senza lock bloccanti (`LOCK_WAIT_S`), test di latenza e di non rallentamento **PASS** | **OK** |
| Nessuna credenziale | redazione; MCP-SEC-01; E2E `no_secret_leaks` **PASS** | **OK** |
| Limiti | `MAX_RESPONSE_BYTES` 64 KiB, connessioni limitate, timeout per richiesta e per connessione (slowloris) | **OK** |
| Errore `RATE_LIMITED` per richiesta (proposta B) | non c'è un 429; esistono il limite di connessioni e l'aggregazione dell'audit | **MANCA**, se l'owner lo vuole |
| `/v1/safety` (proposta B) | coperto da `/v1/status` → `stop` e `protections` | coperto, rotta diversa |
| `/v1/tables` (proposta B) | coperto da `/v1/exposure` → `tables[]` | coperto, rotta diversa |
| Segnali e strategie attive | nessuna rotta; nel core nessun read model (B) | **MANCA**; specifica offline RC-10 in `bad873b`, da ratificare |
| Legacy `betfair_market_api.py` (D04) | non usata dal ponte | ritiro: B |

### 5. Cosa manca davvero (elenco chiuso)

1. **Core, PF-API-0:** portare su main gli handoff 1–9 (ponte 1.9.0). Unico lavoro manuale: risolvere i 3 file di registro.
2. **Core, PF-API-1:**
   - parti `control_api/` degli handoff 10–13, senza l'hunk di `cashout_router.py`;
   - collegamento della scatola nera al reader del runtime;
   - pin del contratto a **1.15.0**, uguale all'MCP. L'MCP rifiuta qualunque altra versione: oggi il ponte dichiara 1.12.0.
3. **Test dipendenti da D:**
   - i test degli handoff 10–12 (6 FAIL, 7+2 ERROR) e i 3 E2E (config F-18, chiusure F-04, trailing F-03) vanno condizionati alla presenza della funzione, oppure spostati nelle PR di D;
   - le viste invece restano: degradano già correttamente.
4. **Packaging (decisione owner, manifest a merge owner):** come entra `pickfair_control_api` nel bot (dipendenza installata con versione e hash, oppure copia versionata).
5. **Repository MCP:** una sola PR che porta la catena `36bbef1..75e7280` su main. Senza conflitti; serve il GO owner.
6. **Facoltativi o da decidere:** `RATE_LIMITED`; rotta e read model di segnali e strategie (B3/C2, partendo da RC-10).

### 6. Sequenza minima (una PR attiva per repository)

1. #617 → merge sicuro (priorità).
2. PR Roserpina in coda (D01).
3. **PF-API-0 (B, core):** handoff 1–9 su main. Accettazione:
   - `tests/control_api` verdi;
   - E2E crossrepo con l'MCP alla 1.9.0;
   - zero rotte di comando.
4. **PF-API-1 (B, core):** handoff 10–13 (solo `control_api/`), collegamento della scatola nera, pin 1.15.0, test di D condizionati.
5. **Integrazione MCP (C, repository MCP):** la PR della catena, che può essere preparata in parallelo perché è un altro repository, ma va mergiata quando il core dichiara 1.15.0. Accettazione:
   - E2E crossrepo a 1.15.0 sul main del core in SIM: le domande dell'owner (stato, tavoli, capitale, esposizione, kill switch) rispondono con `source=core`, `observed_at` e freschezza;
   - verifica indipendente di D.
6. Le viste F-02/03/04/18 e l'età del book si attivano da sole quando le PR di D arrivano su main.

**Riproduzione delle prove di questo inventario** (copia di lavoro, nessun commit):
- `git worktree add <core> 6519794b`;
- `git apply --3way` dei diff `ada40765..4525b28c`, `772ab581..044af41d`, `a0a60137..0dca9d58` (senza `cashout_router.py`), `2ea5187a..f22d6bfb`, `f22d6bfb..0a529035`, escludendo i 3 file di registro;
- `pytest tests/control_api` con `PYTHONPATH=<core>:<mcp f1b4b64>/src`;
- E2E: in pickfair-mcp- @ `f1b4b64`, `PICKFAIR_CORE_PATH=<core> PICKFAIR_CORE_PYTHON=python3 pytest tests/crossrepo`.

Nota d'ambiente: nel container un pacchetto `tests` di site-packages oscura `tests/` del core. Nella sola copia ho aggiunto un `__init__.py` vuoto e installato `betfairlightweight`. Non è un difetto del codice.

Nessun commit, nessuna PR, nessun deploy, nessuna porta nuova. LIVE OFF, certificazione OFF.
