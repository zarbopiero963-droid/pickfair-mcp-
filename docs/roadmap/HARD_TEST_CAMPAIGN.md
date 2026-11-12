# HARD TEST CAMPAIGN — MCP + Control API + Core

Versione **0.1-DRAFT** · 03/11/2026. Nessuna esecuzione con denaro reale è autorizzata da questo piano.
Un ambiente può essere reale nell'architettura (processi veri, DB SQLite temporaneo vero, Control API vera,
SimulationBroker vero, letture Delayed vere via gateway read-only) **senza** denaro reale.

## 1. Livelli di prova (mai equivalenti fra loro)

| Livello | Cosa gira davvero | Uso | Certifica integrazione? |
|---|---|---|---|
| L1 | funzione isolata | logica locale | no |
| L2 | MCP + adapter simulato | contratto lato MCP | no |
| L3 | processo `pickfair-mcp serve` (stdio) | protocollo, trasporto, arresto | no |
| L4 | Control API reale su loopback | schemi, auth, errori reali | parziale (senza esecuzione) |
| L5 | core in SIM (SimulationBroker, Delayed reale in lettura) | percorso completo SIM | **sì, per la SIM** |
| L6 | core LIVE | percorso reale | solo con mandato LIVE separato |

**Nessun mock produce una certificazione di integrazione.** Le campagne A–D sotto sono certificanti solo a L5.

## 2. Infrastruttura: nessuna seconda pipeline

- Le campagne entrano come suite del catalogo canonico di Pickfair-nogui (`tests/catalog/pf-test-catalog.json`,
  PR #606) ed eseguono dal dispatcher universale: **corsia development** per i test nuovi della PR
  (`certification: false`), **corsia certification** solo da catalogo di main, una esecuzione per SHA.
- Il lato MCP usa la propria CI (4 job richiesti + `independent-review`); le prove cross-repo L5 si
  registrano nel catalogo del core come job `orchestrator:<id>` in allowlist (proposta #606 §Limiti).
- Stato oggi: #606 **aperta, dry-run**; la riconciliazione 44 ↔ 61 voci VPS è NOT_RUN. Finché il dispatcher
  non è attivo (GO owner separato), le campagne sono **pronte ma NOT_RUN**.

## 3. Campagne

### A. Integrazione reale MCP → Control API → Core

| ID | Scenario | Oracolo (PASS) |
|---|---|---|
| A-01 | Handshake, lettura di tutte le route su core SIM | ogni campo da sorgente del core; campo assente ⇒ «indisponibile» |
| A-02 | `place_order` BACK e LAY | un solo ordine nel SimulationBroker, ledger e DB coerenti, liability LAY = stake×(price−1) |
| A-03 | Dutching N selezioni | stake Decimal attesi dall'oracolo, somma e rendimento verificati |
| A-04 | Cancel / replace | stato coerente; replace ambiguo ⇒ AMBIGUOUS, nessun retry |
| A-05 | Cashout selezione/mercato/all | posizione chiusa solo con esposizione residua zero riconciliata |
| A-06 | STOP / PAUSE / EMERGENCY / RESUME | semantica del contratto; resume solo dopo readiness |
| A-07 | Patch config | applicata atomica, reload preserva stato, audit presente |
| A-08 | Sabotaggio di un collegamento alla volta (no-bypass) | ogni sabotaggio fa fallire il test |

### B. Roserpina multitavolo e Money Management

| ID | Scenario | Oracolo |
|---|---|---|
| B-01 | 2, 5, 10 tavoli (e oltre fino al limite dichiarato dell'infrastruttura) | esposizione aggregata = somma per tavolo; nessun cap superato |
| B-02 | Entrate simultanee su tavoli diversi stesso evento | anti-duplicazione rispettata, allocazione deterministica |
| B-03 | Gol / variazione di quota durante ingresso | rivalidazione secondo policy, mai ingresso a quota fuori condizioni |
| B-04 | Liquidità insufficiente | rifiuto esplicito, zero effetti |
| B-05 | Transizioni desk EXPANSION/DEFENSE/LOCKDOWN | soglie del config, nessuna soglia di default nascosta |
| B-06 | Recovery tables e debito dopo perdita (F-10) | debito persistito e ripreso dopo kill |
| B-07 | Interruzione e ripresa della sessione | tavoli ripristinati, nessun ordine riemesso |

### C. Crash / recovery ostile (kill -9 in ogni punto)

Punti di interruzione: prima dell'ordine · dopo `begin` del journal · dopo `sent` · durante l'invio ·
dopo l'accettazione del broker · prima della persistenza nel DB · durante il cashout · durante il dutching
multi-selezione · durante lo switch di modalità · durante la riconciliazione · durante il riavvio.

| Oracolo comune |
|---|
| dopo il riavvio: STOP persistente mantenuto; riconciliazione prima di qualsiasi nuovo ordine; nessun ordine duplicato; nessuna esposizione nascosta (DB, ledger, broker convergono); esiti incerti = AMBIGUOUS, mai SUCCESS/FAILED presunti; il MCP non ripete mutazioni (journal `NOT_SENT`/`AMBIGUOUS`) |

Processi da uccidere separatamente e insieme: MCP, Control API, core. Ripetizioni: ≥ 200 per punto
(come MCP-01b, 200 SIGKILL).

### D. Sicurezza avversaria

| ID | Attacco | Oracolo |
|---|---|---|
| D-01 | Tool non autorizzato per lo scope | FORBIDDEN prima di ogni upstream |
| D-02 | Replay di richiesta / handle MANUAL riusato o scaduto | rifiuto, nessun effetto |
| D-03 | Spoofing di identità / token alterato | rifiuto, audit dell'evento |
| D-04 | Payload alterati: campi extra, NaN, Inf, bool numerici, stringhe enormi, unicode ostile | rifiuto, zero effetti |
| D-05 | Prompt injection in nomi di eventi, mercati, blocker, log, audit | trattati come dati; zero ordini, zero switch, zero config |
| D-06 | Tentativo di aggirare STOP, limiti, MM | bloccato dal core; il MCP non ha percorsi alternativi |
| D-07 | `set_mode` LIVE da non-owner o senza readiness | bloccato dal MCP **e** dal core |
| D-08 | Modifiche concorrenti della config | una sola vince, nessuno stato misto |
| D-09 | Destinazione non loopback, redirect, Betfair diretto, DB diretto | rifiutati (guard statici + runtime) |
| D-10 | Ricerca di segreti in stdout, stderr, audit, journal, log esportati | nessun segreto presente |

## 4. Scenari obbligatori della direttiva (tracciati)

| Scenario | Oracolo | Campagna | CAP | Stato |
|---|---|---|---|---|
| Due agenti inviano lo stesso ordine | una sola esecuzione | A-02, C | ORD-11 | NOT_RUN |
| MCP si blocca dopo il comando | nessuna ripetizione non riconciliata | C | MET-10 | NOT_RUN (L2 PASS su MCP-01b) |
| Risposta Betfair persa | AMBIGUOUS gestito e riconciliato | C, A-04 | ORD-12 | NOT_RUN |
| Crash durante cashout | esposizione residua rilevata e gestita | C | CSH-13/15 | NOT_RUN |
| 10 tavoli simultanei | esposizione aggregata e limiti corretti | B-01 | BKR-03/04 | NOT_RUN |
| STOP durante un'operazione | nessuna nuova esposizione; in volo riconciliate | A-06, C | STP-09 | NOT_RUN |
| Quota cambia prima dell'invio | rivalidato secondo policy | B-03 | ORD-16 | NOT_RUN (core: assente ⇒ RED atteso) |
| Saldo insufficiente | rifiuto senza effetti | A-02 | ORD-17 | NOT_RUN |
| Microstake 0,10 € | precisione Decimal | A-02 | ORD-05 | NOT_RUN |
| Commissione 4,5 % | profitto netto corretto | A-05 | CSH-09, BKR-09 | NOT_RUN |
| P/L con segno invertito | mutante rilevato | §5 | CSH-09 | NOT_RUN |
| SL/TP/trailing non propagato | test fallisce, config non dichiarata applicata | A-07 | SLT-07 | NOT_RUN |
| Retry con configurazione cambiata | nessuna applicazione inconsistente | C, D-08 | CFG-07 | NOT_RUN |
| MCP tenta di attivare LIVE | bloccato da core e gateway | D-07 | MOD-08 | NOT_RUN |
| Perdita di database o stream | nessuna falsa dichiarazione di stato sicuro | C | REC-07, MKT-08 | NOT_RUN |
| Switch modalità con posizioni aperte / durante riconciliazione | transizione bloccata o atomica | C | MOD-05/06 | NOT_RUN (BLOCKED_OWNER K1) |
| Riavvio in stato incerto | nessun ACTIVE prima della riconciliazione | C | REC-03 | NOT_RUN |
| Perdita di connessione Betfair | nessun ingresso, nessun riprezzamento | C | ORD-22 | NOT_RUN |
| Corruzione o indisponibilità dei dati | fail-closed | C, D | CFG-06 | NOT_RUN |
| Esposizioni nascoste dopo recovery | zero | C | CSH-19 | NOT_RUN |

Casi economici in ogni oracolo finanziario: risultato positivo, negativo, nullo, posizione mista, fill parziale.

## 5. Mutation testing delle invarianti

Mutanti obbligatori (devono essere KILLED): segno del P/L invertito; commissione ignorata; liability LAY
come stake; retry dopo `sent`; AMBIGUOUS trattato come SUCCESS; STOP ignorato per un ingresso già in coda;
resume declassato a `write`; scope ignorato; campo assente sostituito da default; arrotondamento verso
l'alto dello stake; cap applicato in silenzio invece di rifiuto; capacità esclusa dal denominatore;
SKIPPED contato come PASS. Lato MCP estendono `scripts/critical_mutations.py`; lato core il catalogo
`guardrails/mutation_catalog.json`.

## 6. Regressioni permanenti dai difetti finanziari già trovati

Ogni difetto chiuso diventa un test permanente nel catalogo, con ID del difetto: F-01 (P/L liquidabile
SL/TP), F-05 (hedge nel ledger), F-06 (hedge che chiude la posizione), F-08 (ghost all'avvio), F-09
(recovery blocca ACTIVE), F-10 (debito di recovery dopo crash), F-13a (customerOrderRef), CB-586-FI-03Z
(SIM non abbina su size 0), più i 26 difetti confermati della Phase 0 del 06/10 quando chiusi.

## 7. Dati

Replay di mercati e quote: dataset versionati con hash, registrati nel catalogo; mai dati personali o
segreti; origine dichiarata (Delayed registrato, sintetico). La «SIM offline» su replay è **solo test**
finché K1 non è deciso.
