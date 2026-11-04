# CERTIFICATION GATES — MCP + Control API

Versione **0.1-DRAFT** · 03/11/2026. Si appoggia ai gate esistenti senza sostituirli: MCP-HT-1
(pickfair-mcp- #1), Gate A/B (#506), `docs/hard_verify_spec.md` e `docs/auto_pr_flow_spec.md` §0.9 / 0.9-bis
di Pickfair-nogui, PF-REVIEW-ATTESTATION v2 (#602), dispatcher e catalogo (#606).

## 1. Gate di qualità per ogni PR (Q1–Q6)

| Gate | Requisito | Prova | Fail-closed se |
|---|---|---|---|
| Q1 | Contratto e comportamento documentati | `docs/contract_v1.md` / docs di dominio aggiornati nello stesso PR; CAP-ID citati | doc assente o disallineata |
| Q2 | Unit, integration, regressione PASS | CI completa sullo SHA | un solo test rosso o saltato senza motivo registrato |
| Q3 | Negativi, timeout, input ostili PASS | suite negativa della scheda | test negativo assente per un ramo nuovo |
| Q4 | Concorrenza, recovery, sicurezza applicabili PASS | campagne B/C/D pertinenti | N/A non motivato |
| Q5 | Review indipendente sullo SHA esatto | MCP: status `independent-review`; core: Sol + Grok settled, Codex triagiato | review su altro SHA, troncata, con BLOCKING |
| Q6 | Evidenze firmate, riproducibili, verdetto esterno | attestazione Sigstore (#602) / ledger #606; comando di riproduzione | evidenza non verificabile |

Oltre a Q1–Q6 restano tutti i gate vigenti (mutanti critici 100 %, mutmut ≥ 85 %, check-completion gate,
fix loop ≤ 10, scope `.guardrails/allowed_scope.json` = diff). **Merge solo owner** (direttiva 03/11).

## 2. Corsie separate

| | development | certification |
|---|---|---|
| Codice eseguito | test della PR (non fidati) | solo catalogo di `main` |
| Dove | sandbox dev (#606), CI della PR | dispatcher #606 corsia certification |
| Esecuzioni | ripetibili | una per SHA |
| Esito | `certification: false`, mai Gate A/B | unico esito ufficiale |
| Chi lo produce | esecutore (Claude C/B) | dispatcher + revisore indipendente |

Una prova in corsia development **non può** essere promossa a certificazione, nemmeno se identica.

## 3. Livelli di certificazione

| Livello | Contenuto | Prerequisito |
|---|---|---|
| C-SIM-MCP | capacità lato MCP su adapter simulato (L2/L3) | Q1–Q6 per scheda — **non** è integrazione |
| C-API | Control API reale (L4) | PF-API-1 / commands certificati nel core |
| C-SIM-E2E | MCP → Control API → core SIM (L5), campagne A–D | C-API + core readiness PASS delle capacità |
| C-LIVE | L6 | mandato owner LIVE, MCP-06a/06b, gate PR53/54/59/60 e #351 |
| C-REAL-EXEC | caso singolo con ordini reali (Delayed key) | GO owner specifico per caso (27/10) |

## 4. Dossier per scheda

Ogni scheda produce un dossier con: CAP-ID coperti · requisiti e invarianti · SHA del codice (entrambi i
repository se cross-repo) e versione del contratto · matrice dei test con esiti · risultati delle mutazioni
· evidenze firmate o hash verificabili · review indipendente (link e SHA) · difetti aperti · stato delle
dipendenze · esito del gate · piano di rollback · identità di esecutore e revisore · anomalie e copertura
mancante. Un dossier con sole prove mock vale al più C-SIM-MCP.

## 5. Le cinque dimensioni del 100 %

Denominatore: CAP applicabili del catalogo (v0.2: 225), non i 25 tool. Il denominatore è
preliminare: diventa definitivo solo dopo l'inventario completo (PF-MCP-001) e una verifica indipendente.

| Dimensione | Formula | Oggi |
|---|---|---|
| D1 Capacità applicabili esposte via Control API/MCP reali | CAP con L2 = SI / CAP applicabili | 0/225 (21 con catena su branch `HRN`, non contano) |
| D2 Contratti implementati e testati | contratti con Q1–Q3 PASS a L4 / contratti richiesti | 0 (1 solo a L2) |
| D3 Operazioni sensibili con test di sicurezza | operazioni sensibili con campagna D PASS / operazioni sensibili | 0 |
| D4 Scenari critici crash/recovery | scenari campagna C PASS / scenari obbligatori | 0 |
| D5 Evidenze richieste valide e verificabili | evidenze verificate / evidenze richieste | 0 |

Regole: `SKIPPED`, `BLOCKED`, `NOT_TESTED`, `NOT_RUN`, `INFRA_ERROR` = non-PASS; una capacità obbligatoria
esce dal denominatore solo con decisione owner citata (`OUT_OF_SCOPE`/`RETIRED`); il calcolo è automatico
(PF-MCP-037) e il revisore lo rifà in modo indipendente.

**Certificato finale:** solo con D1–D5 al 100 % sui SHA congelati, nessun FAIL/BLOCKED/NOT_TESTED su
requisito obbligatorio, verdetto di un revisore diverso dall'esecutore, approvazione owner. Il 100 %
significa copertura completa dei requisiti applicabili e ratificati, non rischio zero.

## 6. Ancoraggio e invalidazione

La certificazione è legata a: SHA dei due repository · versione e schema hash del contratto ·
configurazione di prova · dataset (hash) · versione del catalogo test · evidenze. Qualsiasi modifica
rilevante dopo la certificazione (codice delle aree coperte, contratto, config di prova, dataset, catalogo)
impone una nuova valutazione; una certificazione non si «trascina» su un nuovo SHA.

## 7. Matrice di applicabilità dei riferimenti di controllo

Riferimenti usati come lista di controllo, **senza** dichiarare conformità o certificazione formale.

| Riferimento | Aree applicate | Dove è verificato |
|---|---|---|
| NIST SSDF (SP 800-218) | PO/PS/PW/RV: review indipendente, protezione del codice, test, gestione vulnerabilità | Q2–Q6, file protetti, secret scan |
| NIST SP 800-53 | AC (least privilege, separation of duties), AU (audit), CM (change management), CP (recovery), SI (integrità input) | PF-MCP-005/007/014/020/023, 034 |
| OWASP ASVS | V1 architettura, V2–V4 auth e accesso, V5 validazione, V7 log, V8 dati, V13 API | PF-MCP-004/005/023 |
| OWASP API Security Top 10 | API1 BOLA (ordini altrui), API2 auth, API3 proprietà eccessive (campi extra), API4 risorse (rate limit), API5 autorizzazione per funzione, API8 configurazione, API10 consumo di API upstream non fidate | campagna D |
| Four-eyes | doppia conferma MANUAL e azioni owner | PF-MCP-036 (K5 aperto) |

## 8. Ruoli

| Ruolo | Chi | Non può |
|---|---|---|
| Esecutore | Claude C (MCP), Claude B (core) | certificare il proprio lavoro |
| Revisore indipendente | istanza designata dall'owner (Grok; `independent-review` nel MCP) | essere l'autore |
| Dispatcher | #606 (quando attivo) | eseguire codice non fidato in corsia certification |
| Owner | approvazione, merge, mandati LIVE | essere sostituito da un commento di un agente (#472) |

Limite noto: oggi autore e reviewer pubblicano dallo stesso account (AGENTS.md MCP §4, #472);
l'indipendenza è garantita dal processo, non dall'identità. È un rischio residuo accettato dall'owner il
22/10 e va riportato in ogni dossier.
