#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

ADATA="${ADATA:-data/matrix/baron_pancreas_labeled.h5ad}"
TAG="${TAG:-baron_pancreas}"
N_TOP="${N_TOP:-25}"
SKIP_PREPARE="${SKIP_PREPARE:-0}"

if [[ "$SKIP_PREPARE" != "1" ]]; then
  python scripts/prepare_baron_pancreas_h5ad.py --output "$ADATA"
fi

ADATA="$ADATA" \
TISSUE=Pancreas \
TAG="$TAG" \
GROUPBY=cell_type \
LABEL_KEY=cell_type \
ONTOLOGY_KEY=cell_ontology_id \
N_TOP="$N_TOP" \
NO_NORMALIZE=1 \
bash scripts/run_matrix_marker_benchmark.sh
