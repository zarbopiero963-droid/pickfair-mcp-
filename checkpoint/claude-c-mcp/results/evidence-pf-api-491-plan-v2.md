## Piano #491 aggiornato — Control API contratto 1.16.0 (decisione owner PF-CONTROL-API — CONTRACT 1.16.0)

Claude C, 10/11/2026. Sostituisce il piano e la sequenza di c.6754243364 e la §5 di c.6754421452. Restano validi l'inventario, la matrice e l'appendice (c.6754305583). Approvazione architetturale: nessun codice, nessuna PR, nessun merge, nessun deploy.

### Decisioni registrate

| # | Decisione owner | Effetto sul piano |
|---|---|---|
| D01 | Rate limiting configurabile, nel repository MCP, prima dell'importazione | contratto **1.16.0**; l'hash va ricalcolato dai file effettivi dopo l'implementazione. Non si riusa `81a81884…` della 1.15.0 |
| D02 | Scatola nera obbligatoria: senza `request_hook` o con provider mancanti l'avvio è rifiutato; nessun interruttore per singole rotte BB-1 | **nessuna modifica**: è il comportamento attuale (`REQUEST_HOOK_REQUIRED`, `PROVIDERS_INVALID`). Con registro degradato vale già il fail-closed (503 `BLACKBOX_UNAVAILABLE`, tranne `/v1/blackbox/status` e `/v1/meta`). `NOT_IMPLEMENTED` (501) resta riservato alle rotte davvero opzionali (`/v1/events`, `/v1/operations*`, `/v1/audit`) |
| D03 | Il repository MCP è la fonte autorevole; copia versionata con manifest e SHA-256; importazione iniziale direttamente a 1.16.0; solo da commit su main MCP; verifica offline | procedura di c.6754421452 §1–§4, con `contract_version` 1.16.0 |
| D04 | Sequenza: #617 → PR Roserpina → contratto MCP 1.16.0 → PF-API-0 e PF-API-1 → E2E in SIM → (VPS, decisione separata) | vedi la sequenza sotto |

### Progetto del rate limiter (pacchetto `pickfair_control_api`, solo libreria standard)

- **Dove:** nel server della Control API. Si applica **dopo** l'autenticazione e **prima** di qualsiasi provider. La richiesta rifiutata non tocca il runtime.
  - Le richieste non autenticate restano rifiutate prima (401) e già limitate dal tetto di connessioni.
  - Il thread del bot non è mai coinvolto.
- **Algoritmo:** token bucket per token Bearer.
  - Controllo e scalata del gettone avvengono in **un'unica operazione sotto lo stesso `threading.Lock`**: due richieste simultanee non possono consumare lo stesso gettone.
  - Orologio monotono, iniettabile nei test.
- **Configurazione:** argomenti del launcher del core, per esempio `--control-api-rate-per-s` e `--control-api-burst`.
  - Valori iniziali conservativi proposti: **2 richieste/s, raffica 5**.
  - Limiti ammessi validati all'avvio (per esempio 0,1–20/s, raffica 1–50). Un valore fuori limite rifiuta l'avvio (fail-closed): mai un limite «infinito».
- **Risposta:** `429 RATE_LIMITED`, corpo di errore fisso del contratto, header `Retry-After` in secondi interi.
  - Nessun testo dell'input, nessun token nei log: si registra solo il codice.
- **Audit:** la richiesta rifiutata è registrata nella scatola nera come RESULT `RATE_LIMITED` (come ogni rifiuto). In caso di inondazione vale l'aggregazione già esistente (20 record/s, raffica 40, `coalesced_before`): nessun sovraccarico del registro.
- **Lato MCP:** l'adapter HTTP mappa 429 su un errore `RATE_LIMITED` con `retryable=true`. **Nessun nuovo tentativo automatico**: il client decide.
- **Contratto 1.16.0:**
  - `RATE_LIMITED` entra nell'enum dei codici d'errore e nella mappa degli status;
  - aumento della versione in MCP e nel pacchetto;
  - descrittore rigenerato due volte;
  - nuovo `GOLDEN_SCHEMA_HASH` ricalcolato dai file e pubblicato **completo**, così B lo ricalcola in modo indipendente.

### Test obbligatori del rate limiter (RED prima, poi GREEN)

1. **Race:** N thread (per esempio 64) sincronizzati con una `threading.Barrier` partono insieme con raffica B. Successi **esattamente B**, gli altri 429, ripetuto 200 volte; nessuna esecuzione supera B. Variante con orologio iniettato fermo, per escludere il ricarico durante la prova.
2. **Saturazione:** oltre il limite, ogni richiesta è 429 e **nessun provider viene chiamato** (contatore dei provider invariato).
3. **Recupero:** dopo il tempo di ricarico (orologio avanzato) le richieste tornano 200, nella misura del ricarico, senza riaccumulo oltre la raffica.
4. **Isolamento:** i test esistenti di non interferenza col runtime SIM (letture senza effetti, nessuna attesa sui lock, latenza limitata) **sotto saturazione**: il ciclo del bot non rallenta.
5. **Audit:** sotto inondazione i RESULT `RATE_LIMITED` sono aggregati (`coalesced_before`). Con registro degradato vale ancora 503 `BLACKBOX_UNAVAILABLE`.
6. **Configurazione:** valori fuori limite o non numerici → avvio rifiutato.
7. **Segreti:** nessun token nei log o nelle risposte di 429.
8. **Mutanti critici** sul limiter (gettone non scalato, controllo fuori dal lock, ricarico oltre la raffica, provider chiamato prima del controllo): tutti KILLED.

### Sequenza (una PR attiva per repository)

1. **#617**: merge sicuro e gate BB-1.
2. **PR Roserpina** già pianificata.
3. **Repository MCP (C), al GO dello sviluppo:**
   - una sola PR con la catena `36bbef1..75e7280` più il rate limiter e il contratto **1.16.0**;
   - accettazione: suite, test del limiter (sopra), campagna completa dei mutanti, hash completo pubblicato.
4. **PF-API-0 / PF-API-1 (B, core):**
   - importazione della copia **1.16.0** (manifest, SHA-256, test d'integrità offline);
   - ponte dagli handoff 1–13 (solo `control_api/`, senza l'hunk di `cashout_router.py`);
   - `EXPECTED_CONTROL_API_VERSION = "1.16.0"`;
   - provider della scatola nera e `request_hook` sul `BlackBoxReader` del runtime;
   - argomenti del rate limiter nel launcher;
   - test dipendenti da D condizionati o spostati nelle loro PR.
5. **E2E in SIM**, crossrepo, MCP 1.16.0 ↔ core:
   - le domande dell'owner rispondono dal runtime reale (`source=core`, `observed_at`, freschezza);
   - le 4 rotte della scatola nera sono servite e verificate;
   - rate limiting verificato tra processi;
   - verifica indipendente di D.
6. **VPS:** decisione separata.

### Verifiche preliminari (D-owner)

- **B:** ricalcola l'hash completo 1.16.0 e verifica ogni simbolo del ponte sul main dopo #617 e Roserpina.
- **C:** procedura di aggiornamento già pubblicata (c.6754421452), aggiornata alla 1.16.0. Compatibilità con main dopo #617 e Roserpina: da riconfermare sullo SHA reale.

Nessun codice, nessuna PR, nessun deploy. LIVE OFF, certificazione OFF.
