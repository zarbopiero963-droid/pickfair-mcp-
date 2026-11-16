#!/bin/sh
# PR-18 (PF-OWNER-MCP-PR18-DRAWDOWN-VIEW-20261116): ricostruisce l'albero del core con il ponte 1.16
# e la correzione della vista drawdown. Nessun commit nel core: tutto avviene in <destinazione>.
# Uso: pr18_build.sh <clone Pickfair-nogui> <destinazione> [base|fix]
#   base = core + ponte 1.16 (albero del gate MCP-116, piu' i test del ponte): comportamento precedente
#   fix  = base + pr18_core_drawdown_view.patch (predefinito)
set -eu
CORE_REPO=$1; DEST=$2; MODE=${3:-fix}
HERE=$(cd "$(dirname "$0")" && pwd)
DELTA="$HERE/../crossrepo_mcp116/crossrepo_bridge_1_16_test.delta.patch"
PATCH="$HERE/pr18_core_drawdown_view.patch"
CORE_SHA=5daa6a51288bc7be69e663142a311cc729fd1cc1
BRIDGE_SHA=0a529035
case "$MODE" in base|fix) ;; *) echo "modo sconosciuto: $MODE" >&2; exit 2 ;; esac
git -C "$CORE_REPO" cat-file -e "$CORE_SHA^{commit}"
git -C "$CORE_REPO" cat-file -e "$BRIDGE_SHA^{commit}"
rm -rf "$DEST"; mkdir -p "$DEST"
git -C "$CORE_REPO" archive "$CORE_SHA" | tar -x -C "$DEST"
git -C "$CORE_REPO" archive "$BRIDGE_SHA" control_api tests/control_api | tar -x -C "$DEST"
cd "$DEST"; git init -q; git add -A
git -c user.email=pr18@local -c user.name=pr18 commit -qm "core $CORE_SHA + control_api e tests/control_api @ $BRIDGE_SHA"
git apply --check "$DELTA"; git apply "$DELTA"
git add -A; git -c user.email=pr18@local -c user.name=pr18 commit -qm "patch di prova ponte 1.16.0"
if [ "$MODE" = fix ]; then
  git apply --check "$PATCH"; git apply "$PATCH"
  git add -A; git -c user.email=pr18@local -c user.name=pr18 commit -qm "PR-18: vista drawdown dallo stato reale del core"
fi
echo "albero $MODE pronto: commit $(git rev-parse HEAD) tree $(git rev-parse HEAD^{tree})"
