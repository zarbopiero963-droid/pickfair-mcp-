# K3 — specifiche offline di tre route di LETTURA candidate (non ratificate, non servite)

Mandato owner del 05/11/2026, punto 4: «Non implementare nuove route non ratificate. Puoi prepararne
specifiche e test offline senza attivarle, separandole dalle funzionalità già autorizzate.»

**Stato: `K3_DRAFT_NOT_RATIFIED_NOT_SERVED`.** Nessuna di queste route è nel contratto (`APPROVED_ROUTES`,
25 route), nel descrittore, nel catalogo dei tool, nel registro MCP o nel ponte del core. Le bozze di schema
stanno in `docs/design/k3/`, fuori da `src/`, e i test in `tests/k3_offline/` provano che restano inattive
(la Control API risponde 404, il MCP non ha un tool). Attivarle richiede la ratifica owner in un unico atto
(conflitto K3, `docs/roadmap/MASTER_ROADMAP_MCP_CONTROL_API.md`), poi un incremento normale con contratto
versionato, ponte del core, test, mutazioni ed E2E.

Le route di **scrittura** candidate (RC-01 START, RC-02 reset ciclo, RC-03, RC-06 sblocco tavolo) restano fuori:
le scritture finanziarie sono solo design (`docs/design/WRITE_OPERATIONS_DESIGN.md`).

## RC-10 `GET /v1/signals` — esito dei segnali (CAP-SIG-02, CAP-SIG-04)

| Campo | Fonte nel core (`main` `ada40765`) | Stato della fonte |
|---|---|---|
| `last_signal_at` | `RuntimeController.last_signal_at` (stringa ISO, `runtime_controller.py:4548`) | presente |
| `decisions` (approvato/rifiutato, motivo come codice, mercato, selezione) | eventi `SIGNAL_APPROVED`/`SIGNAL_REJECTED` sul bus | **non persistiti**: servirebbe un registro limitato nel core (Claude D) |
| `queue_depth` | `core/signal_queue.py` | **non raggiungibile** dal runtime |

Bozza: `docs/design/k3/rc10_signals.schema.json`. Oggi solo `last_signal_at` sarebbe dimostrabile; gli altri
campi sarebbero `unavailable`. Raccomandazione: ratificare solo insieme al registro persistito nel core.

## RC-11 `GET /v1/pnl` — storico P/L dei settlement (CAP-SET, inventario area 10)

| Campo | Fonte | Stato |
|---|---|---|
| `settlements[]` (istante, esito, tavolo, mercato, betId, P/L, realizzato) | tabella `settlement_effects` (`database.py:467`), lettura `mode=ro` + `query_only` come `/v1/orders` | presente; `customer_ref`, `event_key`, `payload_json` mai esposti |

Bozza: `docs/design/k3/rc11_pnl.schema.json`. Alternativa OWN-MCP-02F (estendere una route esistente): filtro
`cleared` di `GET /v1/orders`; ma il P/L di settlement non è una proprietà dell'ordine, quindi la route dedicata
rappresenta meglio la risorsa. Decide l'owner.

## RC-12 `GET /v1/logs` — log e audit con redazione (CAP-AUD-02)

| Campo | Fonte | Stato |
|---|---|---|
| `entries[]` (istante, tipo, severità, codice, correlation_id) | `audit_events`, `order_events` (`Database.get_recent_audit_events_for_diagnostics`, `database.py:2560`) | presente; **testo libero mai esposto** (solo codici), segreti redatti (`core.redaction`), `redacted` contato |
| filtri e paginazione | — | `next_cursor` opaco; da progettare con Claude B (nessun indice per `correlation_id`) |

Bozza: `docs/design/k3/rc12_logs.schema.json`.

## Regole comuni delle bozze

Le stesse dei contratti in vigore: schema chiuso (`additionalProperties: false`), importi come stringhe
decimali, identificativi con pattern, codici MAIUSCOLI e mai testo libero, `observed_at`, valori mancanti null
e dichiarati (mai zero), elenchi limitati con `omitted`/`truncated`.

## Sezione 13 dell'inventario (stato suite e certificazione)

Non è stato del runtime Pickfair: registro #586 e CI vivono su GitHub. Raccomandazione: lettura fuori banda
(nessuna route), salvo diversa decisione owner.
