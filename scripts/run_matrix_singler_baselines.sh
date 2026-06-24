#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if ! command -v Rscript >/dev/null 2>&1; then
  echo "Rscript not found. Run scripts/setup_singler_conda_autodl.sh first." >&2
  exit 1
fi

ensure_pbmc3k() {
  if [[ ! -f data/matrix/pbmc3k_tutorial_labeled.h5ad ]]; then
    bash scripts/run_pbmc3k_matrix_benchmark.sh
  fi
}

ensure_baron() {
  if [[ ! -f data/matrix/baron_pancreas_labeled.h5ad ]]; then
    bash scripts/run_baron_pancreas_matrix_benchmark.sh
  fi
}

ensure_zeisel() {
  if [[ ! -f data/matrix/zeisel_brain_labeled.h5ad ]]; then
    bash scripts/run_zeisel_brain_matrix_benchmark.sh
  fi
}

write_comparison_table() {
  local tag="$1"
  local marker_output="outputs/${tag}.matrix_marker_overlap.jsonl"
  local rerank_output="outputs/${tag}.deepseek_lora_rerank.jsonl"
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
  table_args+=(--prediction "SingleR=${singler_output}")

  python scripts/write_prediction_metrics_table.py "${table_args[@]}"
}

mkdir -p outputs

ensure_pbmc3k
Rscript scripts/singler_cluster_baseline.R \
  --adata data/matrix/pbmc3k_tutorial_labeled.h5ad \
  --cluster-key cell_type \
  --label-key cell_type \
  --ontology-key cell_ontology_id \
  --tissue PBMC \
  --reference hpca \
  --output outputs/pbmc3k.singler.jsonl
python -m deepseekcell_ft.cli evaluate --predictions outputs/pbmc3k.singler.jsonl
write_comparison_table pbmc3k

ensure_baron
Rscript scripts/singler_cluster_baseline.R \
  --adata data/matrix/baron_pancreas_labeled.h5ad \
  --cluster-key cell_type \
  --label-key cell_type \
  --ontology-key cell_ontology_id \
  --tissue Pancreas \
  --reference hpca \
  --output outputs/baron_pancreas.singler.jsonl
python -m deepseekcell_ft.cli evaluate --predictions outputs/baron_pancreas.singler.jsonl
write_comparison_table baron_pancreas

ensure_zeisel
Rscript scripts/singler_cluster_baseline.R \
  --adata data/matrix/zeisel_brain_labeled.h5ad \
  --cluster-key cell_type \
  --label-key cell_type \
  --ontology-key cell_ontology_id \
  --tissue Brain \
  --reference mouse_rna_seq \
  --output outputs/zeisel_brain.singler.jsonl
python -m deepseekcell_ft.cli evaluate --predictions outputs/zeisel_brain.singler.jsonl
write_comparison_table zeisel_brain

tar -czf singler-matrix-baselines-results.tar.gz \
  outputs/pbmc3k.singler.jsonl \
  outputs/pbmc3k.comparison.md \
  outputs/pbmc3k.comparison.csv \
  outputs/pbmc3k.comparison.json \
  outputs/baron_pancreas.singler.jsonl \
  outputs/baron_pancreas.comparison.md \
  outputs/baron_pancreas.comparison.csv \
  outputs/baron_pancreas.comparison.json \
  outputs/zeisel_brain.singler.jsonl \
  outputs/zeisel_brain.comparison.md \
  outputs/zeisel_brain.comparison.csv \
  outputs/zeisel_brain.comparison.json

echo "Wrote singler-matrix-baselines-results.tar.gz"
