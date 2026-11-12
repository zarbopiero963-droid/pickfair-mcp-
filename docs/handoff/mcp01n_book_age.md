# Handoff a Claude B — MCP-01n: età del book (`book_age_s`)

Da: Claude C · Per: Claude B · 05/11/2026. **Preparato offline, NON integrabile finché `claude/d-market-book-age`
(Claude D, `ea81e93e`, `MarketTracker.received_at` / `book_age_s`) non è su `main`.** Verificato sulla fusione locale
di `ea81e93e` sopra MCP-01m (il file `core/market_tracker.py` della fusione è identico a quello del branch di D).
Dipende da MCP-01d … MCP-01m, MCP-SEC-01, MCP-01i r2. Mandato owner del 05/11/2026, priorità 1-2.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01n.patch`, 7 file, +283/−4, SHA-256 `ebd7a2d544579583bd2cf3036a2618753abddff8ca1767f5ef75c708a405e83e`; commit sorgente locale `f22d6bfb521c742cbf08bbfc9895dd635b885e09` (clone del core mai spinto) |
| Base della patch | MCP-01m + fusione di `claude/d-market-book-age` |
| Package | `pickfair_control_api` **1.12.0** dal branch `ccr-edf04c7d-e7vtj1-mcp01n-book-age` |
| Contratto | 1.12.0, schema hash `10c5df547566aab57ab8b70e50545cc11e9ca24998c0938be93c2db14986dd9a` |
| Scope del core | `pf_api12_control_api_book_age` |

## 2. Cosa espone

Vedi `docs/contract_v1.md` (MCP-01n): `book_age_s` in `list_markets` e `get_market_book`, dall'istante monotono di
ricezione del tracker (nessun ricalcolo), letto prima dei book, `null` quando non dimostrabile. Chiude il limite
dichiarato in MCP-01l.

## 3. Evidenze

| Prova | Esito |
|---|---|
| Test core nuovi (`test_book_age_view.py`, `MarketTracker` reale con orologio monotono iniettato) | RED 8/9 senza le viste 01n → GREEN 9/9; con `test_market_views.py` 17 passed |
| Mutazioni `control_api` (8 nuove `cap_book_age_*`) | 119/119 KILLED, GATE PASS (primo giro INCONCLUSIVE: file di test non tracciato, quindi assente dalla sandbox) |
| Mutanti critici MCP Z01–Z04 | 4/4 KILLED |
| Test MCP unit/control_api/integration/guards | 1828 passed, 1 skipped (permessi da root) |
| E2E fra processi col core 01n (`PICKFAIR_CORE_BOOK_AGE=1`) | 17/17, su 3 esecuzioni |
| Suite MCP completa (con E2E sul core 01n) | 1886 passed, 1 skipped |
| Regressione completa del core (fusione 01m + `ea81e93e` + 01n) | 12908 passed, **2 failed, entrambi preesistenti e indipendenti dalla patch**: (a) `test_il_catalogo_reale_e_applicabile_e_copre_le_aree_critiche` (stack F-13b/F-02 di D, già noto in 01m); (b) `test_every_test_directory_and_module_is_reachable_from_the_catalog`, che arriva col catalogo canonico di `main` (#606) incluso nel branch di D: lì mancano `tests/f02`, `tests/f03`, `tests/f13b` e `tests/f18` (di D) e anche `tests/control_api` (il ponte). Per `tests/control_api` la soluzione è la voce G8 `control-api` più l'id in `campaigns.all` (provato: sparisce dall'elenco; vedi `docs/g8/G8_MCP_CONTROL_API_SUITES.md` sul branch g8, `e029363`) |
| Lint | nessun errore ruff nuovo rispetto a 9958c75; mypy invariato (10 errori preesistenti) |

## 4. Stato della consegna

`DELIVERED`, non integrato. Una patch consegnata non equivale a codice su `main` (decisione owner del 05/11/2026).
