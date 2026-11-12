# Gate crossrepo provvisorio di MCP-116 (contratto 1.16.0)

**Mandato owner:** `PF-OWNER-MCP116-CROSSREPO-BRIDGE-20261112` (opzione 1: patch del ponte di prova).
**Esito:** `CROSSREPO_PROVISIONAL_PASS` per i 14 test eseguibili sul core attuale; 3 test
`BLOCKED_BY_DEPENDENCY` (F-18, F-04, F-03), mai PASS. **Non** è `CORE_INTEGRATION_CERTIFIED`.

LIVE OFF — CERTIFICAZIONE FINALE OFF — KILL SWITCH ON.

## Cosa prova e cosa no

- **Prova** che MCP 1.16.0 (adapter HTTP, Control API con limite di frequenza e scatola nera
  obbligatori) funziona fra processi reali con il `RuntimeController` vero del core in SIM, la
  scatola nera BB-1 reale e un ponte compatibile con 1.16.0.
- **Non prova** il ponte definitivo: la patch qui sotto è un artefatto di collaudo. Il ponte
  ufficiale resta PR-18 di Claude B, che dovrà implementarlo e verificarlo usando queste evidenze.
- Nessun commit nel repository core, nessuna modifica a `main`, nessun deploy, nessun bypass del
  gate di rilascio #626 (in SIM il gate dà NO-GO solo per LIVE; la scatola nera si apre come fanno
  `headless_main` e `mini_gui`, cioè il gate di avvio della scatola nera resta attivo).

## Albero sotto prova (riproducibile)

| Elemento | Valore |
|---|---|
| core | `Pickfair-nogui` `main` @ `c535c1d559f11fdab4f09fa02c04c7824d1d2a19` |
| ponte di partenza | `control_api/` del branch di consegna `handoff/claude-c/mcp-core-20261105` @ `0a529035` (contratto 1.12.0) |
| patch di prova | `crossrepo_mcp116/crossrepo_bridge_1_16_test.delta.patch`, sha256 in `crossrepo_mcp116/SHA256SUMS` |
| hash dell'albero risultante | `git rev-parse HEAD^{tree}` = `0b23bff7533d0b5db156e3f677ca3b72f3081b09` |

La patch di prova cambia solo `control_api/bridge.py` e `control_api/launcher.py`:

1. pin del contratto 1.16.0 (versione e schema hash `194301d4…f325`);
2. scatola nera BB-1 obbligatoria: il ponte riceve il `BlackBoxReader` reale del core, ne verifica
   l'interfaccia (`check_reader`), aggiunge i 4 provider della scatola nera e il `request_hook`;
   lettore assente o incompatibile ⇒ la Control API non parte (`BLACKBOX_UNAVAILABLE`);
3. limite di frequenza obbligatorio, dichiarato dal chiamante senza valori predefiniti
   (`--control-api-rate`, `--control-api-burst`); fuori limite ⇒ non parte (`RATE_LIMIT_INVALID`).

Ricostruzione: `sh docs/handoff/crossrepo_mcp116/gate_build.sh <clone Pickfair-nogui> <dest> docs/handoff/crossrepo_mcp116/crossrepo_bridge_1_16_test.delta.patch`.

## Esecuzione

```sh
PICKFAIR_CORE_PATH=<dest> PICKFAIR_CORE_PYTHON=<python con le dipendenze del core> \
  python -m pytest -p no:cacheprovider tests/crossrepo -rA
```

Condizioni del collaudo registrato:
- **utente senza privilegi** (`nobody`, uid 65534);
- **nessuna rete esterna**: namespace di rete vuoto con il solo loopback
  (`connect_ex(1.1.1.1:443)` = 101, rete irraggiungibile); in più il processo core ammette solo
  connessioni a 127.0.0.1 e i proxy d'ambiente puntano a una porta chiusa;
- il core usa il package `pickfair_control_api` dello stesso albero MCP sotto prova.

## Esiti (17 test)

| Esito | Test |
|---|---|
| PASS (14) | normal_start_reconciliation_and_emergency_stop, reads_have_no_side_effects_on_the_core, invalid_token_is_unauthorized, unauthorized_principal_never_reaches_the_core, core_down_restart_timeout_incompatible_and_stale, stale_core_snapshot_is_rejected, no_secret_leaks, account_and_exposure_report_the_core_values, unserved_reads_are_not_implemented, diagnostics_protections_and_positions, orders_from_the_core_ledger, sl_tp_settlement_and_cashout_barriers, p0_ambiguous_row_without_unconfirmed_amounts, markets_and_book_from_the_real_tracker |
| BLOCKED_BY_DEPENDENCY:F-18 | config_is_read_only_and_redacted (il core `main` non registra `invalid_settings`) |
| BLOCKED_BY_DEPENDENCY:F-04 | sl_tp_close_from_the_core_record (`core/sl_tp_close.py` assente) |
| BLOCKED_BY_DEPENDENCY:F-03 | trailing_from_the_core_trailing_module (`core/trailing_stop.py` assente) |

**Perché i 3 BLOCKED non dipendono dal contratto MCP-116.** Le funzioni F-18/F-04/F-03 esistono
solo su branch del core non integrati (`keep/f18-config-validation-20261103`,
`claude/d-f03-trailing-stop`); la loro fusione con il `main` attuale del core va in conflitto su
`database.py` e non spetta a questo collaudo. Lato MCP la catena MCP-116 (`233ca74..HEAD`) non
cambia `tools/config.py`, `tools/finance.py`, `tools/diagnostics.py` (diff vuoto) e in
`contract/models.py` cambia solo l'a-capo delle docstring di questi modelli. La rilevazione nel test
è positiva sul checkout (file o simbolo presenti): con la funzione presente il test gira per intero.

## Difetto trovato dal gate e corretto (P2, disponibilità)

Con la scatola nera reale ogni richiesta del core dura di più; 30 letture concorrenti superavano il
tetto di connessioni servite del server (16, MCP-SEC-01), ricevevano `BUSY` e in 4 esecuzioni su 10
da 1 a 7 letture finivano in `UPSTREAM_UNAVAILABLE` (`READ_RETRY_EXHAUSTED`). Correzione:
l'adapter HTTP dell'MCP limita a `MAX_CONCURRENT_REQUESTS = 8` le richieste in volo (le altre
attendono; posto non ottenuto entro il timeout ⇒ `UPSTREAM_TIMEOUT` senza richiesta). Tetto del
server invariato. Test (falliscono senza la correzione) e mutante critico `X07`. Dopo la correzione:
10/10 esecuzioni pulite del test di concorrenza.

Il test sugli effetti collaterali ora ammette `BUSY` solo come risposta prima di qualsiasi provider
e verifica che le risposte OK siano 30 letture più da 1 a 1+BUSY handshake.
