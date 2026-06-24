#!/usr/bin/env bash
set -euo pipefail

SPLIT_DIR="${SPLIT_DIR:-data/processed/panglaodb_cl_curated_label_overlap_splits}"
PREFLIGHT_OUTPUT="${PREFLIGHT_OUTPUT:-outputs/finetune_preflight_label_overlap.gpu.json}"
BASE_MODEL="${BASE_MODEL:-deepseek-ai/deepseek-llm-7b-chat}"
MODEL_OUTPUT_DIR="${MODEL_OUTPUT_DIR:-models/deepseekcell-ft-lora-label-overlap}"
MAX_SEQ_LENGTH="${MAX_SEQ_LENGTH:-2048}"
PER_DEVICE_TRAIN_BATCH_SIZE="${PER_DEVICE_TRAIN_BATCH_SIZE:-1}"
GRADIENT_ACCUMULATION_STEPS="${GRADIENT_ACCUMULATION_STEPS:-8}"
LEARNING_RATE="${LEARNING_RATE:-2e-4}"
NUM_TRAIN_EPOCHS="${NUM_TRAIN_EPOCHS:-3.0}"
LORA_R="${LORA_R:-16}"
LORA_ALPHA="${LORA_ALPHA:-32}"
LORA_DROPOUT="${LORA_DROPOUT:-0.05}"
GROUP_BY="${GROUP_BY:-}"
ALLOW_CPU="${ALLOW_CPU:-0}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

preflight_args=(
  preflight-finetune
  --split-dir "$SPLIT_DIR"
  --output "$PREFLIGHT_OUTPUT"
  --base-model "$BASE_MODEL"
  --model-output-dir "$MODEL_OUTPUT_DIR"
  --max-seq-length "$MAX_SEQ_LENGTH"
)

if [[ -z "${GROUP_BY// }" ]]; then
  preflight_args+=(--disable-group-check)
else
  preflight_args+=(--group-by "$GROUP_BY")
fi

python -m deepseekcell_ft.cli "${preflight_args[@]}"

python - "$PREFLIGHT_OUTPUT" "$ALLOW_CPU" <<'PY'
import json
import sys

report_path = sys.argv[1]
allow_cpu = sys.argv[2].lower() in {"1", "true", "yes", "y"}

with open(report_path, encoding="utf-8") as handle:
    report = json.load(handle)

hardware = report.get("hardware", {})
has_accelerator = bool(hardware.get("cuda_available") or hardware.get("mps_available"))

if not has_accelerator and not allow_cpu:
    warnings = "; ".join(report.get("warnings", []))
    raise SystemExit(
        "No GPU accelerator detected. Refusing to launch LoRA training. "
        "Set ALLOW_CPU=1 only for tiny smoke tests. "
        f"Preflight warnings: {warnings}"
    )
PY

python -m deepseekcell_ft.cli train-lora \
  --base-model "$BASE_MODEL" \
  --train-jsonl "$SPLIT_DIR/train.jsonl" \
  --validation-jsonl "$SPLIT_DIR/validation.jsonl" \
  --output-dir "$MODEL_OUTPUT_DIR" \
  --max-seq-length "$MAX_SEQ_LENGTH" \
  --per-device-train-batch-size "$PER_DEVICE_TRAIN_BATCH_SIZE" \
  --gradient-accumulation-steps "$GRADIENT_ACCUMULATION_STEPS" \
  --learning-rate "$LEARNING_RATE" \
  --num-train-epochs "$NUM_TRAIN_EPOCHS" \
  --lora-r "$LORA_R" \
  --lora-alpha "$LORA_ALPHA" \
  --lora-dropout "$LORA_DROPOUT"
