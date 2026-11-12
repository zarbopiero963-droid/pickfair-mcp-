# MASTER ROADMAP — MCP + Control API di Pickfair-nogui

Versione **0.1-DRAFT** · 03/11/2026 · autore Claude C · stato **PROPOSTA, non ratificata**.

Direttiva owner: «PICKFAIR — MASTER ROADMAP MCP + CONTROL API» + «ADDENDUM ENTERPRISE CONTROL &
CERTIFICATION» (03/11/2026). Autorizzati: progettazione completa e preparazione delle schede; resta il
GO limitato allo sviluppo controllato già concesso. **Non autorizzati: PR, merge, deploy, VPS, LIVE,
operazioni con denaro reale.**

Documenti del pacchetto (stessa cartella):

| File | Contenuto |
|---|---|
| `MASTER_ROADMAP_MCP_CONTROL_API.md` | questo file: obiettivo, regole, fasi, percorso critico, conflitti con decisioni owner |
| `FUNCTIONAL_COVERAGE_MATRIX.md` | catalogo versionato delle capacità (ID permanenti), tre livelli di readiness |
| `PR_CARDS.md` | 37 schede PF-MCP con i campi richiesti e il collegamento alle schede esistenti |
| `HARD_TEST_CAMPAIGN.md` | campagne di test hard, scenari obbligatori, oracoli |
| `CERTIFICATION_GATES.md` | gate Q1–Q6, corsie development/certification, dossier, metriche del 100 % |
| `DEPENDENCY_MAP.md` | dipendenze core / Control API / MCP / owner, percorso critico, ordine consigliato |

Audit di partenza: `docs/audit/claude_c_audit_2026-11-03.md` (stesso branch).

## 1. Obiettivo e definizione del 100 %

Ogni capacità **realmente implementata** in Pickfair deve essere accessibile, osservabile e verificabile
tramite la Control API e, dove autorizzato, tramite MCP; ogni capacità mancante nel core è registrata come
dipendenza, mai simulata.

Una capacità è **COMPLETA** solo quando sono PASS tutti i livelli applicabili:

1. **Core readiness** — la funzione esiste nel core ed è certificata (#586 / #506 / #351).
2. **API/MCP readiness** — è raggiungibile e controllabile via Control API reale e tool MCP (non simulati).
3. **Certification readiness** — verificata con test indipendenti, ostili, su SHA esatti dei due repository.

Il 100 % è misurato su cinque dimensioni separate (`CERTIFICATION_GATES.md` §5), con denominatore = catalogo
delle capacità applicabili, **non** i 25 tool. Il 100 % significa copertura completa dei requisiti
applicabili e ratificati, non assenza garantita di difetti.

Punto di partenza misurato (03/11/2026):

| Misura | Valore |
|---|---|
| Tool MCP integrati con il core reale | **0/25** |
| Tool MCP esposti (solo adapter simulato) | 1/25 (`get_meta`) |
| Route Control API esistenti nel core | **0/25** |
| Capacità censite nel catalogo v0.2 | 228, di cui 225 applicabili (3 duplicati marcati; il catalogo cresce con PF-MCP-001) |
| Capacità COMPLETE (3 livelli PASS) | **0/225** |

## 2. Principi vincolanti (riepilogo; fonte: contratto consolidato e #426)

- MCP è un telecomando: **nessun secondo motore**. Roserpina è l'unica autorità monetaria, l'Order Authority
  del core l'unica autorità di invio. Il MCP non calcola stake, liability, esposizione, cashout, MM.
- Percorso unico: **MCP → Control API (in-process, loopback, autenticata, versionata) → command/runtime
  contract → MM/Risk/Safety → broker** (SimulationBroker in SIM).
- Un solo set di tool per SIM e LIVE; parità SIM/LIVE; mai auto-LIVE; il comando owner non bypassa i gate.
- Nessun cap monetario predefinito; limiti configurabili espliciti, opzionali (OFF), subordinati alle protezioni obbligatorie.
- Esito incerto = AMBIGUOUS + riconciliazione, mai retry cieco, mai CLOSED con esposizione non riconciliata.
- Fail-closed, least privilege, segregation of duties, defense in depth, audit append-only, four-eyes per
  le azioni a doppia conferma (riferimenti di controllo: NIST SSDF, NIST SP 800-53, OWASP ASVS, OWASP API
  Top 10 — matrice di applicabilità in `CERTIFICATION_GATES.md` §7; **nessuna certificazione formale dichiarata**).
- Nessuna seconda infrastruttura di certificazione: si usa il catalogo e il dispatcher universale di
  Pickfair-nogui (PR #606, oggi **aperta e in dry-run**) con le due corsie development/certification.

## 3. Le sette fasi

| Fase | Nome | Schede | Esito atteso |
|---|---|---|---|
| 00 | Inventario e contratti | PF-MCP-001…003 | catalogo capacità, matrice di tracciabilità, catalogo contratti |
| 01 | Fondamenta Control API | PF-MCP-004…007, 034 | API versionata, auth/permessi, idempotenza, audit |
| 02 | Lettura integrale | PF-MCP-008…013, 033 | tutte le letture da sorgenti reali del core |
| 03 | Controllo operativo | PF-MCP-014…019, 032, 035, 036 | comandi via authority, solo SIM finché non c'è mandato LIVE |
| 04 | Robustezza estrema | PF-MCP-020…023 | recovery, concorrenza, guasti, hardening |
| 05 | Test hard e certificazione | PF-MCP-024…028, 037 | campagne E2E, Roserpina, fault injection, sicurezza, verdetto |
| 06 | Rilascio controllato | PF-MCP-029…031 | packaging, collaudo autorizzato, audit finale |

Schede nuove dall'addendum (fuori dalle 31 iniziali): **032** macchina a stati delle modalità, **033**
accesso a log e diagnostica, **034** modello dei privilegi a sei livelli, **035** cashout integrale,
**036** dutching integrale, **037** registro automatico della copertura. Dettaglio in `PR_CARDS.md`.
Totale proposto: **37 schede** (non 37 PR: una scheda può diventare più PR o accorparsi, senza perdere ID).

Riconciliazione con le schede esistenti: ogni PF-MCP elenca le schede MCP-xx (pickfair-mcp- #3–#32) e i
passi PF-API / PRxx / B-xxx (Pickfair-nogui #461, #491, #586) che assorbe o da cui dipende. Gli ID
storici restano validi; nessuna scheda esistente è cancellata.

## 4. Corsie di lavoro

| Corsia | Chi | Cosa | Vincoli |
|---|---|---|---|
| A | Claude C | MCP, adapter, contratti, test lato MCP, progettazione Control API | sviluppo su adapter simulato = mai certificazione di integrazione |
| B | Claude B | core (#586), governance, infrastruttura test (#606/#607) | Claude C non tocca queste PR |
| Integrazione | A + B | Control API ↔ core, **solo per capacità mature** (core readiness PASS o fix certificato) | ordine Core → Control API → MCP (#586, 29/10) |
| Certificazione | revisore indipendente (Grok / istanza designata) + dispatcher | corsia certification | l'esecutore non certifica il proprio lavoro |

## 5. Percorso critico (sintesi; dettaglio in `DEPENDENCY_MAP.md`)

```
#586 P0→P3 core ─┐
                 ├─► PF-API-0 (command contract neutro, operation_id, readiness MCP-aware)
PF-MCP-001…003 ──┘        │
                          ├─► PF-API-1 letture (PF-MCP-004/008…013) ─► MCP-01d adapter HTTP ─► MCP-02g
                          └─► PF-API commands (PF-MCP-014…019) ─► MCP-04h / 05d
                                         │
                              #606 dispatcher attivo (GO owner)
                                         │
                     campagne PF-MCP-024…027 (SIM, broker deterministico)
                                         │
                           PF-MCP-028 verdetto indipendente
                                         │
                     PF-MCP-029…031 rilascio · LIVE solo con mandato separato
```

Il collo di bottiglia non è il MCP: è **PF-API-0**, che dipende dal core #586 e da decisioni tecniche
ancora da ratificare (D-07, D-10, D-11, handle MANUAL, schema hash condiviso).

## 6. Conflitti con decisioni owner vigenti — da risolvere prima delle schede interessate

L'addendum introduce richieste che contraddicono decisioni owner registrate. Non le risolvo io: le
schede coinvolte restano **BLOCKED_OWNER** sul punto, il resto procede.

| # | Richiesta dell'addendum | Decisione vigente | Schede bloccate sul punto | Proposta |
|---|---|---|---|---|
| K1 | Quattro modalità: SIM offline, Delayed fittizio, Live data fittizio, Live reale | 07/10: solo SIM e LIVE, vietati LIVE_DATA_SIM e PAPER; 22/10 (CLOSURE-03): SIM / HYBRID_REAL_EXECUTION (disabilitata) / LIVE; 27/10: unico programma autorizzato REAL-DATA SIM (Delayed reale, esecuzione virtuale) | PF-MCP-032, 019 | Modellare **assi separati** (sorgente dati × esecuzione) invece di nuove modalità: «SIM offline» = replay/dataset solo di test; «Delayed fittizio» = REAL-DATA SIM attuale; «Live data fittizio» = vietato finché l'owner non revoca il divieto; «Live reale» = LIVE gated |
| K2 | Strategie: creazione, modifica, attivazione, versionamento | 08/10: nessuna strategia hardcoded/predefinita, nessun tool strategia ora; CRUD futuro solo dopo contratto core; il core oggi non ha strategie | PF-MCP-010, 015 | Classificare CORE_BLOCKED; serve prima una scheda core (Corsia B) con contratto CRUD |
| K3 | Endpoint per log, tavoli, strategie, SL/TP, diagnostica | AGENTS.md MCP §3: nessuna route oltre le 25 approvate; OWN-MCP-02F: prima estendere le route esistenti, route nuove solo se le esistenti non bastano e previa approvazione | PF-MCP-011, 013, 015, 033 | Elenco di route candidate in `FUNCTIONAL_COVERAGE_MATRIX.md` §4 da ratificare in un unico atto owner |
| K4 | Sei livelli di privilegio (READ, SIMULATE, CONFIGURE, OPERATE, EMERGENCY, ADMIN) | MCP-01c (mergiata): scope `read`, `write`, `admin`, `owner`; `resume` sempre owner | PF-MCP-034, 005 | Mappatura proposta in PF-MCP-034; i livelli nuovi si aggiungono, nessun indebolimento di `resume`/`set_mode` owner-only |
| K5 | Doppia conferma verificata da un sistema indipendente dall'agente | 22/10: nessuna GitHub App né nuovo servizio; gli account agente pubblicano come owner (#472) | PF-MCP-036 (MANUAL), 005 | Conferma owner fuori banda (canale non accessibile all'agente) da progettare; richiede decisione infrastruttura |
| K6 | Telegram come origine segnali | Telegram/Copy/Mirror SOSPESI | PF-MCP-010 | Solo lettura dello stato «sospeso»; nessun tool di attivazione |
| K7 | «Non effettuare merge» (questa direttiva) | Mandato Fase A del 22/10: merge automatico delle 18 schede con gate PASS | tutte le MCP | **Prevale la direttiva più recente**: niente merge da parte di Claude C finché l'owner non riattiva esplicitamente la delega |
| K8 | Accesso a log di broker e Betfair | No credenziali, no Betfair diretto | PF-MCP-033 | Solo log redatti prodotti dal core, via Control API |

Domanda aperta dell'audit del 03/11 (ancora senza risposta): **ordine della Control API** — (a) solo
progettazione finché il core #586 non chiude; (b) **PF-API-1 di sola lettura su branch del core, senza
comandi** (raccomandata); (c) Control API completa in parallelo (sconsigliata). Finché manca la risposta,
Claude C non scrive codice in Pickfair-nogui.

## 7. Schede eseguibili subito, bloccate, ordine consigliato

Sintesi; dettaglio in `DEPENDENCY_MAP.md` §4.

- **Eseguibili ora (Corsia A, solo documentazione o adapter simulato):** 001, 002, 003, 037 (registro
  copertura, lato documentale), parti MCP di 005/006/007 (già in larga parte fatte: MCP-01b/01c), parti
  MCP di 008 (= MCP-02a), 009 (= 02c), 012/013 lato lettura (= 02b/02d/02e), 019 parte STOP (= 05a).
- **Bloccate dal core / Control API:** 004 (PF-API-0/1), 010, 011, 014–018, 020–022, 024–027, 032 (+K1),
  033 (+K3), 035, 036.
- **Bloccate dall'owner:** K1–K6, mandato LIVE (MCP-06), GO per attivare #606, GO per ogni PR.

Ordine consigliato: **001 → 002 → 003 → 037 → 008 → 012/013 (letture) → 009 → 019 (STOP) → 034 → 006/007
residui → [PF-API-0/1 disponibili] 004 → 011 → 010 → [PF-API commands] 014 → 016 → 036 → 035 → 018 →
019 → 015 → 032 → 033 → 020…023 → 024…028 → 029…031**.

## 8. Governance applicata a questa roadmap

- Nessuna PR senza GO owner; una sola PR aperta per repository; nessun merge (K7); nessun deploy; nessuna VPS.
- Ogni scheda: Gate A specifico → RED → GREEN → regressione → mutazioni → review indipendente sullo SHA
  esatto → Gate B (HT-1, `CERTIFICATION_GATES.md`).
- Budget fix loop: 10 cicli per PR (CLAUDE.md Pickfair-nogui, AGENTS.md MCP §4).
- Ogni modifica rilevante dopo una certificazione la invalida (`CERTIFICATION_GATES.md` §6).
- Questo pacchetto è una **proposta**: diventa programma ufficiale con la ratifica owner (registrazione in
  #426 e in pickfair-mcp- #1).
