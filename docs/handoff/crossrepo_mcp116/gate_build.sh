#!/bin/sh
# Ricostruisce l'albero del core per il gate crossrepo MCP-116 (nessun commit nel core).
# Uso: gate_build.sh <clone Pickfair-nogui> <destinazione> <delta.patch>
set -eu
CORE_REPO=$1; DEST=$2; DELTA=$3
CORE_SHA=c535c1d559f11fdab4f09fa02c04c7824d1d2a19
BRIDGE_SHA=0a529035
git -C "$CORE_REPO" cat-file -e "$CORE_SHA^{commit}"
rm -rf "$DEST"; mkdir -p "$DEST"
git -C "$CORE_REPO" archive "$CORE_SHA" | tar -x -C "$DEST"
git -C "$CORE_REPO" archive "$BRIDGE_SHA" control_api | tar -x -C "$DEST"
cd "$DEST"; git init -q; git add -A
git -c user.email=gate@local -c user.name=gate commit -qm "core $CORE_SHA + control_api @ $BRIDGE_SHA"
git apply --check "$DELTA"; git apply "$DELTA"
git add -A; git -c user.email=gate@local -c user.name=gate commit -qm "patch di prova ponte 1.16.0"
echo "albero pronto: $(git rev-parse HEAD)"
