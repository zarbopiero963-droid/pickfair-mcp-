# Handoff a Claude B — MCP-SEC-01: irrobustimento di sicurezza della Control API

Da: Claude C · Per: Claude B · 05/11/2026 · **dipende da MCP-01d … MCP-01l**. `Roadmap-Card: none`.
Mandato owner del 05/11/2026, priorità 3 («verificare autenticazione, autorizzazioni, isolamento dei segreti e
protezione contro operazioni non consentite»).

## 1. Metodo

Revisione di sicurezza **indipendente** (un revisore separato, solo lettura, che ha ricevuto il codice e non le
mie conclusioni) del package `pickfair_control_api` e del server MCP, con una riproduzione eseguibile per ogni
rilievo. Esito: nessun bypass dell'autenticazione, nessun percorso di scrittura o comando, nessuna fuga di token
o di testo d'eccezione verso un client. Quattro debolezze reali riprodotte, corrette qui con test RED → GREEN; una
quinta (codici del core che arrivano all'agente) è rischio residuo by-design, dichiarato nel contratto.

## 2. Cosa cambia

Quasi tutto nel package (repository pickfair-mcp-, `src/pickfair_control_api/`): `tokens.py` (token deboli
rifiutati, rotazione serializzata) e `server.py` (tetto di 16 connessioni, scadenza di 10 s per connessione,
errori di protocollo in JSON fisso, nessun traceback). Nel core cambia solo il **pin** del ponte (1.9.0) più
documentazione e scope (`pf_api10_control_api_security`): patch `core_bridge_mcpsec01.patch`, 4 file, +24/−2.

## 3. Evidenze

Vedi il commento di consegna su pickfair-mcp- #37 (RED, GREEN, mutanti X01–X06, suite, E2E, regressione).

## 4. Effetto sull'integrazione

Il ponte rifiuta un package diverso da quello pinnato: la patch va applicata con il package 1.9.0. Un core che
costruisce `TokenStore` da un valore esterno debole ora fallisce all'avvio (`WeakTokenError`) invece di servire
un'API di fatto senza autenticazione: comportamento voluto (fail-closed).
