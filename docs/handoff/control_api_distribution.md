# Distribuzione di `pickfair_control_api` verso Pickfair-nogui

Requisiti owner (04/11/2026): pin esatto della versione, verifica dell'integrità, nessuna
risoluzione dinamica delle dipendenze all'avvio. Il package usa **solo la libreria standard** e non
dichiara dipendenze: non c'è nulla da risolvere.

Strumento comune: `python scripts/build_control_api_wheel.py --out DIR` produce
- `pickfair_control_api-1.1.0-py3-none-any.whl` — **byte per byte riproducibile** (timestamp e
  permessi fissi, ordine dei file fisso, `RECORD` con SHA-256 di ogni file);
- `requirements-control-api.txt` — `pickfair-control-api==1.1.0 --hash=sha256:<sha della wheel>`;
- `control_api_manifest.json` — SHA-256 di ogni file e impronta complessiva dell'albero.

Provato da `tests/unit/test_control_api_distribution.py`: due build identiche; nessun file estraneo
(niente `pickfair_mcp`, niente `.pyc`); `RECORD` coerente; nessun `Requires-Dist`; installazione offline
con `--no-deps --no-index --require-hashes` riuscita; wheel con un bit alterato **rifiutata** dal pin;
manifest che cambia se cambia un solo file della copia.

In entrambe le opzioni il ponte del core verifica all'avvio `__version__ == "1.1.0"` e lo schema
hash atteso (`control_api/bridge.py`, `EXPECTED_*`): un package diverso non viene mai usato
(`CONTROL_API_NOT_STARTED: CONTRACT_PIN_MISMATCH`), e la Control API non parte.

## Opzione A — artefatto installabile con hash

```bash
# lato pickfair-mcp- (a uno SHA fissato):
python scripts/build_control_api_wheel.py --out dist/
# lato Pickfair-nogui (installazione, mai all'avvio del bot):
pip install --no-deps --no-index --require-hashes --find-links dist/ -r requirements-control-api.txt
```

| | |
|---|---|
| Vantaggi | un solo codice sorgente (nessuna copia che diverge); integrità verificata da pip con l'hash; rebuild riproducibile da chiunque allo stesso SHA; nessuna dipendenza transitiva |
| Rischi | nuova voce in un manifest di dipendenze del core (supply chain ⇒ merge owner); serve un canale per portare la wheel nel packaging Windows/Linux; installazione dimenticata ⇒ `PACKAGE_MISSING` (sicuro: Pickfair parte senza API) |
| Aggiornamento | nuova versione del contratto ⇒ nuova wheel, nuovo hash in `requirements-control-api.txt` e nuovi `EXPECTED_*` nel ponte, nello STESSO cambio del core; versione vecchia ⇒ pin mismatch, mai uso silenzioso |

## Opzione B — copia vendorizzata con manifest

La copia di `src/pickfair_control_api/` viene messa nel core (per esempio `third_party/pickfair_control_api/`)
insieme a `control_api_manifest.json`; un test del core ricalcola le impronte e fallisce se un file
differisce o se l'impronta dell'albero non coincide con quella pubblicata da pickfair-mcp-.

| | |
|---|---|
| Vantaggi | nessun manifest di dipendenze toccato; nessun passo di installazione; il packaging (PyInstaller/AppImage) lo include come codice del core |
| Rischi | due copie dello stesso codice: una correzione nel MCP non arriva al core finché non si ricopia; modifiche locali alla copia vietate (il test le blocca, ma va mantenuto); codice di un altro repository dentro il core |
| Aggiornamento | ricopia completa + nuovo manifest + nuovi `EXPECTED_*`, in un unico cambio; mai patch parziali alla copia |

## Raccomandazione tecnica

**Opzione A** per il primo rilascio: un solo sorgente, integrità verificata due volte (hash della wheel
all'installazione, versione e schema hash all'avvio), nessuna copia da mantenere. L'opzione B resta la
scelta se l'owner preferisce non aggiungere voci ai manifest di dipendenze. La decisione spetta
all'owner (dipendenze e supply chain sono a merge owner nella governance del core).

## Valori correnti

| Voce | Valore |
|---|---|
| Versione package / contratto | 1.1.0 |
| Schema hash | `e9471531792d74337f03a3014e84364994fe76b25e28c6fab4b5ea117df9d4b6` |
| Wheel SHA-256 | ricalcolato dal dossier di certificazione allo SHA del repository |
| Impronta dell'albero (manifest) | ricalcolata dal dossier di certificazione allo SHA del repository |
