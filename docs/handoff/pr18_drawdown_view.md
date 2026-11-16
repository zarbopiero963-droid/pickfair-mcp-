# PR-18 — patch di consegna: vista degli hard-stop di drawdown

**Mandato owner:** `PF-OWNER-MCP-PR18-DRAWDOWN-VIEW-20261116`. Corregge solo i due difetti
registrati in Pickfair-nogui #628-C11 e #628-C11-bis. Contratto MCP **1.16.0 invariato** (schema
hash `194301d4…f325`). Nessuna PR, nessun merge, nessun deploy, nessun LIVE, nessuna modifica al
codice applicativo del core: la patch tocca solo il ponte `control_api/` (consegna a Claude B per
PR-18) e i suoi test. L'integrazione richiede un GO owner separato.

LIVE OFF — CERTIFICAZIONE FINALE OFF — KILL SWITCH ON.

## I due difetti (comportamento precedente)

| Difetto | Prima | Stato reale del core |
|---|---|---|
| #628-C11 — drawdown assoluto | La vista cercava nel LOCKDOWN il codice `DRAWDOWN_ABS_HARD_STOP_TRIGGERED`, che il core non produce: il core scrive `drawdown_hard_stop_triggered:<tipo>:<perdita>`. Superamento reale ⇒ `drawdown_abs_hard_stop` = **ACTIVE**, e `drawdown_pct_hard_stop` = **TRIGGERED** anche se non configurato. | Superamento memorizzato nel `DrawdownHardStop`, gate d'ingresso `max_drawdown_abs_active`, runtime in LOCKDOWN. |
| #628-C11-bis — drawdown percentuale | `live_only`: in SIM, con il limite configurato, **INACTIVE** `ENFORCED_ONLY_IN_LIVE`. | Dopo #631 il core applica lo stop percentuale in SIM e LIVE (`tests/d1/test_d1_drawdown_hard_stop.py::test_percent_hard_stop_uses_the_persistent_peak_in_sim_and_live`). |

## Correzione

`control_api/views.py::_drawdown_stop(rc, name)` legge lo stato dal `DrawdownHardStop` **reale**
del runtime (`rc._drawdown_hard_stop`), in sola lettura e sotto il lock dello stop: `snapshot()`,
`scope_block_reason()`, `baseline_block_reason()`, `history_block_reason()`. Mai `reason()` o
`evaluate()` (salvano il picco) né `_hard_stop()` (costruirebbe e rileggerebbe lo stato). Nessuna
logica finanziaria duplicata: perdite, picco e superamento li decide il core; la vista riporta lo
stato memorizzato e i motivi del core. Nessun `live_only`: stessa regola in SIM e LIVE.

| Stato del core | Vista (`state` / `reason`) |
|---|---|
| stop assente nel runtime | UNKNOWN `STATE_UNAVAILABLE` (la vista non lo crea) |
| lock dello stop occupato | UNKNOWN `LOCK_BUSY` |
| stato persistito illeggibile | UNKNOWN `MAX_DRAWDOWN_ABS_STATO_ILLEGGIBILE` (anche con un superamento in memoria) |
| flag di superamento non booleano | UNKNOWN `STATE_INCOHERENT` |
| superamento di tipo sconosciuto | UNKNOWN `BREACH_KIND_UNKNOWN` (entrambi gli stop) |
| superamento di questo tipo | TRIGGERED `MAX_DRAWDOWN_ABS_ACTIVE` / `DRAWDOWN_HARD_STOP_ACTIVE`, `limit` = limite superato, `as_of` = istante del core; anche se il limite è stato poi tolto (lo sblocca solo l'owner) |
| limite assente | INACTIVE `NOT_CONFIGURED` |
| limite non valido (non finito, ≤ 0; percentuale > 100) | UNKNOWN `INVALID_LIMIT` (il core nega ogni ingresso: mai ACTIVE) |
| stato di un altro ambito, picco non salvato, baseline non verificata, storia insufficiente | UNKNOWN con il motivo del core (`DRAWDOWN_STATO_DI_ALTRO_AMBITO`, `MAX_DRAWDOWN_ABS_PICCO_NON_PERSISTITO`, `DRAWDOWN_BASELINE_NON_VERIFICATA`, `DRAWDOWN_STORIA_INSUFFICIENTE`, …): ingressi negati, picco non verificabile |
| altrimenti | ACTIVE, `source` `DRAWDOWN_HARD_STOP`, `limit` configurato |

La cassa non verificata (`max_drawdown_abs_cassa_non_verificata`) è una condizione del singolo
ingresso, non uno stato memorizzato: non compare nella vista ed è dichiarato qui.
`source` passa da `CONFIG` a `DRAWDOWN_HARD_STOP` quando lo stato viene dallo stop (il campo è un
`Code` generico: contratto invariato); resta `CONFIG` per limite assente o non valido.

## Albero sotto prova (riproducibile)

```sh
sh docs/handoff/pr18_drawdown_view/pr18_build.sh <clone Pickfair-nogui> <dest> base   # comportamento precedente
sh docs/handoff/pr18_drawdown_view/pr18_build.sh <clone Pickfair-nogui> <dest> fix    # con la correzione
```

| Elemento | Valore |
|---|---|
| core | `Pickfair-nogui` `main` @ `5daa6a51288bc7be69e663142a311cc729fd1cc1` (#631) |
| ponte di partenza | `control_api/` e `tests/control_api/` @ `0a529035` + `crossrepo_mcp116/crossrepo_bridge_1_16_test.delta.patch` |
| patch PR-18 | `pr18_drawdown_view/pr18_core_drawdown_view.patch` (sha256 in `pr18_drawdown_view/SHA256SUMS`) |
| tree `base` | `77482ddc73e4839544c86e6a7de4e17066986407` |
| tree `fix` | `eecffa58af75ed87af5a7f6295e45e1c57710f46` |
| MCP | `main` @ `3e4902c` + i test crossrepo di questo branch |

Ricostruito due volte da zero: tree identici a quelli dello spazio di lavoro.

## Evidenze

### Test del ponte (`tests/control_api/test_drawdown_view.py`, 31 casi, RuntimeController reale)

- Drawdown assoluto: non configurato (INACTIVE), attivo (ACTIVE), superamento reale (TRIGGERED con
  `as_of`), superamento con il messaggio di LOCKDOWN che il core produce davvero, superamento dopo
  la rimozione del limite, stati non verificabili (illeggibile, picco non salvato, baseline, storia
  insufficiente, altro ambito, lock occupato, stop assente, flag incoerente, tipo sconosciuto),
  limite non valido, nessun effetto collaterale sullo stop (snapshot identico dopo tre letture).
- Drawdown percentuale: SIM e LIVE × configurato e non configurato, superamento reale in SIM e LIVE,
  limite non valido (150, 0, −1, inf).
- Confronto con il gate reale del core su un runtime **avviato in SIM**: prima del superamento il
  gate `_drawdown_hard_stop_reason()` ammette e la vista dice ACTIVE; dopo il superamento il gate
  nega con il proprio motivo e la vista dice TRIGGERED (assoluto e percentuale).
- **RED** sul comportamento precedente: 20 falliti, 8 passati (i passati sono i casi che il codice
  precedente già trattava bene: non configurato, limite assoluto non valido, assenza di effetti).
  **GREEN** con la correzione: 31/31 (il caso del flag incoerente è stato aggiunto dopo la verifica
  a mutanti).
- Test storico `test_drawdown_stops_follow_the_core_rules` aggiornato: codificava la semantica errata
  (percentuale INACTIVE in SIM, codice di LOCKDOWN inventato).
- Suite del ponte, prima e dopo: **stesso insieme di 25 fallimenti preesistenti** (18 failed +
  7 errors, test dell'epoca 1.12 non riallineati a 1.16: fuori mandato, vedi sotto), 199 → 230
  passati, nessuna regressione. Esclusi `test_sl_tp_close_view.py` e `test_trailing_view.py`, che non
  si importano senza F-04/F-03.
- Verifica a mutanti manuale della nuova funzione: 13/13 uccisi (ramo del superamento, tipo, stato
  illeggibile, motivi di blocco, percentuale > 100, lock occupato, tipo sconosciuto, `as_of`,
  `limit`, ordine limite/superamento, picco non salvato, stop costruito dalla vista, flag non
  booleano).
- `ruff check` pulito.

### Crossrepo (stato reale del core ⇔ risposta MCP)

Nuovo comando dell'helper `DRAWDOWN STATE | ARM <limite> <valore> | BREACH <frazione>`: comando al
**core**, non alla Control API. Risponde il gate d'ingresso reale e lo snapshot dell'hard-stop.
Nuovo test `test_e2e_drawdown_hard_stops_match_the_core_state[abs|pct]`: runtime reale avviato in
SIM, letture tramite il tool MCP `get_status`; non configurato ⇒ INACTIVE; configurato ⇒ ACTIVE in
SIM; superamento reale (gate del core = `max_drawdown_abs_active` / `drawdown_hard_stop_active`,
LOCKDOWN) ⇒ TRIGGERED con limite e istante del core, l'altro stop resta INACTIVE.

Condizioni: utente `nobody`, namespace di rete vuoto con il solo loopback, come il gate MCP-116.

| Albero | Esito |
|---|---|
| `base` (comportamento precedente) | 14 PASS, 3 `BLOCKED_BY_DEPENDENCY` (F-18, F-04, F-03), **2 FAIL**: assoluto `ACTIVE` invece di `TRIGGERED`; percentuale `INACTIVE` invece di `ACTIVE` in SIM |
| `fix` | **16 PASS**, 3 `BLOCKED_BY_DEPENDENCY` (F-18, F-04, F-03), 0 FAIL |

Senza la patch PR-18 i due nuovi test falliscono per costruzione: sono la prova dei difetti.

### Regressioni MCP-116

Suite completa MCP sul branch (Python 3.12): **2357 passati, 20 skip, 0 falliti** (i due nuovi
test crossrepo sono `NOT_RUN` senza un core configurato; con il core, vedi la tabella sopra). Nessun file sotto `src/` cambiato:
contratto, descrittore e schema hash invariati.

## Cosa resta fuori (dichiarato)

- I 25 fallimenti preesistenti della suite del ponte (test 1.12 non riallineati a 1.16:
  `RATE_LIMIT_REQUIRED`, flag del launcher, chiavi di config, età del book…) appartengono a PR-18
  completa di Claude B, non a questo mandato.
- I 3 `BLOCKED_BY_DEPENDENCY` (F-18, F-04, F-03) restano tali: mai PASS.
- Nessuna prova in LIVE reale: in LIVE si verifica solo che la vista non dipenda dalla modalità
  (nessun avvio LIVE).
