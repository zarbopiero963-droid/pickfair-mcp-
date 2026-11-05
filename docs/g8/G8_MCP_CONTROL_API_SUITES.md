# G8 — suite automatiche MCP / Control API per il catalogo universale

Mandato owner del 05/11/2026, priorità 4. Riferimento: gap **G8** di PF-UNIVERSAL-360-TESTING
(`docs/roadmap/pf_universal_360_testing.md` §3, branch `pf-gov-persistent-roadmap-01` @ `eacba405`, registrato
su Pickfair-nogui #586 c.6657216281): «GUI Windows, Control API, MCP, packaging … non testati in automatico …
suite dichiarate `UNSUPPORTED` con motivo finché non c'è un runner». Catalogo canonico:
`tests/catalog/pf-test-catalog.json` (`pf-test-catalog/1`, `main` `911562ad`, 45 suite, nessuna MCP/Control API).

## 1. Due parti, perché vivono in due repository

| Parte | Dove gira | Stato nel catalogo canonico |
|---|---|---|
| Ponte Control API nel core (`tests/control_api/…` di Pickfair-nogui) | dispatcher di Pickfair-nogui | **proposta** `catalog/g8/pf-test-catalog.control-api.json`: voce `control-api` (pytest `tests/control_api`, SIM, LOW). Validata col `validate_catalog` **reale** di `scripts/pf_test_dispatch.py` (`main` `911562ad`): VALIDA sul `main` con il ponte applicato (46 suite), RIFIUTATA (`PYTEST_PATH:control-api`) senza il ponte. Entra nel catalogo con una PR del core dopo l'integrazione delle patch (Claude B) |
| Repository MCP (`pickfair-mcp-`) | `scripts/run_suites.py` nel repository MCP | `UNSUPPORTED` nel catalogo canonico, con motivo: il dispatcher esegue solo percorsi `tests/` di Pickfair-nogui. Nessun nuovo runner o servizio: si usa pytest con le stesse regole |

## 2. Manifest `catalog/g8/pf-mcp-suites.json` (`pf-mcp-suites/1`)

Stessi campi chiusi del catalogo canonico più `allowed_skips` (test saltati ammessi, uno per uno, con motivo).

| Suite | Percorsi | Ambiente | Cosa prova |
|---|---|---|---|
| `mcp-unit` | `tests/unit` | OFFLINE | contratto, modelli, parsing, handshake, journal, token, CLI |
| `mcp-guards` | `tests/guards` | OFFLINE | nessun bypass, superficie dei tool, igiene dello scope, G8 stesso |
| `mcp-control-api` | `tests/control_api` | OFFLINE | server HTTP reale su loopback: autenticazione, route, errori, sicurezza (MCP-SEC-01) |
| `mcp-integration` | `tests/integration` | OFFLINE | server MCP in processo: adapter simulato e Control API reale via HTTP |
| `mcp-e2e` | `tests/e2e` | OFFLINE | processo stdio reale, journal, kill |
| `mcp-crossrepo` | `tests/crossrepo` | SIM | catena fra processi col core reale in SIM; richiede `PICKFAIR_CORE_PATH`, `PICKFAIR_CORE_PYTHON` |

Campagne: `all-offline` (le prime cinque), `all` (tutte). Ogni file `tests/**/test_*.py` appartiene ad almeno
una suite (verificato da `tests/guards/test_g8_suites.py`).

## 3. Runner `scripts/run_suites.py`

`python scripts/run_suites.py suite:<id>|campaign:<nome> --evidence DIR`. Argv fisso dal manifest (solo
`tests/…` esistenti, nessun flag, nessuna risalita), evidenze `<id>.junit.xml`, `<id>.log`, `report.json`.

Verdetti:
- **PASS**: exit 0, nessun fallito o errore, nessun saltato fuori da `allowed_skips`.
- **FAIL**: almeno un fallito o errore, oppure timeout.
- **BLOCKED**: prerequisito mancante (nessuna esecuzione), nessun test raccolto, oppure un test saltato non ammesso.

Una campagna è PASS solo se tutte le suite sono PASS. Una suite non verificabile non è mai PASS.

## 4. Limiti e prossimi passi

- L'esecuzione automatica sulla VPS o nel dispatcher del core richiede un runner cross-repository (G8 resta aperto
  lato infrastruttura: non introdotto qui, per mandato).
- La voce `control-api` va proposta nel catalogo del core da Claude B insieme alla prima patch del ponte integrata.
  Insieme alla voce va aggiunto l'id `control-api` a `campaigns.all`: lo richiede
  `test_campaign_all_reaches_every_test_except_the_redundant_full_regression`. Provato il 05/11/2026 sul core con
  ponte e `claude/d-market-book-age` (contiene `main` `911562ad`). Senza la voce, `tests/control_api` risulta non
  raggiungibile dal catalogo. Con voce e campagna, `tests/scripts` (dispatch e catalogo) dà 661 passed. Restano 2
  failed, preesistenti e indipendenti dal ponte, entrambi dello stack di Claude D: le directory `tests/f02`,
  `tests/f03`, `tests/f13b` e `tests/f18` non sono nel catalogo, e mancano gli originali di mutazione
  `recovery_live_bets_inverted`.

## 5. Esito della campagna `all` (05/11/2026)

PASS: 6/6 suite e 1845 test. Dettaglio: mcp-unit 1260 (1 skip ammesso, permessi da root), mcp-guards 139,
mcp-control-api 131, mcp-integration 268, mcp-e2e 32, mcp-crossrepo 15. Eseguita su questo branch (`c37b938`) con il
core del ponte fino a SEC-01; il JUnit di ogni suite resta nello scratchpad della sessione. Rapporto:
`docs/g8/evidence/campaign_all_20261105.json`.
