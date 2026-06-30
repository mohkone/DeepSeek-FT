#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

ensure_pbmc3k() {
  if [[ ! -f data/raw/pbmc3k.matrix_markers.csv || ! -f data/processed/pbmc3k.matrix.instructions.jsonl ]]; then
    bash scripts/run_pbmc3k_matrix_benchmark.sh
  fi
}

ensure_baron() {
  if [[ ! -f data/raw/baron_pancreas.matrix_markers.csv || ! -f data/processed/baron_pancreas.matrix.instructions.jsonl ]]; then
    bash scripts/run_baron_pancreas_matrix_benchmark.sh
  fi
}

ensure_zeisel() {
  if [[ ! -f data/raw/zeisel_brain.matrix_markers.csv || ! -f data/processed/zeisel_brain.matrix.instructions.jsonl ]]; then
    bash scripts/run_zeisel_brain_matrix_benchmark.sh
  fi
}

run_sctype() {
  local tag="$1"
  local marker_db="data/raw/${tag}.matrix_markers.csv"
  local instructions="data/processed/${tag}.matrix.instructions.jsonl"
  local output="outputs/${tag}.sctype.jsonl"

  python -m deepseekcell_ft.cli benchmark-sctype \
    --marker-db "$marker_db" \
    --input "$instructions" \
    --output "$output"
}

write_comparison_table() {
  local tag="$1"
  local marker_output="outputs/${tag}.matrix_marker_overlap.jsonl"
  local rerank_output="outputs/${tag}.deepseek_lora_rerank.jsonl"
  local sctype_output="outputs/${tag}.sctype.jsonl"
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
  if [[ -f "$singler_output" ]]; then
    table_args+=(--prediction "SingleR=${singler_output}")
  fi

  python scripts/write_prediction_metrics_table.py "${table_args[@]}"
}

mkdir -p outputs

ensure_pbmc3k
run_sctype pbmc3k
write_comparison_table pbmc3k

ensure_baron
run_sctype baron_pancreas
write_comparison_table baron_pancreas

ensure_zeisel
run_sctype zeisel_brain
write_comparison_table zeisel_brain

tar -czf sctype-matrix-baselines-results.tar.gz \
  outputs/pbmc3k.sctype.jsonl \
  outputs/pbmc3k.comparison.md \
  outputs/pbmc3k.comparison.csv \
  outputs/pbmc3k.comparison.json \
  outputs/baron_pancreas.sctype.jsonl \
  outputs/baron_pancreas.comparison.md \
  outputs/baron_pancreas.comparison.csv \
  outputs/baron_pancreas.comparison.json \
  outputs/zeisel_brain.sctype.jsonl \
  outputs/zeisel_brain.comparison.md \
  outputs/zeisel_brain.comparison.csv \
  outputs/zeisel_brain.comparison.json

echo "Wrote sctype-matrix-baselines-results.tar.gz"
