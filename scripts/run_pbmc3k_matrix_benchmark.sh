#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ADATA="${ADATA:-data/matrix/pbmc3k_tutorial_labeled.h5ad}"
TAG="${TAG:-pbmc3k}"
N_TOP="${N_TOP:-25}"
SKIP_PREPARE="${SKIP_PREPARE:-0}"

if [[ "$SKIP_PREPARE" != "1" ]]; then
  python scripts/prepare_pbmc3k_tutorial_h5ad.py --output "$ADATA"
fi

ADATA="$ADATA" \
TISSUE=PBMC \
TAG="$TAG" \
GROUPBY=louvain \
LABEL_KEY=cell_type \
ONTOLOGY_KEY=cell_ontology_id \
N_TOP="$N_TOP" \
NO_NORMALIZE=1 \
bash scripts/run_matrix_marker_benchmark.sh
