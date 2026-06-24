#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

: "${ADATA:?Set ADATA=/path/to/dataset.h5ad}"
: "${TISSUE:?Set TISSUE='PBMC' or another tissue name}"

TAG="${TAG:-matrix}"
GROUPBY="${GROUPBY:-leiden}"
LABEL_KEY="${LABEL_KEY:-}"
ONTOLOGY_KEY="${ONTOLOGY_KEY:-}"
N_TOP="${N_TOP:-25}"
METHOD="${METHOD:-wilcoxon}"
RUN_CLUSTERING="${RUN_CLUSTERING:-0}"
NO_NORMALIZE="${NO_NORMALIZE:-0}"

marker_db="data/raw/${TAG}.matrix_markers.csv"
instructions="data/processed/${TAG}.matrix.instructions.jsonl"
predictions="outputs/${TAG}.matrix_marker_overlap.jsonl"

prepare_args=(
  prepare-matrix-benchmark
  --adata "$ADATA"
  --output-marker-db "$marker_db"
  --tissue "$TISSUE"
  --groupby "$GROUPBY"
  --n-top "$N_TOP"
  --method "$METHOD"
)
if [[ -n "$LABEL_KEY" ]]; then
  prepare_args+=(--label-key "$LABEL_KEY")
fi
if [[ -n "$ONTOLOGY_KEY" ]]; then
  prepare_args+=(--ontology-key "$ONTOLOGY_KEY")
fi
if [[ "$RUN_CLUSTERING" == "1" ]]; then
  prepare_args+=(--run-clustering)
fi
if [[ "$NO_NORMALIZE" == "1" ]]; then
  prepare_args+=(--no-normalize)
fi

python -m deepseekcell_ft.cli "${prepare_args[@]}"
python -m deepseekcell_ft.cli validate-marker-db --input "$marker_db"
python -m deepseekcell_ft.cli build-dataset \
  --input "$marker_db" \
  --output "$instructions" \
  --examples-per-record 1 \
  --min-markers "$N_TOP" \
  --max-markers "$N_TOP" \
  --noise-rate 0
python -m deepseekcell_ft.cli benchmark-marker-overlap \
  --marker-db "$marker_db" \
  --input "$instructions" \
  --output "$predictions"

printf 'marker_db: %s\ninstructions: %s\npredictions: %s\n' \
  "$marker_db" "$instructions" "$predictions"
