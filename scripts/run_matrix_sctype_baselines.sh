#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

ensure_pbmc3k() {
  if [[ ! -f data/raw/pbmc3k.matrix_markers.csv || ! -f data/processed/pbmc3k.matrix.instructions.jsonl ]]; then
    bash scripts/run_pbmc3k_matrix_benchmark.sh
  fi
  require_matrix_inputs pbmc3k data/matrix/pbmc3k_tutorial_labeled.h5ad
}

ensure_baron() {
  if [[ ! -f data/raw/baron_pancreas.matrix_markers.csv || ! -f data/processed/baron_pancreas.matrix.instructions.jsonl ]]; then
    bash scripts/run_baron_pancreas_matrix_benchmark.sh
  fi
  require_matrix_inputs baron_pancreas data/matrix/baron_pancreas_labeled.h5ad
}

ensure_zeisel() {
  if [[ ! -f data/raw/zeisel_brain.matrix_markers.csv || ! -f data/processed/zeisel_brain.matrix.instructions.jsonl ]]; then
    bash scripts/run_zeisel_brain_matrix_benchmark.sh
  fi
  require_matrix_inputs zeisel_brain data/matrix/zeisel_brain_labeled.h5ad
}

require_matrix_inputs() {
  local tag="$1"
  local adata="$2"
  local missing=()
  [[ -s "$adata" ]] || missing+=("$adata")
  [[ -s "data/raw/${tag}.matrix_markers.csv" ]] || missing+=("data/raw/${tag}.matrix_markers.csv")
  [[ -s "data/processed/${tag}.matrix.instructions.jsonl" ]] || missing+=("data/processed/${tag}.matrix.instructions.jsonl")
  if (( ${#missing[@]} )); then
    printf 'Missing required %s inputs. Restore a complete result tarball or regenerate the matrix benchmark:\n' "$tag" >&2
    printf '  %s\n' "${missing[@]}" >&2
    exit 1
  fi
}

run_sctype() {
  local tag="$1"
  local adata="$2"
  local cluster_key="$3"
  local label_key="$4"
  local tissue="$5"
  local sctype_tissue="$6"
  local marker_db="data/raw/${tag}.matrix_markers.csv"
  local raw_output="outputs/${tag}.sctype.raw.jsonl"
  local output="outputs/${tag}.sctype.jsonl"
  local harmonized_output="outputs/${tag}.sctype.harmonized.jsonl"
  local harmonization="data/curation/${tag}_sctype_label_harmonization.csv"

  if ! command -v Rscript >/dev/null 2>&1; then
    echo "Rscript not found. Run scripts/setup_sctype_conda_autodl.sh first." >&2
    exit 1
  fi

  Rscript scripts/official_sctype_cluster_baseline.R \
    --adata "$adata" \
    --cluster-key "$cluster_key" \
    --label-key "$label_key" \
    --ontology-key cell_ontology_id \
    --tissue "$tissue" \
    --sctype-tissue "$sctype_tissue" \
    --output "$raw_output"

  python -m deepseekcell_ft.cli map-prediction-ontology \
    --predictions "$raw_output" \
    --marker-db "$marker_db" \
    --output "$output"

  if [[ -f "$harmonization" ]]; then
    python -m deepseekcell_ft.cli harmonize-prediction-labels \
      --predictions "$output" \
      --mapping "$harmonization" \
      --marker-db "$marker_db" \
      --output "$harmonized_output"
  fi
}

write_comparison_table() {
  local tag="$1"
  local marker_output="outputs/${tag}.matrix_marker_overlap.jsonl"
  local rerank_output="outputs/${tag}.deepseek_lora_rerank.jsonl"
  local sctype_output="outputs/${tag}.sctype.jsonl"
  local sctype_harmonized_output="outputs/${tag}.sctype.harmonized.jsonl"
  local singler_output="outputs/${tag}.singler.jsonl"

  local table_args=(
    --output-markdown "outputs/${tag}.comparison.md"
    --output-csv "outputs/${tag}.comparison.csv"
    --output-json "outputs/${tag}.comparison.json"
  )
  if [[ -f "$marker_output" ]]; then
    table_args+=(--prediction "Marker overlap=${marker_output}")
  fi
  if [[ -f "$rerank_output" ]]; then
    table_args+=(--prediction "DeepSeek LoRA rerank=${rerank_output}")
  fi
  table_args+=(--prediction "scType=${sctype_output}")
  if [[ -f "$sctype_harmonized_output" ]]; then
    table_args+=(--prediction "scType harmonized=${sctype_harmonized_output}")
  fi
  if [[ -f "$singler_output" ]]; then
    table_args+=(--prediction "SingleR=${singler_output}")
  fi

  python scripts/write_prediction_metrics_table.py "${table_args[@]}"
}

mkdir -p outputs
DATASETS="${DATASETS:-pbmc3k baron_pancreas zeisel_brain}"

if [[ " $DATASETS " == *" pbmc3k "* ]]; then
  ensure_pbmc3k
  run_sctype pbmc3k data/matrix/pbmc3k_tutorial_labeled.h5ad cell_type cell_type PBMC "Immune system"
  write_comparison_table pbmc3k
fi

if [[ " $DATASETS " == *" baron_pancreas "* ]]; then
  ensure_baron
  run_sctype baron_pancreas data/matrix/baron_pancreas_labeled.h5ad cell_type cell_type Pancreas Pancreas
  write_comparison_table baron_pancreas
fi

if [[ " $DATASETS " == *" zeisel_brain "* ]]; then
  ensure_zeisel
  run_sctype zeisel_brain data/matrix/zeisel_brain_labeled.h5ad cell_type cell_type Brain Brain
  write_comparison_table zeisel_brain
fi

tar_paths=()
for tag in pbmc3k baron_pancreas zeisel_brain; do
  for path in \
    "outputs/${tag}.sctype.raw.jsonl" \
    "outputs/${tag}.sctype.jsonl" \
    "outputs/${tag}.sctype.harmonized.jsonl" \
    "outputs/${tag}.comparison.md" \
    "outputs/${tag}.comparison.csv" \
    "outputs/${tag}.comparison.json"; do
    [[ -f "$path" ]] && tar_paths+=("$path")
  done
done

if (( ${#tar_paths[@]} )); then
  tar -czf sctype-matrix-baselines-results.tar.gz "${tar_paths[@]}"
  echo "Wrote sctype-matrix-baselines-results.tar.gz"
else
  echo "No scType output files were produced; skipping result archive." >&2
fi
