#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

ADATA="${ADATA:-data/matrix/zeisel_brain_labeled.h5ad}"
TAG="${TAG:-zeisel_brain}"
BASE_MODEL="${BASE_MODEL:-/root/autodl-tmp/models/deepseek-llm-7b-chat}"
ADAPTER="${ADAPTER:-models/deepseekcell-ft-lora-label-overlap}"
TOP_K="${TOP_K:-5}"
N_TOP="${N_TOP:-25}"
SINGLER_REFERENCE="${SINGLER_REFERENCE:-mouse_rna_seq}"
SCTYPE_TISSUE="${SCTYPE_TISSUE:-Brain}"
SKIP_PREPARE="${SKIP_PREPARE:-0}"
SKIP_RERANK="${SKIP_RERANK:-0}"
SKIP_SINGLER="${SKIP_SINGLER:-0}"
SKIP_SCTYPE="${SKIP_SCTYPE:-0}"
RUN_PROMPT="${RUN_PROMPT:-0}"
PROMPT_MODEL="${PROMPT_MODEL:-$BASE_MODEL}"

is_enabled() {
  case "${1,,}" in
    1|true|yes|y) return 0 ;;
    *) return 1 ;;
  esac
}

echo "Zeisel brain full comparison: SKIP_RERANK=${SKIP_RERANK} SKIP_SCTYPE=${SKIP_SCTYPE} SKIP_SINGLER=${SKIP_SINGLER} RUN_PROMPT=${RUN_PROMPT}" >&2

SKIP_PREPARE="$SKIP_PREPARE" ADATA="$ADATA" TAG="$TAG" N_TOP="$N_TOP" \
  bash scripts/run_zeisel_brain_matrix_benchmark.sh

marker_db="data/raw/${TAG}.matrix_markers.csv"
instructions="data/processed/${TAG}.matrix.instructions.jsonl"
marker_output="outputs/${TAG}.matrix_marker_overlap.jsonl"
rerank_output="outputs/${TAG}.deepseek_lora_rerank.jsonl"
singler_output="outputs/${TAG}.singler.jsonl"
sctype_raw_output="outputs/${TAG}.sctype.raw.jsonl"
sctype_output="outputs/${TAG}.sctype.jsonl"
prompt_output="outputs/${TAG}.prompt.jsonl"
prompt_mapped_output="outputs/${TAG}.prompt.mapped.jsonl"

prediction_specs=(
  "Marker overlap=$marker_output"
)

if ! is_enabled "$SKIP_RERANK"; then
  python -m deepseekcell_ft.cli benchmark-lora-rerank \
    --marker-db "$marker_db" \
    --base-model "$BASE_MODEL" \
    --adapter "$ADAPTER" \
    --input "$instructions" \
    --output "$rerank_output" \
    --top-k "$TOP_K"
  prediction_specs+=("DeepSeek LoRA rerank=$rerank_output")
fi

if ! is_enabled "$SKIP_SCTYPE"; then
  Rscript scripts/official_sctype_cluster_baseline.R \
    --adata "$ADATA" \
    --cluster-key cell_type \
    --label-key cell_type \
    --ontology-key cell_ontology_id \
    --tissue Brain \
    --sctype-tissue "$SCTYPE_TISSUE" \
    --output "$sctype_raw_output"
  python -m deepseekcell_ft.cli map-prediction-ontology \
    --predictions "$sctype_raw_output" \
    --marker-db "$marker_db" \
    --output "$sctype_output"
  prediction_specs+=("scType=$sctype_output")
fi

if ! is_enabled "$SKIP_SINGLER"; then
  Rscript scripts/singler_cluster_baseline.R \
    --adata "$ADATA" \
    --cluster-key cell_type \
    --label-key cell_type \
    --ontology-key cell_ontology_id \
    --tissue Brain \
    --reference "$SINGLER_REFERENCE" \
    --output "$singler_output"
  prediction_specs+=("SingleR=$singler_output")
fi

if [[ "$RUN_PROMPT" == "1" ]]; then
  python -m deepseekcell_ft.cli benchmark-prompt \
    --base-model "$PROMPT_MODEL" \
    --input "$instructions" \
    --output "$prompt_output"
  python -m deepseekcell_ft.cli map-prediction-ontology \
    --predictions "$prompt_output" \
    --marker-db "$marker_db" \
    --output "$prompt_mapped_output"
  prediction_specs+=("Prompt-only=$prompt_mapped_output")
fi

table_args=(
  --output-markdown "outputs/${TAG}.comparison.md"
  --output-csv "outputs/${TAG}.comparison.csv"
  --output-json "outputs/${TAG}.comparison.json"
)
for spec in "${prediction_specs[@]}"; do
  table_args+=(--prediction "$spec")
done

python scripts/write_prediction_metrics_table.py "${table_args[@]}"
