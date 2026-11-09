## Control API: procedura di importazione e aggiornamento della copia versionata (decisione owner #491, packaging)

Claude C, 10/11/2026. Questa è solo una procedura: nessun codice scritto, nessuna PR.

### 1. Sorgente unica

- **Unica implementazione autorevole:** `pickfair-mcp-` → `src/pickfair_control_api/`. Comprende server, token, contratto, controllo degli schemi, lettura e redazione della scatola nera.
- **Nel core** vive solo la copia importata, in sola lettura (`vendor/pickfair_control_api/`), più il ponte `control_api/{bridge,views,launcher}.py`, che è codice del core.
- **Regola:** nessuna modifica si fa nella copia del core. Ogni cambiamento passa da una PR nel repository MCP, poi si fa una nuova importazione. Una PR del core che tocca `vendor/` deve contenere **solo** la reimportazione e il manifest.

### 2. Manifest della copia (`vendor/pickfair_control_api/VENDOR_MANIFEST.json`)

```json
{
  "package": "pickfair_control_api",
  "source_repo": "zarbopiero963-droid/pickfair-mcp-",
  "source_commit": "<SHA completo, 40 hex, di un commit raggiungibile da main MCP>",
  "contract_name": "pickfair-control-api",
  "contract_version": "1.15.0",
  "schema_hash": "<sha256 completo, 64 hex>",
  "files": {"__init__.py": "<sha256>", "server.py": "<sha256>", "...": "..."},
  "import_command": "<comando esatto dello script di importazione, §4>"
}
```

- **Valore di partenza** (catena MCP `75e7280`, contratto 1.15.0):
  `schema_hash = 81a81884c80c3bb269ce20d214f5e064d66159336a6063b7c9922436ed245bed`.
  B lo ricalcola in modo indipendente prima del gate.
- **Algoritmo:** `sha256(json.dumps(contract_v1.json, sort_keys=True, separators=(",",":"), ensure_ascii=True))`.

### 3. Test di integrità nel core (obbligatorio, solo libreria standard)

1. Ogni file elencato esiste e il suo sha256 è uguale al manifest.
2. Nella cartella non ci sono **file non elencati**, né link simbolici o `__pycache__` tracciati: una modifica locale o un file aggiunto viene rilevato.
3. `schema_hash` ricalcolato da `contract_v1.json` è uguale al manifest **e** uguale al valore fissato nel test per la versione attesa: un cambio di contratto non passa in silenzio.
4. `CONTRACT_VERSION` del pacchetto è uguale a `contract_version` del manifest ed è uguale a `EXPECTED_CONTROL_API_VERSION` del ponte.
5. Le viste del ponte, su un runtime SIM, producono risposte che il controllo degli schemi accetta (`tests/control_api`, già esistenti).
6. **Il test non va in rete:** la raggiungibilità di `source_commit` da main MCP la verificano lo script (§4) e il reviewer, non il test.

### 4. Procedura di aggiornamento (riproducibile)

1. Nel repository MCP la modifica entra su `main` con una PR e i suoi gate. Se il contratto cambia, aumenta la versione e il nuovo hash è nel test golden.
2. Lo script `tools/vendor_control_api.py` (da scrivere al GO, nel core, solo libreria standard):
   1. clona o legge pickfair-mcp- al `source_commit` dato;
   2. **rifiuta** se `source_commit` non è raggiungibile da `origin/main` MCP, o se il working tree non è pulito;
   3. rigenera il descrittore (`python -m pickfair_mcp contract-descriptor`) e **rifiuta** se non è identico byte per byte a `contract_v1.json` del pacchetto;
   4. copia **solo** i file del pacchetto, sostituendo l'intera cartella;
   5. scrive il manifest con gli sha256, la versione e l'hash ricalcolato.
3. Nel core si apre una PR di sola reimportazione:
   - diff limitato a `vendor/`;
   - più l'eventuale `EXPECTED_CONTROL_API_VERSION` del ponte e il valore atteso nel test di integrità.
4. Prima del merge:
   - test di integrità;
   - `tests/control_api`;
   - E2E crossrepo in SIM: l'MCP alla stessa versione e allo stesso hash, letti da `/v1/meta`.

### 5. Conseguenze da decidere (owner)

- **Rate limiting configurabile** (decisione owner sì; oggi assente). Va fatto nel pacchetto, cioè nella sorgente unica:
  - per token, con default conservativo, solo libreria standard;
  - risposta 429 `RATE_LIMITED`.

  Aggiungere `RATE_LIMITED` al contratto **cambia l'hash e quindi la versione: 1.16.0**. Due strade:
  - **(a) Raccomandata:** rate limiting nel repository MCP **prima** della prima importazione, poi una sola importazione a 1.16.0 con il suo nuovo hash completo.
  - **(b)** Importare la 1.15.0 e poi reimportare la 1.16.0.
- **Rotte della scatola nera abilitate solo dopo i loro gate.** Il server 1.15.0 è fail-closed: **senza `request_hook` non parte** (`REQUEST_HOOK_REQUIRED`) ed esige tutti i provider, compresi i 4 della scatola nera (`PROVIDERS_INVALID`). Quindi:
  - la Control API 1.15.0 **non può girare prima del merge della #617 (BB-1)**. Dipende solo dalla lettura del registro, mai dal trading;
  - le 4 rotte non si possono accendere separatamente dal resto. Se l'owner vuole un interruttore distinto (rotte della scatola nera a 501 finché i loro gate non sono superati), è una piccola modifica al pacchetto, da fare nella sorgente unica insieme alla (a).
- **Provenienza.** Il contratto esistente usa `source` (`core`/`simulated`) più `execution_mode`, `unavailable`/`not_reported` (NOT_AVAILABLE) e snapshot `STALE` con motivo. I quattro stati REAL/SIMULATED/STALE/NOT_AVAILABLE della decisione sono già rappresentati: non serve uno schema nuovo.

Nessun codice, nessuna PR, nessun deploy. LIVE OFF, certificazione OFF.
