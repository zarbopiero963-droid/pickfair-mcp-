# Consegna cross-repository delle patch del motore di Claude C (PF-MCP-CROSS-REPO-HANDOFF-01)

Da: Claude C · Per: Claude B · 05/11/2026 · decisione owner **opzione A**: branch di handoff durevole su
`zarbopiero963-droid/Pickfair-nogui`, pubblicato da Claude B dopo la verifica SHA-256. Questo file contiene **solo
metadati**: nessun codice del motore è nel repository MCP.

## Stato

Tutte le patch sono **`DELIVERED`**: non pubblicate e non integrate. Una patch consegnata non vale come integrata, e la
pubblicazione del branch di handoff non vale come integrazione su `main`. Finché B non pubblica il branch, i commit
sorgente esistono solo nel workspace locale di Claude C e **non sono dichiarati recuperabili**. Lo stato del checkpoint
resta `NEEDS_RECONCILIATION`.

## Artefatti consegnati all'owner (per Claude B)

| Artefatto | SHA-256 |
|---|---|
| `claude-c-core-handoff.bundle` (git bundle, 12 ref `refs/heads/claude-c-handoff/mcp*`) | `82b056e4289b0aa41d87beb98d9c0a092f72dbe79237d58b757cbe562a7efdad` |
| `core_bridge_mcp<inc>.full-index.patch` (12 file, forma canonica) | tabella sotto |

Prerequisiti del bundle, tutti pubblicati su GitHub: `ada40765` (main), `65a84f56` (`claude/d-f03-trailing-stop`),
`ea81e93e` (`claude/d-market-book-age`).

Pubblicare dal bundle conserva **gli stessi SHA** dei commit sorgente: il commit di handoff coincide con il commit
sorgente, e i riferimenti del checkpoint di C diventano risolvibili.

Il bundle contiene anche tre commit di F-04 di Claude D come erano al momento della fusione locale (`adf4271f`,
`7fae4755`, `772ab581`). D li ha poi riscritti in `aa7959a8`, `4c07f719`, `2d0cf4ca`: la base di 01i-r2 non è più
raggiungibile da nessun branch remoto, quindi viaggia nel bundle.

## Patch

`base` e `source` sono SHA completi; il tree è quello del commit sorgente. Digest canonico =
`git diff --binary --full-index <base> <source> | sha256sum`.

| Incremento | base | source (commit di handoff) | tree della sorgente | SHA-256 canonico | SHA-256 consegnato prima (abbreviato) | file, righe |
|---|---|---|---|---|---|---|
| MCP-01d | `ada40765e7949b8deb7661b3b5e9ddc8484adba3` | `ae17bb8e03498d3941831de98291a252332a3483` | `e43b9380cdd493922dd7938e3d62fd1401870614` | `96d54331feab9d47eaefa3db3f16ccab6253f35f93e6fd31ed9d8e84864d1d7f` | `505f579c48493881d79a138bff77d02366e33c35dd31dfd93139920c9d3c7d0c` | 14 files changed, 1615 insertions(+), 1 deletion(-) |
| MCP-01e | `ae17bb8e03498d3941831de98291a252332a3483` | `b8b26434c37a03a9e5a165ebe9849ca995ab3a28` | `d8c1bb1cd72490918121d68f1b22ff13f3b6d2a6` | `7e241cc4eeda36ef09fd169135164b404aeef547a02270e9021c31f46e83d266` | `39833bc317daacec037e4ca4c2f7758eb89e9043f6648c6e2faccbad04005bc4` | 8 files changed, 735 insertions(+), 8 deletions(-) |
| MCP-01f | `b8b26434c37a03a9e5a165ebe9849ca995ab3a28` | `211374dca220bd6d8b5a2d43f17fa97a9874f234` | `0e9b5e9bfd145753488d8ad3b68ecc4e7be7f6e0` | `1cadea449582c28801c918920d5320c1158297559d2422e54b8955fc20704afd` | `5b847d946e18579d9e2a7c2c2e1afad5425cdfc95e92f2a3115b47ca5cf0fe74` | 9 files changed, 1147 insertions(+), 6 deletions(-) |
| MCP-01g | `211374dca220bd6d8b5a2d43f17fa97a9874f234` | `1bcfd7e1f597ffba893969e5459bdf5ec4700f7e` | `0ce978f8e3ee4ee08b88a73db5b54e489b6a23b7` | `f32f89fad534e44535b10ce9f66e956383e76bdda30d4ae828419874cd3999fd` | `aa89bc71f6e28b28e1fc1d93b9b74fb6ae153ba6922d6bf4326a675165ce131c` | 8 files changed, 838 insertions(+), 2 deletions(-) |
| MCP-01h | `1bcfd7e1f597ffba893969e5459bdf5ec4700f7e` | `0a894c4d4b43f21862e7346c4ebccb32d6631e12` | `27e41ec69f79875e68562503b09698459595b009` | `3bbce12ebc4dd3d27a6d1dae576edbd5aa7f6bdaedb3f00683a6ed3dec94a808` | `fbfa5210ba7a44fb59c8326e2c2a6d08bd24ce2bd4c508788028d476c0b2388e` | 10 files changed, 519 insertions(+), 4 deletions(-) |
| MCP-01j | `0a894c4d4b43f21862e7346c4ebccb32d6631e12` | `05372f4e4939181a0b446d22a0482855f5aaaa4c` | `c11e684c7bd3e6b0a91dd0f37a494b6560aeea6d` | `f7662028db3b300df7923222b492d2298239ca37e5dee2b4040d71b4a99713c3` | `85fcfd7687d7cfd9e9cfaff9825faf2aabf4cd28febc1e842462d58cc61cd8de` | 8 files changed, 521 insertions(+), 2 deletions(-) |
| MCP-01k | `05372f4e4939181a0b446d22a0482855f5aaaa4c` | `190789d5a5e55ad32a6c11ff2a4f4c350669943b` | `398b86249d39f81a75d295af0e634ba19f462246` | `4d05830a118898d652e104b6a3b55b4461b4f1c40387a1b27104040eeec9e54f` | `7e29ca8b7f1b33547a9f6274f304c6d6dda550eef2430f22ab27298c01562bdc` | 7 files changed, 212 insertions(+), 4 deletions(-) |
| MCP-01l | `190789d5a5e55ad32a6c11ff2a4f4c350669943b` | `210ac9ad954db94a5c3636a1a0903eef6a6d1a63` | `f5857cdbf49d66f3c101c1415a2321a06729f070` | `f34cde8cedd038dca39d41edbf1fd89cfa2690a7cea482bc222decd0f5f531aa` | `815bcb50cdb9816062d3cecca9fb75e0bbee1ca0b7be770ad8014e5730d6f17c` | 8 files changed, 433 insertions(+), 3 deletions(-) |
| MCP-sec01 | `210ac9ad954db94a5c3636a1a0903eef6a6d1a63` | `4525b28cbb057319d11db6d5b449b2c0205b47d9` | `61b95c42d55500c397a42e0790b694dc3573fe8f` | `7f6286d967555a10c337266b3ef01291ce8a0372580e71bda66b4c3bb5356d92` | `a0f6d249a57e124666cd1763ced6a8957cb4c765b483bbcf163f432c4f47d254` | 4 files changed, 24 insertions(+), 2 deletions(-) |
| MCP-01i-r2 | `772ab58152b9bde7ce4a6ca88a4face72bd25b0c` | `044af41d78d78053b9ab1249b22cc6ff29a5c52c` | `65c1aae29b17a86de29246ea47b4306dedc11ae3` | `ab38b7d5bc6d700cd61d19bcf59f976f426e89e549562b20a7012b2080df134f` | `5fe5b25b032c5f481864aa0bcaf562b5f5a17d69c1c3e0476f28a4462822f6f4` | 8 files changed, 578 insertions(+), 4 deletions(-) |
| MCP-01m | `a0a6013738aaee7b4c281e524eb014c02246dded` | `0dca9d58a28b8a4e9b85449928906a6b08f35f1b` | `4e9779049f2794f5b9d0caae757bfda370aaa8f1` | `9d2de2d9574beef2637a97d2bb659908cfa6813c1595931dd4df55092e6e7532` | `0c877b9aac0c824224ca01d226d6d8ed8d6648e19f06d13c42a0c3bdd6bb83cb` | 11 files changed, 467 insertions(+), 33 deletions(-) |
| MCP-01n | `2ea5187a9fad9a1b9cacfa310269bda45f89b3ba` | `f22d6bfb521c742cbf08bbfc9895dd635b885e09` | `dd759ec1f3e42f41341b948b3d27e47b54586118` | `c2029073346920532cd054bf74b4e27f48fe1386cf9e7ae366502fbfd0ed9a53` | `ebd7a2d544579583bd2cf3036a2618753abddff8ca1767f5ef75c708a405e83e` | 7 files changed, 283 insertions(+), 4 deletions(-) |

## Prova di riproducibilità (05/11/2026)

Clone nuovo da GitHub (`--filter=blob:none`) più i branch prerequisiti; `git bundle verify` OK; fetch del bundle.
I 12 ref puntano agli stessi SHA. Per ogni patch:
- il digest canonico è identico nel clone nuovo e nel clone locale (12/12 REPRO);
- il contenuto è identico a quello consegnato prima, righe `index` escluse (12/12 SAME).

**Difetto corretto qui.** I digest consegnati prima venivano da `git diff` senza `--full-index`. Le righe `index`
abbreviano gli hash a una lunghezza che dipende dal numero di oggetti del repository: 8 caratteri nel clone di C, 7
in un clone nuovo. Erano quindi riproducibili solo nel clone di C. Il contenuto non cambia; da ora vale il digest
canonico.

## Verifiche richieste a Claude B (decisione owner, punto 2)

1. SHA-256 del bundle e delle patch contro questa tabella; provenienza: questo file, `pickfair-mcp- #37`.
2. `git bundle verify` e fetch; ogni ref allo SHA indicato; `git rev-parse <source>^{tree}` uguale alla colonna tree.
3. Per ogni patch, `git diff --binary --full-index <base> <source> | sha256sum` uguale al digest canonico.
   È la verifica indipendente che il codice consegnato corrisponda a quello pubblicato.
4. Pubblicare il branch di handoff dedicato, conservarlo fino alla riconciliazione e registrarne SHA e tree.
   Nessuna PR concorrente; l'integrazione su `main` passa solo da PR e gate.

Le dipendenze fra incrementi e da D sono nei singoli handoff `docs/handoff/mcp01*.md`. 01i-r2, 01m e 01n non sono
integrabili finché F-04, F-03 e `claude/d-market-book-age` non sono su `main`.
