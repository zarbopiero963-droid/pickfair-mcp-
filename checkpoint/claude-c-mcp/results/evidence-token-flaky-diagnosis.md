# MCP-TOKEN-TEST-FLAKY — diagnosi (codice congelato 869d2c0, ambiente isolato)

Test: `tests/control_api/test_tokens.py::test_concurrent_processes_never_read_a_partial_token`.
- Meccanismo: 3 processi lettori (`LocalTokenFile.read`, 2000 letture ciascuno) e, nel processo del test, rotazioni
  continue (`TokenStore.rotate`: file temporaneo O_EXCL 0600, `fsync`, `os.replace`) finché i lettori sono vivi.
- Proprietà di sicurezza provata: nessuna lettura parziale o malformata (`BAD 0`).
- Asserzioni aggiuntive, che dipendono dai tempi: `rotations >= 20` e `distinct >= 2` per ogni lettore.

## Prove

| Condizione | Esecuzioni | Fallite | Asserzione | Letture parziali o malformate |
|---|---|---|---|---|
| Riposo (replica diagnostica) | 5 | 0 | — (144–277 rotazioni, rotate 0,25–0,45 ms medi) | 0 |
| Riposo (test vero) | 15 | 0 | — | 0 |
| CPU satura, 8 processi (test vero) | 12 | 0 | — | 0 |
| Carico fsync, 6 processi (replica) | 10 | 7 | ROTATIONS<20 (6–17 rotazioni), DISTINCT<2 | 0 su 60.000 letture |
| Carico fsync, 6 processi (test vero) | 8 | 5 | `assert 14/15/18 >= 20` | 0 |
| 3 suite complete in parallelo (condizione della campagna) | 9 | 0 | — | 0 |
| Campagna 540a932, primo avvio (evento originale) | 3 baseline | 1 | non registrata: il driver salva solo l'id del test | — |

Sotto carico di fsync, `rotate` sale a 1,7–13 ms medi e fino a 19 ms al massimo. I lettori finiscono le 2000
letture prima delle 20 rotazioni.

Identità dei processi: per ogni esecuzione della replica sono registrati il pid di ogni lettore, l'inizio e la
fine (monotonic), le letture, i token distinti e i codici di errore. Non c'è nessun errore in nessun lettore.

## Classificazione

**Difetto del test** (soglia di tempo), non del codice. La proprietà verificata dal test, nessuna lettura
parziale di un token durante la rotazione, ha retto in tutte le prove, comprese quelle sotto carico.

Limite: l'asserzione del fallimento originale non è stata registrata. Che sia la stessa soglia è l'ipotesi più
probabile, perché è l'unico modo di fallire riprodotto, ma non è provato.

## Correzione proposta (NON applicata al branch congelato)

- Patch: `proposed_test_fix.patch` (sha256 `f8c1abf8…653914`), solo `tests/control_api/test_tokens.py`.
- I lettori si fermano a una condizione, non a un tempo: almeno 2000 letture **e** almeno 3 token distinti,
  con una scadenza di 60 s solo come rete.
- Asserzioni nuove: `rotations >= 2`, `reads >= 2000`, `distinct >= 3`. `BAD 0` resta invariata.

Verifica nel worktree di diagnosi:
- sotto carico fsync, 10 PASS su 10 (il test attuale cedeva 5 volte su 8);
- con una scrittura del token non atomica (troncamento sul posto e scrittura in due metà), il test corretto
  FALLISCE 3 volte su 3 con `TOKEN_FILE_MALFORMED`: continua a vedere le letture parziali.

Stato: **APERTO**. Classificato come difetto del test, con correzione proposta. Si applica solo in una consegna
autorizzata dopo il congelamento.
