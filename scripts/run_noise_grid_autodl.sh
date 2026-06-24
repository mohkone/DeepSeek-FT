#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

MARKER_DB="${MARKER_DB:-data/raw/panglaodb.normalized.cl.curated.csv}"
SPLIT_DIR="${SPLIT_DIR:-data/processed/panglaodb_cl_curated_label_overlap_splits}"
INPUT_JSONL="${INPUT_JSONL:-$SPLIT_DIR/test.jsonl}"
BASE_MODEL="${BASE_MODEL:-/root/autodl-tmp/models/deepseek-llm-7b-chat}"
ADAPTER="${ADAPTER:-models/deepseekcell-ft-lora-label-overlap}"
TOP_K="${TOP_K:-5}"
SEED="${SEED:-23}"
GRID="${GRID:-0.50:3:drop50_noise3 0.75:5:drop75_noise5 0.90:8:drop90_noise8}"

mkdir -p outputs "$SPLIT_DIR"

if [[ ! -d "$ADAPTER" ]]; then
  backup_adapter="$(
    find /root/autodl-tmp -maxdepth 3 -type d \
      -path "/root/autodl-tmp/DeepSeek-FT.backup.*/$ADAPTER" \
      -printf "%T@ %p\n" 2>/dev/null \
      | sort -nr \
      | head -n 1 \
      | cut -d " " -f 2-
  )"
  if [[ -n "$backup_adapter" && -d "$backup_adapter" ]]; then
    echo "Adapter not found at '$ADAPTER'; using latest backup adapter '$backup_adapter'."
    ADAPTER="$backup_adapter"
  else
    echo "error: LoRA adapter not found at '$ADAPTER'." >&2
    echo "Set ADAPTER=/path/to/deepseekcell-ft-lora-label-overlap or copy the adapter into models/." >&2
    exit 1
  fi
fi

for item in $GRID; do
  IFS=":" read -r drop_rate noise_markers tag <<< "$item"

  perturbed_jsonl="$SPLIT_DIR/test.perturbed.${tag}.jsonl"
  marker_output="outputs/marker_overlap_label_overlap_perturbed_${tag}.jsonl"
  rerank_output="outputs/deepseek_lora_rerank_label_overlap_perturbed_${tag}.jsonl"
  harm_output="outputs/deepseek_lora_rerank_perturbed_${tag}_harm_examples.csv"

  echo "=== Noise grid: ${tag} (drop_rate=${drop_rate}, add_noise_markers=${noise_markers}) ==="

  python -m deepseekcell_ft.cli perturb-markers \
    --input "$INPUT_JSONL" \
    --output "$perturbed_jsonl" \
    --marker-db "$MARKER_DB" \
    --drop-rate "$drop_rate" \
    --add-noise-markers "$noise_markers" \
    --seed "$SEED"

  python -m deepseekcell_ft.cli benchmark-marker-overlap \
    --marker-db "$MARKER_DB" \
    --input "$perturbed_jsonl" \
    --output "$marker_output"

  python -m deepseekcell_ft.cli benchmark-lora-rerank \
    --marker-db "$MARKER_DB" \
    --base-model "$BASE_MODEL" \
    --adapter "$ADAPTER" \
    --input "$perturbed_jsonl" \
    --output "$rerank_output" \
    --top-k "$TOP_K"

  python -m deepseekcell_ft.cli analyze-rerank-predictions \
    --predictions "$rerank_output" \
    --examples-output "$harm_output" \
    --max-examples 50
done
