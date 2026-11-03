# DEPENDENCY MAP — percorso critico e ordine di implementazione

Versione **0.1-DRAFT** · 03/11/2026 · baseline Pickfair-nogui `7a70062`, pickfair-mcp- `36bbef1`.

## 1. Dipendenze dal core (Corsia B, #586 / #461 / #491)

| Dipendenza core | Stato su main | Schede PF-MCP bloccate |
|---|---|---|
| #586 P0 (CSH, MM-02, RST, DD-03/04, ID-01, BF-01/02/05, FUNDS-03, DD-01/02, MOD-03) | in corso: F-01, F-05, F-06, F-08, F-09, F-10, F-13a, CB-586-FI-03Z mergiate (certificazione da registrare) | 012, 013, 016, 017, 020, 035 |
| #586 P1 (T80U, CAP-01, FUNDS-01, CFG-01..07, ROS-01/02, SET-01/02, CSH-12, CMP) | aperto | 011, 012, 014, 015, 025 |
| #586 P2/P3 (MOD-01/02, OBS, ARC, MM-01, STK-01, SIG-01..04, MOD-04/05…) | aperto | 010, 032, 033 |
| PR08 resolver per nome | da certificare | 009 |
| PR11 Market Stream; Order Stream (nuova scheda) | parziale / assente | 009, 018, 022 |
| PR15 separazione SIM/LIVE di peak, drawdown, saldo | aperto | 012, 032 |
| PR24/PR25 SL/TP, trailing, P35 | aperto | 018, 035 |
| PR30/31/32/33/34 ambiguità, startup reconciliation, fencing, saga, durabilità SIM | parziale; PR33 BLOCKED_ENV | 020, 021, 022 |
| PR37 barriera STOP | aperto | 019 |
| PR43/44/45 netting, Void, fraction, AMBIGUOUS cashout | aperto | 035 |
| PR47 correlation/audit | aperto | 007, 033 |
| Miglior prezzo dinamico (PF-OD12-04) | **non implementato** (decisione registrata) | 016 (CAP-ORD-16) |
| MANUAL nel core (preview → handle → conferma) | assente | 036 |
| CRUD strategie (scheda core da creare) | assente | 010, 015 |
| STOP per tavolo | assente | 015 |
| **PF-API-0** command contract neutro, `operation_id`, readiness MCP-aware, provenienza | assente | **tutte le integrazioni** |
| **PF-API-1** letture | assente | 004, 008–013 a L4/L5 |
| **PF-API commands** | assente | 014–019, 032, 035, 036 a L4/L5 |

## 2. Dipendenze infrastrutturali

| Dipendenza | Stato | Bloccate |
|---|---|---|
| Dispatcher universale e catalogo (#606) | PR aperta, dry-run, merge owner; attivazione con GO separato | corsia certification di tutte le schede; 024–028, 037 (ledger) |
| Governance #607 | PR aperta (Claude B) | nessuna diretta |
| Riconciliazione 44 ↔ 61 voci VPS | NOT_RUN | 024–027 |
| Identità di review separata (#472, N12) | rischio accettato; N12 aperto (file protetto) | Q5 più robusto |

## 3. Dipendenze owner

| ID | Decisione | Bloccate |
|---|---|---|
| Q-ORD | Ordine Control API: (a) solo progettazione / (b) PF-API-1 sola lettura su branch del core / (c) tutto in parallelo | 004 e ogni codice nel core da parte di Claude C |
| K1 | Modalità: assi dati × esecuzione; «Live data fittizio» | 032, 019 (switch) |
| K2 | Strategie: contratto CRUD nel core | 010, 015 |
| K3 | Route candidate RC-01…12 | 011, 013, 015, 033, parti di 009/019 |
| K4 | Sei livelli di privilegio | 034, 005 |
| K5 | Conferma fuori dall'agente (four-eyes) | 036 |
| K8 | Perimetro dei log accessibili | 033 |
| D-07, D-10, D-11, handle MANUAL, campi `/v1/meta`, schema hash | parametri tecnici PF-API-0 | 003, 004, 005, 006 |
| B1 dossier | rendere disponibile l'archivio #506 (A 872 / B 344 / 1.062 differenze / 125 righe Control API) | 001 completa |
| GO PR | ogni PR; nessun merge da Claude C (K7) | tutte |
| Mandato LIVE | MCP-06a/06b/07c | C-LIVE |

## 4. Percorso critico

```
[Owner Q-ORD, D-xx] ──────────────┐
                                  ▼
#586 P0 → P1 → P2/P3 ──► PF-API-0 ──► PF-API-1 ──► PF-API commands
                                  │            │              │
                    PF-MCP-003/004 ◄┘   008–013 L4/L5    014–019, 032, 035, 036 L4/L5
                                                   │              │
                         #606 attivo (GO) ─────────┴──────┬───────┘
                                                          ▼
                                       024 E2E · 025 Roserpina · 026 fault · 027 ostili
                                                          ▼
                                             028 verdetto ─► 029–031 rilascio
```

Elemento più lungo: **#586 → PF-API-0**. Tutto ciò che Claude C fa prima è preparazione (contratti,
adapter simulato, test pronti, catalogo) che riduce il tempo dopo PF-API, ma **non** anticipa la certificazione.

## 5. Schede immediatamente eseguibili (Corsia A, senza toccare il core)

| Ordine | Scheda | Cosa si produce ora | Collegamento |
|---|---|---|---|
| 1 | PF-MCP-001 | catalogo esteso sulle fonti accessibili | B-CTL-01 |
| 2 | PF-MCP-002 | matrice di tracciabilità con test pianificati | #586 A.2 |
| 3 | PF-MCP-003 | contratti delle 14 letture (PROVISIONAL) | contract_v1 |
| 4 | PF-MCP-037 | `catalog/capabilities.json` + calcolo D1–D5 lato MCP | #606 schema |
| 5 | PF-MCP-008 | `get_status`, `get_reconciliation_status` su adapter simulato | **MCP-02a #7** |
| 6 | PF-MCP-013 | `list_orders`, `get_operation`, `list_pending_operations` | MCP-02d #10 |
| 7 | PF-MCP-012 | `get_account`, `get_exposure`, `list_positions` | MCP-02b #8 |
| 8 | PF-MCP-009 | `list_events`, `list_markets`, `get_market_book` | MCP-02c #9 |
| 9 | PF-MCP-013 (b) | `get_config`, `get_audit_trail` | MCP-02e #11 |
| 10 | PF-MCP-019 (STOP) | preparazione `stop`/`resume`, non esposti | MCP-05a #24 |

Tutte READY_SIM: utili, ma valgono al più C-SIM-MCP. Da 5 in poi servono codice e PR, quindi il **GO owner**
per ciascuna (il GO limitato attuale copre lo sviluppo su branch, non la PR).

## 6. Ordine di implementazione consigliato (completo)

1. **Fase 00:** 001 → 002 → 003 → 037.
2. **Letture MCP su simulato:** 008 → 013 → 012 → 009 → 013(b).
3. **Barriera prima del trading:** 019 (STOP/resume, preparazione).
4. **Privilegi:** 034 (dopo K4), poi residui di 005/006/007.
5. **Con PF-API-0/1:** 004 → MCP-01d → MCP-02g → 011 → 010 → 033 (dopo K3/K8).
6. **Con PF-API commands:** 014 → 016 → 036 → 035 → 017 → 018 → 019 → 015 → 032 (dopo K1).
7. **Robustezza:** 020 → 021 → 022 → 023.
8. **Certificazione:** 024 → 025 → 026 → 027 → 028.
9. **Rilascio:** 029 → 030 → 031. LIVE: MCP-06a → 06b → 07c solo con mandato.

## 7. Parallelismo senza sovrapposizioni

- Claude C non apre PR in Pickfair-nogui finché #606/#607 sono aperte (una PR per repository) e senza Q-ORD.
- Claude C non modifica catalogo/dispatcher di #606: propone le suite MCP come voci del catalogo, che Claude B
  integra (o l'owner autorizza una PR dedicata dopo il merge di #606).
- Nel repository MCP: una PR alla volta, dopo GO; nessun merge da parte di Claude C (K7).
