#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEARCH_ROOT="${SEARCH_ROOT:-/root/autodl-tmp}"
OUTPUT_ARCHIVE="${OUTPUT_ARCHIVE:-$PROJECT_ROOT/deepseekcell-ft-results-label-overlap.tar.gz}"

find_latest_path() {
  local relative_path="$1"
  find "$SEARCH_ROOT" -path "*/$relative_path" -printf "%T@ %p\n" 2>/dev/null \
    | sort -nr \
    | head -n 1 \
    | cut -d " " -f 2-
}

find_cuda_preflight() {
  local relative_path="$1"
  while IFS= read -r candidate; do
    if grep -q '"cuda_available": true' "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(
    find "$SEARCH_ROOT" -path "*/$relative_path" -printf "%T@ %p\n" 2>/dev/null \
      | sort -nr \
      | cut -d " " -f 2-
  )
  find_latest_path "$relative_path"
}

copy_into_stage() {
  local relative_path="$1"
  local source_path="$2"
  local stage="$3"

  mkdir -p "$stage/$(dirname "$relative_path")"
  cp -a "$source_path" "$stage/$relative_path"
  echo "included: $relative_path <- $source_path"
}

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

required_files=(
  "outputs/deepseek_lora_label_overlap_predictions.jsonl"
  "outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl"
  "outputs/deepseek_lora_label_overlap_errors.csv"
  "outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl"
  "outputs/deepseek_lora_rerank_harm_examples.csv"
  "outputs/panglaodb_cl_curated_marker_overlap_label_overlap.jsonl"
)

optional_files=(
  "outputs/deepseek_prompt_label_overlap_predictions.jsonl"
  "outputs/deepseek_prompt_label_overlap_predictions.mapped.jsonl"
  "outputs/deepseek_prompt_label_overlap_errors.csv"
  "outputs/qwen25_7b_prompt_label_overlap_predictions.jsonl"
  "outputs/qwen25_7b_prompt_label_overlap_predictions.mapped.jsonl"
  "outputs/qwen25_7b_prompt_label_overlap_errors.csv"
  "outputs/llama3_8b_prompt_label_overlap_predictions.jsonl"
  "outputs/llama3_8b_prompt_label_overlap_predictions.mapped.jsonl"
  "outputs/llama3_8b_prompt_label_overlap_errors.csv"
)

missing=()
for relative_path in "${required_files[@]}"; do
  source_path="$(find_latest_path "$relative_path")"
  if [[ -z "$source_path" || ! -e "$source_path" ]]; then
    missing+=("$relative_path")
    continue
  fi
  copy_into_stage "$relative_path" "$source_path" "$stage"
done

for relative_path in "${optional_files[@]}"; do
  source_path="$(find_latest_path "$relative_path")"
  if [[ -n "$source_path" && -e "$source_path" ]]; then
    copy_into_stage "$relative_path" "$source_path" "$stage"
  fi
done

preflight_relative="outputs/finetune_preflight_label_overlap.gpu.json"
preflight_source="$(find_cuda_preflight "$preflight_relative")"
if [[ -n "$preflight_source" && -e "$preflight_source" ]]; then
  copy_into_stage "$preflight_relative" "$preflight_source" "$stage"
else
  missing+=("$preflight_relative")
fi

adapter_relative="models/deepseekcell-ft-lora-label-overlap"
adapter_source="$(find_latest_path "$adapter_relative")"
if [[ -n "$adapter_source" && -d "$adapter_source" ]]; then
  copy_into_stage "$adapter_relative" "$adapter_source" "$stage"
else
  echo "warning: adapter directory not found: $adapter_relative" >&2
fi

if (( ${#missing[@]} )); then
  printf 'error: missing required label-overlap result files:\n' >&2
  printf '  %s\n' "${missing[@]}" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_ARCHIVE")"
tar -C "$stage" -czf "$OUTPUT_ARCHIVE" .
echo "wrote: $OUTPUT_ARCHIVE"
