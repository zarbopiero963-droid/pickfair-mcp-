# Handoff a Claude B — ponte Control API di sola lettura in Pickfair-nogui

Da: Claude C (MCP + Control API) · Per: Claude B (proprietario del core) · 04/11/2026
Direttiva owner «AUTONOMIA PERMANENTE MCP + CONTROL API»: Claude C non modifica Pickfair-nogui;
ogni componente che tocca `RuntimeController`, `EventBus`, broker o moduli interni è consegnato
come patch proposta. **Claude B decide se, quando e come integrarla**, secondo la governance del core.

## 1. Cosa consegno

| File | Contenuto |
|---|---|
| `core_bridge.patch` | patch `git apply` contro Pickfair-nogui `main` **`ada40765e7949b8deb7661b3b5e9ddc8484adba3`** (14 file, +1485/−1). **Non è pubblicata in questo repository**: il codice di Pickfair-nogui resta fuori da pickfair-mcp-; la patch è consegnata come file e se ne verifica l'integrità con `core_bridge.patch.sha256` (in questa cartella) |
| questo documento | contratto, prove, governance, decisioni aperte |

Verifiche sulla patch, tutte su una copia esportata del `main` con la patch applicata:
- `git apply --check` pulito sul `main` indicato;
- `scripts/guardrail_check.py`: scope = diff (14 file), registro toccato solo nella voce del task;
- regressione completa del core con Python 3.11 (vedi §5).

Integrità: `sha256sum -c core_bridge.patch.sha256` nella cartella in cui si trova la patch.

Riferimento storico: il commit `46e5bac2` sul branch `ccr-edf04c7d-e7vtj1` di Pickfair-nogui
conteneva una prima versione con il server dentro il core. È **superato** da questa patch (il server
ora vive in `pickfair_control_api`) e resta solo come riferimento; non va mergiato.

## 2. Architettura (separazione dei repository)

```
pickfair-mcp-  (Claude C)                         Pickfair-nogui  (Claude B)
───────────────────────────                        ─────────────────────────────
pickfair_mcp  ── adapter HTTP ──► pickfair_control_api ◄── control_api/bridge.py
  (MCP server)    127.0.0.1         (server, token,          control_api/views.py ──► RuntimeController
                  Bearer            contratto, self-check)   control_api/launcher.py ◄── headless_main.py
```

- `pickfair_control_api`: solo libreria standard, non importa nulla di Pickfair. Riceve due
  *provider* di lettura e valida ogni risposta contro lo schema del contratto prima di inviarla.
- Il ponte del core è l'unico codice che legge il runtime. Nessun comando, nessuna scrittura.

## 3. Contenuto della patch

| File | Modifica |
|---|---|
| `control_api/views.py` | letture pure con controllo di tipo; campo assente ⇒ `null` + `unavailable`; motivi ⇒ token MAIUSCOLI; **mai** `get_status()` |
| `control_api/bridge.py` | provider + avvio del server con token nuovo (`publish_fresh_token`) |
| `control_api/launcher.py` | avvio opzionale, **disattivato per impostazione predefinita**; fail-closed sulla sola API |
| `headless_main.py` | +16 righe: avvio dopo `runtime.start()` riuscito, arresto per primo in `stop()` |
| `tests/control_api/*` | 4 file: viste su runtime reale, assenza di effetti su runtime SIM avviato, launcher e processo `headless_main` reale |
| `guardrails/mutation_catalog.json` | area opzionale nuova `control_api`, 12 mutazioni |
| `scripts/ci_changed_modules.py` | `control_api/` sulla lane `mutation-guardrails` |
| `docs/control_api.md`, `CHANGELOG.md`, `.guardrails/allowed_scope.json` | documentazione e scope (`pf_api1_control_api_bridge`) |

## 4. Contratto

Contratto Control API **1.1.0**, schema hash `e9471531792d74337f03a3014e84364994fe76b25e28c6fab4b5ea117df9d4b6`
(descrittore canonico in pickfair-mcp-: `src/pickfair_control_api/contract_v1.json`, identico a
`src/pickfair_mcp/contract/descriptor_v1.json`). Copre route, schemi delle risposte, input/output dei
tool, codici d'errore e semantica (`unavailable`, codici, `consistency`, freschezza).

## 5. Prove eseguite (copia esportata del core + patch, Python 3.11)

| Prova | Esito |
|---|---|
| Regressione completa del core con la patch | vedere il rapporto di consegna (SHA e conteggi) |
| `tests/control_api/` (viste, effetti, launcher, processo reale) | PASS |
| Mutazioni area `control_api` (`run_mutation_guardrails.py`) | 12/12 KILLED, GATE PASS |
| E2E fra processi (MCP reale ⇄ Control API ⇄ RuntimeController in SIM) | 7/7 PASS, stabile su 3 esecuzioni |
| Sabotaggi (vista che chiama `get_status()` o il broker) | rilevati |

Prove di assenza di effetti su runtime **avviato in SIM** (SimulationBroker, riconciliazione d'avvio):
DB (hash dei file), bus (eventi), saldo SIM, chiamate a servizio Betfair e broker (solo `status()` e
`get_client()` ammessi, letti nel codice: stato locale), monitor di rischio, stato profondo di runtime,
risk desk, tavoli, dedupe, MM, riconciliazione: tutto invariato dopo 50 letture dirette e 100 HTTP.
Le letture non attendono i lock di ammissione e dei tavoli; il caso peggiore di un'operazione del
runtime sotto letture continue resta sotto 50 ms.

## 6. Osservazioni sul core (nessuna modifica fatta: decide Claude B)

1. `RuntimeController.get_status()` non è una lettura: legge i fondi Betfair, aggiorna lo stato della
   cassa e fa girare il monitor della perdita giornaliera. Il ponte non lo usa; valutare se rinominarlo
   o documentarlo.
2. `_recovery_persist_failed` esiste solo dopo la prima scrittura dello stato di recovery, quindi
   `recovery_state` resta indisponibile dopo un avvio pulito. Proposta: inizializzarlo a `False` nel
   costruttore, se coerente con la semantica di RSR-12.
3. All'avvio in SIM il runtime chiama una volta `SimulationBroker.list_events` (sync del catalogo in
   background): normale, documentato perché le prove di assenza di effetti misurano le chiamate nuove.
4. `is_emergency_stopped` è una property, non un metodo: utile saperlo per chi scrive strumenti.

## 7. Decisioni aperte (owner / Claude B)

- **Dipendenza dal package `pickfair_control_api`.** Opzioni: (a) installarlo da pickfair-mcp- a SHA
  fissato (nuova voce nei requirements del core: manifest di dipendenze ⇒ merge owner);
  (b) copiarlo nel core con un test che ne verifica l'hash rispetto al repository MCP.
  Senza il package, il ponte non parte (`PACKAGE_MISSING`) e Pickfair funziona identico.
- **Packaging**: `control_api/` non è in `pyproject.toml`/`pickfair.spec`; serve anche `BUILD_SHA`
  scritto dal packaging, altrimenti la Control API rifiuta di partire (`GIT_SHA_UNRESOLVABLE`).
- **Merge**: la patch tocca `headless_main.py` (runtime): per la governance del core è codice di
  prodotto finanziario critico ⇒ certificazione rafforzata o merge owner (§0.9-bis).
- **D-11 definitivo**: oggi token bearer locale in file 0600, nuovo a ogni avvio. Miglioramenti senza
  nuovi servizi: socket Unix con `SO_PEERCRED`; token per sessione MCP.

## 8. Come applicare e verificare

```bash
git checkout -b <branch> origin/main          # main = ada40765 o successivo
git apply --check core_bridge.patch && git apply core_bridge.patch
pip install -e <checkout di pickfair-mcp->    # oppure l'opzione scelta al §7
python -m pytest -q tests/control_api
python scripts/run_mutation_guardrails.py --module control_api.views --module control_api.launcher --fail-under 100
# E2E dal repository MCP:
PICKFAIR_CORE_PATH=<checkout core> PICKFAIR_CORE_PYTHON=<python del core> python -m pytest -q tests/crossrepo
```
