# AutoDL GPU Runbook

This project can use an AutoDL GPU instance for the real LoRA fine-tuning run.
Use the local Windows machine for data preparation, unit tests, and baseline
checks, then move the repository to AutoDL for GPU training.

AutoDL references:

- AutoDL GPU cloud: https://www.autodl.com/
- GPU troubleshooting and `nvidia-smi` checks: https://www.autodl.com/docs/qa3/
- GPU utilization checks: https://www.autodl.com/docs/perf/

## Recommended Instance

For the first DeepSeek-7B LoRA run, choose a CUDA PyTorch image on one of these
GPUs:

- A100 40 GB or A100 80 GB: safest first choice.
- L40S 48 GB or A800/H800/H100-class GPUs: also suitable.
- RTX 4090 24 GB: possible only after memory tuning, smaller batch settings, or
  adding QLoRA/4-bit loading support.

Avoid 16 GB GPUs for the current 7B LoRA path. The repository currently trains
standard LoRA adapters and does not yet load the base model in 4-bit.

## Upload Or Clone

The `/root/autodl-tmp/...` path exists only inside the AutoDL Linux instance.
If PowerShell shows a path such as `C:\root\autodl-tmp`, you are still running
commands on the local Windows machine.

On the AutoDL terminal:

```bash
cd /root/autodl-tmp
git clone <YOUR_REPOSITORY_URL> DeepSeek-FT
cd DeepSeek-FT
```

If the project is not in Git, upload the folder to `/root/autodl-tmp/DeepSeek-FT`
with the AutoDL file manager, `scp`, or `rsync`.

From local Windows, you can create an uploadable zip first:

```powershell
.\scripts\package_for_autodl.ps1
```

Upload `dist/deepseek-ft-autodl.zip` to AutoDL, then run this in the AutoDL
Linux terminal:

```bash
cd /root/autodl-tmp
python -m zipfile -e deepseek-ft-autodl.zip DeepSeek-FT
cd DeepSeek-FT
```

## Environment Check

AutoDL recommends checking GPU visibility with `nvidia-smi`. Then verify PyTorch
can see CUDA:

```bash
nvidia-smi

python - <<'PY'
import torch

print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("cuda devices:", torch.cuda.device_count())
if torch.cuda.is_available():
    print("device 0:", torch.cuda.get_device_name(0))
PY
```

If `nvidia-smi` works but `torch.cuda.is_available()` is false, rebuild the
Python environment from a CUDA-enabled PyTorch image or CUDA PyTorch wheel.

## Install

```bash
python -m pip install -U pip
python -m pip install -e ".[train]"
```

Optional but useful before paying for a long run:

```bash
python -m unittest discover -s tests
python -m compileall -q src tests
```

## Run Prompt-Only Baselines

Prompt-only DeepSeek is the key comparison for showing whether LoRA changed
behavior. A second prompt-only model, such as Qwen2.5-7B-Instruct, strengthens
the manuscript by showing whether the result is DeepSeek-specific.

```bash
cd /root/autodl-tmp/DeepSeek-FT
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=/root/autodl-tmp/huggingface

DEEPSEEK_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
SECOND_MODEL=Qwen/Qwen2.5-7B-Instruct \
SECOND_MODEL_NAME=qwen25_7b \
bash scripts/run_prompt_baselines_autodl.sh
```

If you want to run only DeepSeek first:

```bash
DEEPSEEK_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
RUN_SECOND_MODEL=0 \
bash scripts/run_prompt_baselines_autodl.sh
```

For Llama-3-8B, replace `SECOND_MODEL` and `SECOND_MODEL_NAME`. Meta Llama
models usually require accepting the license and authenticating with a
Hugging Face token.

The script writes raw predictions, Cell-Ontology-mapped predictions, and error
examples:

- `outputs/deepseek_prompt_label_overlap_predictions.jsonl`
- `outputs/deepseek_prompt_label_overlap_predictions.mapped.jsonl`
- `outputs/deepseek_prompt_label_overlap_errors.csv`
- `outputs/qwen25_7b_prompt_label_overlap_predictions.jsonl`
- `outputs/qwen25_7b_prompt_label_overlap_predictions.mapped.jsonl`
- `outputs/qwen25_7b_prompt_label_overlap_errors.csv`

## Train The Label-Overlap Model

This is the standard first fine-tuning comparison because validation and test
labels are represented in training.

```bash
chmod +x scripts/run_lora_training.sh
bash scripts/run_lora_training.sh
```

The launcher reruns preflight, writes
`outputs/finetune_preflight_label_overlap.gpu.json`, refuses CPU-only training,
and then starts `train-lora`.

If training fails while requesting files from `https://huggingface.co`, the GPU
and project setup are already working; only the base-model download failed. Try
downloading the model through a reachable Hugging Face endpoint first, then
point `BASE_MODEL` at the local directory:

```bash
cd /root/autodl-tmp/DeepSeek-FT
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=/root/autodl-tmp/huggingface
mkdir -p /root/autodl-tmp/models

python - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="deepseek-ai/deepseek-llm-7b-chat",
    local_dir="/root/autodl-tmp/models/deepseek-llm-7b-chat",
)
PY

BASE_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
bash scripts/run_lora_training.sh
```

To tune memory use on a smaller GPU:

```bash
PER_DEVICE_TRAIN_BATCH_SIZE=1 \
GRADIENT_ACCUMULATION_STEPS=16 \
MAX_SEQ_LENGTH=1024 \
bash scripts/run_lora_training.sh
```

## Train The Label-Held-Out Model

This grouped split is a harder generalization experiment. It is useful for the
paper, but train the label-overlap split first.

```bash
SPLIT_DIR=data/processed/panglaodb_cl_curated_grouped_splits \
PREFLIGHT_OUTPUT=outputs/finetune_preflight_grouped.gpu.json \
MODEL_OUTPUT_DIR=models/deepseekcell-ft-lora-grouped \
GROUP_BY=tissue,cell_type,source \
bash scripts/run_lora_training.sh
```

## Benchmark The Trained Adapter

After `Saved LoRA model to models/deepseekcell-ft-lora-label-overlap`, run:

```bash
python -m deepseekcell_ft.cli benchmark-lora \
  --base-model /root/autodl-tmp/models/deepseek-llm-7b-chat \
  --adapter models/deepseekcell-ft-lora-label-overlap \
  --input data/processed/panglaodb_cl_curated_label_overlap_splits/test.jsonl \
  --output outputs/deepseek_lora_label_overlap_predictions.jsonl
```

This writes evaluator-compatible predictions and prints accuracy, macro F1,
Cell Ontology accuracy, calibration error, and runtime.

Inspect the first mismatches and output-format failures:

```bash
python -m deepseekcell_ft.cli analyze-predictions \
  --predictions outputs/deepseek_lora_label_overlap_predictions.jsonl \
  --examples-output outputs/deepseek_lora_label_overlap_errors.csv \
  --max-examples 50
```

Map predicted labels back to curated Cell Ontology IDs before reporting
ontology accuracy. This preserves `original_pred_cl_id` for auditing and writes
a corrected `pred_cl_id` when the predicted label has one unambiguous curated
CL ID:

```bash
python -m deepseekcell_ft.cli map-prediction-ontology \
  --predictions outputs/deepseek_lora_label_overlap_predictions.jsonl \
  --marker-db data/raw/panglaodb.normalized.cl.curated.csv \
  --output outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl

python -m deepseekcell_ft.cli evaluate \
  --predictions outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl
```

For the grouped label-held-out adapter, change the adapter, input, and output
paths to the grouped equivalents.

## Benchmark Candidate Reranking

The next constrained experiment uses marker-overlap to propose the top
candidate labels and CL IDs, then asks the LoRA adapter to choose one candidate
instead of generating an open-ended label:

```bash
python -m deepseekcell_ft.cli benchmark-lora-rerank \
  --marker-db data/raw/panglaodb.normalized.cl.curated.csv \
  --base-model /root/autodl-tmp/models/deepseek-llm-7b-chat \
  --adapter models/deepseekcell-ft-lora-label-overlap \
  --input data/processed/panglaodb_cl_curated_label_overlap_splits/test.jsonl \
  --output outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl \
  --top-k 5
```

Each prediction row includes the candidate list, marker-overlap scores, and
`selection_source`, so reranker behavior can be audited.

Audit whether reranking helped or harmed the marker-overlap top candidate:

```bash
python -m deepseekcell_ft.cli analyze-rerank-predictions \
  --predictions outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl \
  --examples-output outputs/deepseek_lora_rerank_harm_examples.csv \
  --max-examples 50
```

## Stress Test Noisy Marker Lists

The curated PanglaoDB split is almost saturated by marker overlap. Create a
harder test split by dropping true markers and adding distractors:

```bash
python -m deepseekcell_ft.cli perturb-markers \
  --input data/processed/panglaodb_cl_curated_label_overlap_splits/test.jsonl \
  --output data/processed/panglaodb_cl_curated_label_overlap_splits/test.perturbed.drop50_noise3.jsonl \
  --marker-db data/raw/panglaodb.normalized.cl.curated.csv \
  --drop-rate 0.5 \
  --add-noise-markers 3 \
  --seed 23

python -m deepseekcell_ft.cli benchmark-marker-overlap \
  --marker-db data/raw/panglaodb.normalized.cl.curated.csv \
  --input data/processed/panglaodb_cl_curated_label_overlap_splits/test.perturbed.drop50_noise3.jsonl \
  --output outputs/marker_overlap_label_overlap_perturbed_drop50_noise3.jsonl

python -m deepseekcell_ft.cli benchmark-lora-rerank \
  --marker-db data/raw/panglaodb.normalized.cl.curated.csv \
  --base-model /root/autodl-tmp/models/deepseek-llm-7b-chat \
  --adapter models/deepseekcell-ft-lora-label-overlap \
  --input data/processed/panglaodb_cl_curated_label_overlap_splits/test.perturbed.drop50_noise3.jsonl \
  --output outputs/deepseek_lora_rerank_label_overlap_perturbed_drop50_noise3.jsonl \
  --top-k 5

python -m deepseekcell_ft.cli analyze-rerank-predictions \
  --predictions outputs/deepseek_lora_rerank_label_overlap_perturbed_drop50_noise3.jsonl \
  --examples-output outputs/deepseek_lora_rerank_perturbed_drop50_noise3_harm_examples.csv \
  --max-examples 50
```

To run a small robustness grid after the first perturbation succeeds:

```bash
BASE_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
bash scripts/run_noise_grid_autodl.sh
```

If you refreshed the code by moving the old project to
`DeepSeek-FT.backup.<timestamp>`, the trained adapter may still be in the
backup folder. In that case, either copy it back into `models/` or pass
`ADAPTER=/root/autodl-tmp/DeepSeek-FT.backup.<timestamp>/models/deepseekcell-ft-lora-label-overlap`.

## Artifacts To Download

After training, download these paths:

- `models/deepseekcell-ft-lora-label-overlap/`
- `outputs/finetune_preflight_label_overlap.gpu.json`
- `outputs/deepseek_lora_label_overlap_predictions.jsonl`
- `outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl`
- `outputs/deepseek_lora_label_overlap_errors.csv`
- `outputs/deepseek_prompt_label_overlap_predictions.jsonl`
- `outputs/deepseek_prompt_label_overlap_predictions.mapped.jsonl`
- `outputs/deepseek_prompt_label_overlap_errors.csv`
- `outputs/qwen25_7b_prompt_label_overlap_predictions.jsonl`
- `outputs/qwen25_7b_prompt_label_overlap_predictions.mapped.jsonl`
- `outputs/qwen25_7b_prompt_label_overlap_errors.csv`
- `outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl`
- `outputs/deepseek_lora_rerank_harm_examples.csv`
- `outputs/marker_overlap_label_overlap_perturbed_drop*_noise*.jsonl`
- `outputs/deepseek_lora_rerank_label_overlap_perturbed_drop*_noise*.jsonl`
- `outputs/deepseek_lora_rerank_perturbed_drop*_noise*_harm_examples.csv`
- Any terminal log you captured for the training run

For the grouped run, also download:

- `models/deepseekcell-ft-lora-grouped/`
- `outputs/finetune_preflight_grouped.gpu.json`

To bundle the label-overlap run before stopping the GPU instance:

```bash
tar -czf deepseekcell-ft-results-label-overlap.tar.gz \
  models/deepseekcell-ft-lora-label-overlap \
  outputs/*prompt_label_overlap_predictions*.jsonl \
  outputs/*prompt_label_overlap_errors.csv \
  outputs/deepseek_lora_label_overlap_predictions.jsonl \
  outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl \
  outputs/deepseek_lora_label_overlap_errors.csv \
  outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl \
  outputs/deepseek_lora_rerank_harm_examples.csv \
  outputs/marker_overlap_label_overlap_perturbed_drop*_noise*.jsonl \
  outputs/deepseek_lora_rerank_label_overlap_perturbed_drop*_noise*.jsonl \
  outputs/deepseek_lora_rerank_perturbed_drop*_noise*_harm_examples.csv \
  outputs/panglaodb_cl_curated_marker_overlap_label_overlap.jsonl \
  data/processed/panglaodb_cl_curated_label_overlap_splits/test.perturbed.drop*_noise*.jsonl \
  outputs/finetune_preflight_label_overlap.gpu.json
```

Download `deepseekcell-ft-results-label-overlap.tar.gz` from
`/root/autodl-tmp/DeepSeek-FT/`.

For final local reporting, extract both archives if available:

```powershell
tar -xzf .\deepseekcell-ft-results-label-overlap.tar.gz
tar -xzf .\deepseekcell-ft-results-noise-grid.tar.gz
.\scripts\run_experiment_summary.ps1
python .\scripts\render_experiment_figures.py
```

The summary script reuses existing preflight JSON files by default. Pass
`-RefreshPreflight` only when you intentionally want to regenerate local
preflight reports.

If the label-overlap archive was not downloaded before refreshing the project,
recreate it on AutoDL by searching the current project and backup folders:

```bash
cd /root/autodl-tmp/DeepSeek-FT
bash scripts/bundle_label_overlap_results_autodl.sh
```

This writes `deepseekcell-ft-results-label-overlap.tar.gz` in the current
project folder when the clean LoRA outputs are still available in
`/root/autodl-tmp/DeepSeek-FT*`.

## Notes

- Do not use `ALLOW_CPU=1` for real 7B training. It is only for tiny smoke tests.
- Keep the model license and access requirements for the selected base model in
  mind, especially if switching from DeepSeek to Llama or Qwen.
- The current local Windows OpenMP warning is not a reason to force unsafe
  OpenMP settings. Prefer a clean Linux CUDA PyTorch environment on AutoDL.
