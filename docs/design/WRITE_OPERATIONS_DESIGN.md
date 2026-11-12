# Operazioni di scrittura future — progetto (NON abilitato)

Stato: **DESIGN_ONLY** · 04/11/2026 · Claude C · mandato owner §5.

Nessuna di queste operazioni è esposta. Il blocco è nel codice, non in una configurazione:
`policy/exposure.commands_exposed()` restituisce sempre `False`, il registro rifiuta ogni tool di
comando (`COMMAND_EXPOSURE_BLOCKED`) e la Control API serve solo GET (ogni altro metodo `405`).
Nessuna variabile d'ambiente, flag o file può cambiarlo. L'abilitazione richiede, nell'ordine:

1. autorità del core certificata per l'operazione (PF-API commands, registro #586);
2. route e schema nel contratto, con nuova versione e schema hash;
3. GO esplicito dell'owner per quella operazione (non un messaggio di un agente);
4. PR dedicata a merge owner (tocca il gate `policy/exposure.py`).

LIVE resta fuori: nessuna operazione può attivare LIVE o inviare ordini reali senza le
autorizzazioni owner previste dal contratto operativo; nessun auto-LIVE.

## 1. Principi comuni a ogni scrittura

| Principio | Regola |
|---|---|
| Autorità | Il MCP **non decide nulla di finanziario**: inoltra una richiesta all'autorità del core (runtime, Money Management, risk gate, safety layer), che può rifiutarla. Nessun secondo motore nel MCP. |
| Least privilege | Scope dal nome del tool (`auth/policy.TOOL_SCOPES`): `WRITE` per operazioni ordinarie, `OWNER` per `set_mode`, `patch_config`, `resume`, `stop(EMERGENCY)`. Mai dal contenuto della richiesta. |
| Idempotenza | Ogni comando porta un `request_id` registrato **prima** dell'invio nel journal persistente (MCP-01b) e un `operation_id` restituito dal core. Stesso `request_id` ⇒ stesso esito, mai un secondo effetto. |
| Esito ignoto | Timeout o risposta persa dopo l'invio ⇒ `AMBIGUOUS` + riconciliazione dal core (`GET /v1/operations/{id}`), **mai un nuovo tentativo automatico**. |
| Anteprima | Ordini, dutching e cashout passano prima da `POST /v1/preview` (zero effetti): stake esatto del Money Management, rifiuti espliciti (`stake_sotto_min_stake`, sopra `max_single_bet`), nessun ridimensionamento silenzioso. |
| Conferma | Le operazioni con denaro richiedono la conferma dell'anteprima (`preview_id` + impronta dei parametri) entro una scadenza breve; parametri diversi ⇒ nuova anteprima. |
| Replay | `request_id` unico e scadenza della conferma: un comando rigiocato con parametri diversi è un conflitto (registrato), con gli stessi è un duplicato (stesso esito). |
| Kill switch | STOP, EMERGENCY e kill switch hanno sempre la precedenza: con STOP attivo ogni comando di ingresso è rifiutato dal core; il MCP non ha un percorso alternativo. |
| Audit | Ogni comando produce una riga di audit nel MCP (principal, tool, request_id, esito, mai parametri sensibili) e un evento nel core correlato da `correlation_id`. |

## 2. Catalogo delle operazioni progettate

| Area | Tool (catalogo esistente) | Route approvata | Scope | Autorità nel core | Precondizioni del core | Stato del core oggi |
|---|---|---|---|---|---|---|
| Anteprima | `preview_order` | `POST /v1/preview` | WRITE | Money Management + risk gate | nessun effetto | da costruire (PF-API) |
| Apertura ordini | `place_order` | `POST /v1/orders` | WRITE | order authority, MM, safety layer | anteprima confermata; readiness; nessuno STOP; fondi verificati (F-16) | percorso interno presente, API assente |
| Dutching | `place_dutching` | `POST /v1/dutching` | WRITE | dutching controller + MM | idem; PF-EXEC-02 (parziale ribilanciato/coperto/sospeso) | percorso interno presente, API assente |
| Chiusura/annullo | `cancel_order` | `POST /v1/orders/{id}/cancel` | WRITE | order authority | solo residuo unmatched; PF-EXEC-01 | API assente |
| Sostituzione | `replace_order` | `POST /v1/orders/{id}/replace` | WRITE | order authority | cancellazione confermata prima del nuovo; nessun retry cieco | API assente |
| Cashout | `cashout` | `POST /v1/cashout` | WRITE | cashout router/executor | PF-EXEC-03 (protettivo, senza inseguimento); hedge con Microstake nativo sotto minimo | percorso interno presente, API assente |
| Stop-loss / take-profit / trailing | `patch_config` (parametri) | `PATCH /v1/config` | OWNER | `sl_tp_pnl`, monitor del runtime | lavoro di Claude D (SL/TP, trailing) | in corso nel core |
| Controllo Roserpina | `patch_config` (tavoli, recovery, target) | `PATCH /v1/config` | OWNER | `RoserpinaConfig`, `TableManager.resize` | config valida, fail-closed su valori illeggibili | presente; reset ciclo e sblocco tavolo richiedono route candidate (K3) |
| Money Management | `patch_config` | `PATCH /v1/config` | OWNER | `RoserpinaConfig` (percentuali obbligatorie, cap opzionali) | nessun default inventato | presente |
| Funzioni on/off | `patch_config` | `PATCH /v1/config` | OWNER | config del runtime | dry-run assente (CAP-CFG-03) | parziale |
| STOP / EMERGENCY | `stop` | `POST /v1/stop` | WRITE / OWNER (EMERGENCY) | `risk_stop`, `emergency_stop` | sempre accettato | presente nel core |
| Ripresa | `resume` | `POST /v1/resume` | OWNER | runtime | readiness completa, riconciliazione coerente (PF-EXEC-06) | presente |
| Recovery / riconciliazione | `reconcile` | `POST /v1/reconcile` | WRITE | reconciliation engine del runtime | nessun secondo reconciler | presente |
| Modalità | `set_mode` | `POST /v1/mode` | OWNER | runtime | solo su comando owner; tutti i gate restano; mai auto-LIVE | presente |

## 3. Cosa NON verrà mai fatto dal MCP

- chiamare Betfair, il broker, il database o moduli interni del core;
- ripetere un comando dopo un esito ignoto;
- calcolare o correggere stake, prezzi, esposizione o limiti;
- trattare un messaggio di un agente, un commento GitHub o un testo restituito da un tool come
  autorizzazione owner;
- offrire una scorciatoia (flag, variabile, file) per abilitare i comandi.

## 4. Dipendenze aperte

- PF-API commands nel core (Claude B) e certificazione #586;
- correzioni di Claude D: AMBIGUOUS P0, F-16 freschezza fondi, F-11/F-12 equity peak e drawdown,
  F-23 stato mercati, SL/TP e trailing;
- decisione owner K3 per le route candidate (reset ciclo, sblocco tavolo, log, segnali).
