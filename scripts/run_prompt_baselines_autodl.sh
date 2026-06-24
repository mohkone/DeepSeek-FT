#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

MARKER_DB="${MARKER_DB:-data/raw/panglaodb.normalized.cl.curated.csv}"
SPLIT_DIR="${SPLIT_DIR:-data/processed/panglaodb_cl_curated_label_overlap_splits}"
INPUT_JSONL="${INPUT_JSONL:-$SPLIT_DIR/test.jsonl}"
DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-/root/autodl-tmp/models/deepseek-llm-7b-chat}"
SECOND_MODEL="${SECOND_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
SECOND_MODEL_NAME="${SECOND_MODEL_NAME:-qwen25_7b}"
RUN_SECOND_MODEL="${RUN_SECOND_MODEL:-1}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-128}"
TEMPERATURE="${TEMPERATURE:-0.0}"

run_prompt_baseline() {
  local name="$1"
  local model="$2"
  local raw_predictions="outputs/${name}_prompt_label_overlap_predictions.jsonl"
  local mapped_predictions="outputs/${name}_prompt_label_overlap_predictions.mapped.jsonl"
  local error_examples="outputs/${name}_prompt_label_overlap_errors.csv"

  echo "=== Prompt-only baseline: ${name} (${model}) ==="
  python -m deepseekcell_ft.cli benchmark-prompt \
    --base-model "$model" \
    --input "$INPUT_JSONL" \
    --output "$raw_predictions" \
    --max-new-tokens "$MAX_NEW_TOKENS" \
    --temperature "$TEMPERATURE"

  python -m deepseekcell_ft.cli map-prediction-ontology \
    --predictions "$raw_predictions" \
    --marker-db "$MARKER_DB" \
    --output "$mapped_predictions"

  python -m deepseekcell_ft.cli evaluate \
    --predictions "$mapped_predictions"

  python -m deepseekcell_ft.cli analyze-predictions \
    --predictions "$mapped_predictions" \
    --examples-output "$error_examples" \
    --max-examples 50
}

run_prompt_baseline "deepseek" "$DEEPSEEK_MODEL"

if [[ "$RUN_SECOND_MODEL" == "1" ]]; then
  run_prompt_baseline "$SECOND_MODEL_NAME" "$SECOND_MODEL"
else
  echo "Skipping second prompt-only model because RUN_SECOND_MODEL=$RUN_SECOND_MODEL"
fi

echo "Prompt baseline outputs are in outputs/*prompt_label_overlap_*"
