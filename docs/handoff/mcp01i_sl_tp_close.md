# Handoff a Claude B — MCP-01i: stato della chiusura SL/TP (dipende da F-04)

Da: Claude C · Per: Claude B · 05/11/2026 · mandato owner del 05/11/2026, punto 2. `Roadmap-Card: F-04`.
**Preparato offline, NON integrabile finché F-04 (`claude/d-f04-sl-tp-close` @ `4c07f719`) non è su `main`.**
Dipende da MCP-01d … MCP-01k. Nessuna route nuova: estensione di `GET /v1/exposure`.

## 1. Artefatti

| Artefatto | Valore |
|---|---|
| Patch incrementale | `core_bridge_mcp01i.patch` (vedi `core_bridge_mcp01i.patch.sha256`) |
| Base della patch | `main` `ada40765` + patch MCP-01d … 01h, 01j, 01k + commit di F-04 (identici al branch di D) |
| Contratto | 1.8.0 |
| Scope del core | `pf_api8_control_api_sl_tp_close` (8 file = diff) |

## 2. Cosa espone (solo dati persistiti)

Tavolo, posizione (mercato, selezione, lato, betId), evento SL/TP, stato della chiusura (CLAIMED / ROUTED /
NOT_EXECUTED / UNCERTAIN, illeggibile UNKNOWN), ritentabile come decide il core, dettaglio/blocco come codice,
ordini della posizione (parzialmente abbinati, in riconciliazione, ambigui), esposizione residua dal tavolo che
porta ancora la posizione, hedge della selezione. Dettagli e limiti in `docs/contract_v1.md` (MCP-01i).

## 3. Evidenze

In compilazione: vedi il commento di consegna su pickfair-mcp- #37.
