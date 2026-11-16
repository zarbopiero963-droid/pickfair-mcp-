# Matrice d'integrazione delle patch del ponte MCP-01d…01n (per Claude B)

Da: Claude C · Per: Claude B · 05/11/2026 · direttiva owner PF-MCP-CONTINUE-01, punto 4. Solo metadati: il codice
sta sul branch `handoff/claude-c/mcp-core-20261105` di Pickfair-nogui (`f22d6bfb`), pubblicato da B e verificato da C.
B resta responsabile dell'integrazione su `main`, solo tramite PR e gate. C non apre PR.

Prove di questa matrice:
- clone nuovo di Pickfair-nogui da GitHub;
- catena riapplicata su `main` `89af178`;
- fusioni con F-16 (`claude/d-f16-funds-freshness` @ `64e965b`) e F-R06 (`claude/d-g7-r06-settled-ambiguous` @
  `1d8ca01`);
- test del ponte (`tests/control_api`) e test di F-16/F-R06 sullo stack risultante.

## 1. Ordine e dipendenze

| # | Patch | Contratto / pin | Dipende da | Integrabile su `main` oggi |
|---|---|---|---|---|
| 1 | 01d — ponte, launcher, `GET /v1/meta`, `status`, `reconciliation/status` | 1.1.0 | `main` | sì (conflitti solo nei registri, §4) |
| 2 | 01e — `account`, `exposure` | 1.2.0 | 01d | sì |
| 3 | 01f — `engine`, `protections`, `positions` | 1.3.0 | 01e | sì |
| 4 | 01g — `orders` | 1.4.0 | 01f | sì |
| 5 | 01h — SL/TP per tavolo, settlement, barriere cashout | 1.5.0 | 01g | sì |
| 6 | 01j — `config` redatto | 1.6.0 | 01h | sì |
| 7 | 01k — importi AMBIGUOUS non confermati, limite fondi F-16 | 1.7.0 | 01j | sì; con F-16 serve la patch 13 (§3) |
| 8 | 01l — `markets`, `markets/{id}/book` | 1.8.0 | 01k | sì |
| 9 | sec01 — pin al package irrobustito | 1.9.0 | 01l | sì |
| 10 | 01i-r2 — stato della chiusura SL/TP | 1.10.0 | sec01 + **F-04 su main** | **no** |
| 11 | 01m — trailing F-03, F-02, F-18 | 1.11.0 | 01i-r2 + **F-03 su main** (contiene F-02, F-04) | **no** |
| 12 | 01n — età del book | 1.12.0 | 01m + **`claude/d-market-book-age` su main** | **no** |
| 13 | f16-compat — test del ponte validi con e senza F-16 (§3) | invariato | 01n (si applica anche dopo 9) | sì, insieme a F-16 |

**Pin del package.**
- Ogni patch fissa la versione esatta del package `pickfair_control_api` e lo schema hash (`control_api/bridge.py`). Con un package diverso la Control API non parte (`CONTRACT_PIN_MISMATCH`, fail-closed).
- La versione del package (repository pickfair-mcp-) va installata insieme all'ultima patch integrata: 1.9.0 dopo sec01, 1.12.0 dopo 01n.
- La Control API resta **spenta di default**: parte solo con `--control-api-port` e `--control-api-token-file` espliciti (01d, `headless_main.py`), e si ferma per prima al teardown.

## 2. Funzionalità e test richiesti per patch

Per ogni patch:
- `tests/control_api` completo;
- mutazioni `scripts/run_mutation_guardrails.py --module control_api.views --module control_api.bridge --module control_api.launcher --fail-under 100`;
- regressione completa del core.

L'esito di riferimento è nel handoff `docs/handoff/mcp01*.md` di ciascuna patch. Controlli specifici:

| Patch | Comportamento critico da riverificare all'integrazione |
|---|---|
| 01d | nessuna porta senza flag espliciti; solo host loopback; il token mai nei log; stop prima del runtime |
| 01e–01h | letture pure: nessuna scrittura su DB, bus o saldi (`test_side_effects.py`); lock con attesa limitata; valori mancanti `null`, mai zero |
| 01g, 01k | AMBIGUOUS mai FAILED; importi di un report non confermato mai esposti; betId mantenuto |
| 01j | segreti sempre redatti (test negativi di fuga) |
| 01l, 01n | nessuna chiamata di rete; mercato non seguito = NOT_TRACKED; età del book mai sottostimata, `null` se ignota |
| 01i-r2 | solo record persistiti di F-04; hedge legati per id di richiesta |
| 01m | soglia del trailing calcolata da `core.trailing_stop` (nessuna regola replicata) |

## 3. Conflitti e regressioni con i lavori finanziari

| Lavoro di D | File in comune col ponte | Esito della prova | Azione |
|---|---|---|---|
| F-16 (`64e965b`) | `core/runtime_controller.py` (letto, non modificato dal ponte); registri | **3 test del ponte falliscono con F-16 integrato**: `test_funds_limit_on_main_is_the_reservation_ttl`, `test_funds_limit_not_declared_when_f16_threshold_exists_without_accessor`, `test_funds_freshness_follows_the_core_gate`. La vista è corretta: F-16 introduce l'accessore `funds_max_age_s()` (limite 30 s) e nega l'entrata con un istante di lettura ignoto (TRIGGERED, più prudente). I test codificavano il `main` precedente | **patch 13 (f16-compat)**: test validi su entrambe le forme del core. Prova: catena 01n senza F-16 246 passed; catena fino a sec01 + F-16 + F-R06 215 passed |
| F-R06 (`1d8ca01`) | `core/runtime_controller.py`, `database.py` (letti); registri | nessuna regressione: nessuno stato d'ordine nuovo, nessuna modifica di schema; aggiunge `settled_customer_refs` e `_drop_settled_candidates` | nessuna |
| F-16 + F-R06 sullo stack del ponte | — | `tests/acceptance/test_f16_*`, `test_issue461_pr28e_funds_gate.py`, `test_g7_r06_rebuild_settled.py`, `tests/f026/test_g7_r06_settled_ambiguous.py`: 96 passed | nessuna |
| F-03 (01m) | `cashout_router.py` | la patch 01m **modifica un file di D**: rimuove 9 righe, il blocco duplicato nato dalla fusione locale di F-03. Dipende dalla forma di F-03 integrata | in integrazione: tenere la versione di F-03 su `main`, scartare l'hunk di 01m se il duplicato non c'è |

## 4. Conflitti testuali

Riapplicando 01d…sec01 su `main` `89af178` e fondendo F-16 e F-R06, i conflitti stanno **solo nei registri in
aggiunta**: `.guardrails/allowed_scope.json`, `CHANGELOG.md`, `guardrails/mutation_catalog.json`. Nessun conflitto
nel codice; `headless_main.py` e `scripts/ci_changed_modules.py` si applicano puliti.

Risoluzione: unione delle voci. Gli `original` del catalogo delle mutazioni devono restare unici; il test del catalogo
reale lo verifica.

## 5. Catalogo canonico dei test (#606)

Con `tests/control_api` su `main`, il test di raggiungibilità del catalogo fallisce finché manca la voce. Insieme alla
prima patch (01d) vanno aggiunti a `tests/catalog/pf-test-catalog.json`:
- la voce `control-api` proposta in G8 (`catalog/g8/pf-test-catalog.control-api.json`, branch
  `ccr-edf04c7d-e7vtj1-g8-suites`);
- il suo id in `campaigns.all`.

Provato: con entrambi, `tests/control_api` non risulta più scoperto.

## 6. Rischi residui dichiarati

- Le patch 10–12 dipendono dal codice di D non ancora su `main`: integrarle prima rompe i test (moduli assenti).
- La base di 01i-r2 è la copia di F-04 del momento (`772ab581`). D ha poi riscritto il branch (`2d0cf4ca`): integrare
  01i-r2 dopo il F-04 effettivo e confrontare i file di D.
- Ogni push al package MCP richiede la riverifica del pin (versione e schema hash) nel `bridge.py` integrato.
