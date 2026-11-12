# Handoff a Claude B — MCP-01l: mercati e book in sola lettura

Da: Claude C · Per: Claude B · 05/11/2026 · **dipende da MCP-01d … MCP-01k**. `Roadmap-Card: none`.
Mandato owner del 05/11/2026 («completare le funzionalità read-only ancora mancanti»). Route già approvate,
nessuna route K3. In coda dietro le correzioni P0/P1.

**Ordine della catena MCP:** 01d → … → 01k → **01l** → 01i. MCP-01i (che dipende da F-04) va dopo 01l e sarà
ripinnato al contratto successivo prima dell'integrazione.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01l.patch`, 8 file, +433/−3, SHA-256 `815bcb50cdb9816062d3cecca9fb75e0bbee1ca0b7be770ad8014e5730d6f17c` |
| Base della patch | `main` `ada40765` + patch MCP-01d … 01h, 01j, 01k |
| Package | `pickfair_control_api` **1.8.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01l-markets` |
| Contratto | 1.8.0, schema hash `0bb7355fc5476f80f2e5c2c6865bba97eac2c9cc7bcab96620c8ddf347991309` |
| Scope del core | `pf_api9_control_api_markets` (8 file = diff) |

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

| Prova | Esito |
|---|---|
| Test core nuovi (`test_market_views.py`, book reali da `MarketTracker.on_market_book`) | 8 passed; `tests/control_api` 213 passed |
| Route con parametro sul server reale (`tests/control_api/test_market_routes.py`) | 22 passed: id valido passato al provider; 14 forme non valide (`..`, `%2e%2e`, risalite, lettere, lunghezze, query, barra finale) → 404 senza chiamare il core; token e metodi |
| Mutazioni `control_api` | 90/90 KILLED, GATE PASS. Primo giro 90/91: sopravvissuto `cap_book_string_number`, **equivalente** (il controllo di tipo era ridondante: `decimal_str` rifiuta già stringhe e bool); controllo ridondante e mutante rimossi |
| Mutanti critici MCP N01–N06 | 6/6 KILLED. Primo giro 5/6: N05 (id non validato nell'adapter HTTP) sopravvissuto, lacuna reale; test aggiunto, N05 ucciso |
| E2E fra processi | 15/15, su 3 esecuzioni (book entrato dal percorso reale dello stream nel core in SIM; NOT_TRACKED; nessun effetto) |
| Suite MCP | 1781 passed, 16 skipped (+6 test dell'adapter dopo N05) |
| Regressione completa del core (`pytest -n 4 tests`) | 11994 passed, 0 failed, 16 skipped, 56 xfailed |
