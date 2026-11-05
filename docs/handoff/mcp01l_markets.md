# Handoff a Claude B — MCP-01l: mercati e book in sola lettura

Da: Claude C · Per: Claude B · 05/11/2026 · **dipende da MCP-01d … MCP-01k**. `Roadmap-Card: none`.
Mandato owner del 05/11/2026 («completare le funzionalità read-only ancora mancanti»). Route già approvate,
nessuna route K3. In coda dietro le correzioni P0/P1.

**Ordine della catena MCP:** 01d → … → 01k → **01l** → 01i. MCP-01i (che dipende da F-04) va dopo 01l e sarà
ripinnato al contratto successivo prima dell'integrazione.

## 1. Artefatti

Patch, SHA e contratto: vedi il commento di consegna su pickfair-mcp- #37 e `core_bridge_mcp01l.patch.sha256`.

## 2. Cosa cambia nel core

| File | Modifica |
|---|---|
| `control_api/views.py` | `markets_view`, `market_book_view` dal `MarketTracker` (copia unica del dizionario dei book); tre livelli per lato, Decimal, runner illeggibili contati; `NOT_TRACKED` per un mercato non seguito |
| `control_api/bridge.py` | provider `markets` e `market_book` (quest'ultimo riceve l'id già validato dal server); pin 1.8.0 |
| `tests/control_api/test_market_views.py` | book reali entrati da `MarketTracker.on_market_book`; valori illeggibili mai zero; tracker assente; id non validi; troncamento; nessun effetto; contratto del server |
| `tests/control_api/test_side_effects.py` | `/v1/markets` e `/v1/markets/{id}/book` nelle letture senza effetti e nel martellamento |
| `guardrails/mutation_catalog.json`, `docs/control_api.md`, `CHANGELOG.md`, `.guardrails/allowed_scope.json` | mutazioni, documentazione, scope `pf_api9_control_api_markets` |

## 3. Limiti dichiarati

- Il `MarketTracker` non registra l'istante di ricezione: l'età del book è nota solo con `lastMatchTime`
  (richiesta non bloccante a Claude D: un timestamp di ricezione per mercato).
- `book_status` è il dato Betfair, non il giudizio di negoziabilità (F-23, protezione `market_tradability`).
- `GET /v1/events` resta 501: il core non ha un catalogo degli eventi senza chiamate di rete.

## 4. Evidenze

Vedi il commento di consegna su #37.
