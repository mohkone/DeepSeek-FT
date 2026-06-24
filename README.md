# DeepSeekCell-FT

DeepSeekCell-FT is a research scaffold for evaluating fine-tuned and
candidate-constrained instruction-following large language models for
single-cell RNA-seq cell type annotation from marker genes. It supports marker
evidence ingestion, synthetic instruction generation, LoRA fine-tuning adapters,
prompt-only annotation, marker-overlap baselines, candidate reranking,
ontology-aware evaluation, robustness analysis, and manuscript drafting.

The project is intentionally split into a lightweight core and optional heavy
adapters. The core runs with the Python standard library. Training and
single-cell workflows require optional dependencies.

## Citation and Archive

[![DOI](https://zenodo.org/badge/1279602640.svg)](https://doi.org/10.5281/zenodo.20837447)

Archived release DOI: [10.5281/zenodo.20837447](https://doi.org/10.5281/zenodo.20837447).

## Research Question

Is fine-tuned open-ended generation reliable enough for ontology-grounded cell
type annotation from marker genes, or are LLMs more useful as constrained
rerankers over evidence-backed candidate labels?

## Quick Start

Either install the package once:

```powershell
python -m pip install -e .
```

or set `PYTHONPATH` in each new PowerShell session:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
```

Then run:

```powershell
python -m unittest discover -s tests
python -m deepseekcell_ft.cli build-dataset `
  --input data/raw/marker_evidence.example.csv `
  --output data/processed/instructions.jsonl `
  --examples-per-record 8
python -m deepseekcell_ft.cli annotate `
  --marker-db data/raw/marker_evidence.example.csv `
  --tissue PBMC `
  --markers "IL7R,LTB,MALAT1,IL32"
python -m deepseekcell_ft.cli benchmark-marker-overlap `
  --marker-db data/raw/marker_evidence.example.csv `
  --input data/processed/splits/test.jsonl `
  --output outputs/marker_overlap_predictions.jsonl
```

For the complete example workflow, run:

```powershell
.\scripts\run_example_pipeline.ps1
```

For a real PanglaoDB plus Cell Ontology smoke benchmark, run:

```powershell
.\scripts\run_panglaodb_cl_pipeline.ps1
```

## Project Layout

```text
configs/                 Experiment configuration templates
data/raw/                User-provided marker evidence files
data/processed/          Generated instruction datasets and splits
manuscript/              Paper draft
src/deepseekcell_ft/     Python package
tests/                   Standard-library unit tests
```

## Data Contract

Marker evidence CSV files should include at least:

```csv
tissue,cell_type,cell_ontology_id,markers,source,evidence
PBMC,CD4+ T cell,CL:0000624,"IL7R,LTB,IL32",CellMarker,"Canonical helper T markers"
```

Accepted marker columns are `markers`, `positive_markers`, or
`cluster_markers`. Markers may be separated by commas, semicolons, pipes, or
whitespace.

## Real Marker Data Workflow

For external sources such as CellMarker or PanglaoDB, first normalize downloaded
tables into the standard schema:

```powershell
python -m deepseekcell_ft.cli normalize-markers `
  --input data/raw/cellmarker_raw.example.csv `
  --output data/raw/cellmarker.normalized.example.csv `
  --source CellMarker `
  --species Human `
  --tissue-column tissueType `
  --cell-type-column cellName `
  --marker-column geneSymbol `
  --cl-id-column CellOntologyID `
  --species-column speciesType `
  --evidence-column PMID
```

For a real CellMarker download, replace the input and output paths:

```powershell
python -m deepseekcell_ft.cli normalize-markers `
  --input data/raw/cellmarker_raw.csv `
  --output data/raw/cellmarker.normalized.csv `
  --source CellMarker `
  --species Human `
  --tissue-column tissueType `
  --cell-type-column cellName `
  --marker-column geneSymbol `
  --cl-id-column CellOntologyID `
  --species-column speciesType `
  --evidence-column PMID
```

Then validate and merge normalized sources:

```powershell
python -m deepseekcell_ft.cli validate-marker-db `
  --input data/raw/cellmarker.normalized.csv
python -m deepseekcell_ft.cli merge-marker-dbs `
  --inputs data/raw/cellmarker.normalized.csv data/raw/panglaodb.normalized.csv `
  --output data/raw/marker_evidence.combined.csv `
  --min-markers 2
```

See `data/sources/README.md` for source notes and links.

You can also download PanglaoDB markers directly:

```powershell
python -m deepseekcell_ft.cli download-panglaodb-markers `
  --output data/raw/panglaodb_markers.tsv
python -m deepseekcell_ft.cli normalize-markers `
  --input data/raw/panglaodb_markers.tsv `
  --output data/raw/panglaodb.normalized.csv `
  --source PanglaoDB `
  --species Human `
  --min-markers 2
```

To enrich marker records with Cell Ontology IDs:

```powershell
python -m deepseekcell_ft.cli download-cell-ontology `
  --output data/raw/cl.obo
python -m deepseekcell_ft.cli build-ontology-map `
  --input data/raw/cl.obo `
  --output data/raw/cell_ontology_labels.csv `
  --ambiguous-output data/raw/cell_ontology_labels.ambiguous.csv
python -m deepseekcell_ft.cli map-marker-db-ontology `
  --marker-db data/raw/panglaodb.normalized.csv `
  --ontology-map data/raw/cell_ontology_labels.csv `
  --output data/raw/panglaodb.normalized.cl.csv `
  --unmapped-output outputs/panglaodb_unmapped_cl.csv
python -m deepseekcell_ft.cli propose-ontology-curation `
  --unmapped outputs/panglaodb_unmapped_cl.csv `
  --ontology-map data/raw/cell_ontology_labels.csv `
  --output outputs/panglaodb_cl_curation_template.csv
python -m deepseekcell_ft.cli auto-accept-ontology-curation `
  --curation outputs/panglaodb_cl_curation_template.csv `
  --output outputs/panglaodb_cl_curation_autoaccepted.csv
python -m deepseekcell_ft.cli accept-ontology-suggestion `
  --curation outputs/panglaodb_cl_curation_template.csv `
  --output outputs/panglaodb_cl_curation_reviewed.csv `
  --cell-type "Bergmann glia" `
  --rank 1 `
  --notes "reviewed manually"
python -m deepseekcell_ft.cli accept-ontology-decisions `
  --curation outputs/panglaodb_cl_curation_template.csv `
  --decisions data/curation/panglaodb_cl_decisions.example.csv `
  --output outputs/panglaodb_cl_curation_reviewed.csv
```

After adding reviewed decisions, rebuild the curated dataset and benchmark:

```powershell
.\scripts\run_reviewed_curation_pipeline.ps1
```

To decide which remaining labels to review first, rank them by split presence:

```powershell
.\scripts\run_curation_priority.ps1
```

For paper-oriented experiments, prefer a grouped split so augmented examples
from the same marker record do not leak across splits:

```powershell
python -m deepseekcell_ft.cli split-grouped `
  --input data/processed/panglaodb.instructions.jsonl `
  --output-dir data/processed/panglaodb_grouped_splits `
  --group-by tissue,cell_type,source
```

This grouped split is a hard label-held-out generalization benchmark. For a
standard in-distribution fine-tuning comparison, also build a label-overlap
split:

```powershell
.\scripts\run_label_overlap_pipeline.ps1
```

The label-overlap pipeline writes:

- `data/processed/panglaodb_cl_curated_label_overlap_splits`
- `outputs/panglaodb_cl_curated_marker_overlap_label_overlap.jsonl`
- `outputs/finetune_preflight_label_overlap.json`

To regenerate manuscript-ready baseline tables from the current benchmark and
preflight outputs:

```powershell
.\scripts\run_experiment_summary.ps1
```

This writes `outputs/experiment_summary.json` and
`outputs/experiment_summary.md`.

Generated instruction examples can be exported as either:

- `chat`: OpenAI/Hugging Face-style `messages` JSONL
- `instruction`: instruction/input/output JSONL

## Matrix-Derived Benchmarks

For reviewer-facing experiments that start from real expression matrices rather
than curated marker records, use the matrix benchmark runbook:
`docs/matrix_benchmark_runbook.md`.

The generic PowerShell launcher is:

```powershell
.\scripts\run_pbmc3k_matrix_benchmark.ps1
```

This writes a standard marker evidence CSV, a one-example-per-cluster
instruction JSONL, and a marker-overlap benchmark output. The same marker
instructions can then be passed to LoRA, candidate reranking, or prompt-only
benchmark commands. A SingleR wrapper is provided at
`scripts/singler_cluster_baseline.R`; it exports H5AD to Matrix Market before
calling R so AutoDL runs do not depend on the reticulate/zellkonverter bridge.

After the LoRA adapter is available, generate the PBMC3k comparison table:

```powershell
.\scripts\run_pbmc3k_full_comparison.ps1
```

This writes `outputs/pbmc3k.comparison.md`,
`outputs/pbmc3k.comparison.csv`, and `outputs/pbmc3k.comparison.json` with
marker-overlap, DeepSeek LoRA rerank, SingleR, and optional prompt-only metrics.

For a second matrix-derived pancreas benchmark, run Baron pancreas:

```powershell
.\scripts\run_baron_pancreas_matrix_benchmark.ps1
```

On AutoDL, after the base model and LoRA adapter are available:

```bash
SKIP_SINGLER=1 \
BASE_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
bash scripts/run_baron_pancreas_full_comparison.sh
```

For a mouse brain matrix-derived validation dataset using the UCSC Cell Browser Zeisel
2015 dataset:

```powershell
.\scripts\run_zeisel_brain_matrix_benchmark.ps1
```

On AutoDL:

```bash
SKIP_SINGLER=1 \
BASE_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
bash scripts/run_zeisel_brain_full_comparison.sh
```

To add the expected traditional SingleR baseline for all three matrix-derived
datasets on AutoDL:

```bash
bash scripts/setup_singler_conda_autodl.sh
bash scripts/run_matrix_singler_baselines.sh
```

## Optional Training Dependencies

Before installing GPU/training packages, run a preflight audit of the curated
splits:

```powershell
.\scripts\run_finetune_preflight.ps1
```

The report is written to `outputs/finetune_preflight.json` and summarizes split
sizes, Cell Ontology coverage, rough token lengths, group leakage, label overlap,
optional training dependency status, and GPU/accelerator availability.

```powershell
python -m pip install -e ".[train,single-cell,dev]"
```

Then run LoRA fine-tuning from a GPU-enabled machine. On Windows/PowerShell:

```powershell
.\scripts\run_lora_training.ps1
```

On Linux GPU hosts such as AutoDL:

```bash
bash scripts/run_lora_training.sh
```

If you are still on local Windows, package the project first and upload the zip
to AutoDL:

```powershell
.\scripts\package_for_autodl.ps1
```

The launcher reruns preflight and refuses to start 7B LoRA training if no CUDA
or MPS accelerator is detected. It defaults to the label-overlap split, which
is the standard first fine-tuning comparison. To train the label-held-out
grouped split instead:

```powershell
.\scripts\run_lora_training.ps1 `
  -SplitDir data/processed/panglaodb_cl_curated_grouped_splits `
  -PreflightOutput outputs/finetune_preflight_grouped.gpu.json `
  -ModelOutputDir models/deepseekcell-ft-lora-grouped `
  -GroupBy "tissue,cell_type,source"
```

Linux/AutoDL equivalent:

```bash
SPLIT_DIR=data/processed/panglaodb_cl_curated_grouped_splits \
PREFLIGHT_OUTPUT=outputs/finetune_preflight_grouped.gpu.json \
MODEL_OUTPUT_DIR=models/deepseekcell-ft-lora-grouped \
GROUP_BY=tissue,cell_type,source \
bash scripts/run_lora_training.sh
```

The equivalent direct CLI command for the label-overlap split is:

```powershell
python -m deepseekcell_ft.cli train-lora `
  --base-model deepseek-ai/deepseek-llm-7b-chat `
  --train-jsonl data/processed/panglaodb_cl_curated_label_overlap_splits/train.jsonl `
  --validation-jsonl data/processed/panglaodb_cl_curated_label_overlap_splits/validation.jsonl `
  --output-dir models/deepseekcell-ft-lora-label-overlap
```

The training adapter is deliberately thin. It keeps configuration explicit and
lets each lab choose the exact DeepSeek, Llama, or Qwen checkpoint allowed by
its compute and license constraints. A 7B LoRA run should be launched from a
GPU-enabled environment; CPU-only PyTorch is suitable for pipeline checks, not
full model fine-tuning.

For an AutoDL-specific GPU checklist, see `docs/autodl_gpu_runbook.md`.

Before or after LoRA training, run the prompt-only baselines that reviewers will
expect. On AutoDL, this runs prompt-only DeepSeek plus one additional prompt-only
model, Qwen2.5-7B-Instruct by default:

```bash
DEEPSEEK_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
SECOND_MODEL=Qwen/Qwen2.5-7B-Instruct \
SECOND_MODEL_NAME=qwen25_7b \
bash scripts/run_prompt_baselines_autodl.sh
```

The direct CLI command for one prompt-only model is:

```bash
python -m deepseekcell_ft.cli benchmark-prompt \
  --base-model /root/autodl-tmp/models/deepseek-llm-7b-chat \
  --input data/processed/panglaodb_cl_curated_label_overlap_splits/test.jsonl \
  --output outputs/deepseek_prompt_label_overlap_predictions.jsonl
```

As with open-ended LoRA outputs, map generated labels back to curated Cell
Ontology IDs before reporting ontology accuracy:

```bash
python -m deepseekcell_ft.cli map-prediction-ontology \
  --predictions outputs/deepseek_prompt_label_overlap_predictions.jsonl \
  --marker-db data/raw/panglaodb.normalized.cl.curated.csv \
  --output outputs/deepseek_prompt_label_overlap_predictions.mapped.jsonl
```

After training, benchmark the saved adapter on the label-overlap test split:

```bash
python -m deepseekcell_ft.cli benchmark-lora \
  --base-model /root/autodl-tmp/models/deepseek-llm-7b-chat \
  --adapter models/deepseekcell-ft-lora-label-overlap \
  --input data/processed/panglaodb_cl_curated_label_overlap_splits/test.jsonl \
  --output outputs/deepseek_lora_label_overlap_predictions.jsonl
```

Then inspect mismatches:

```bash
python -m deepseekcell_ft.cli analyze-predictions \
  --predictions outputs/deepseek_lora_label_overlap_predictions.jsonl \
  --examples-output outputs/deepseek_lora_label_overlap_errors.csv \
  --max-examples 50
```

For Cell Ontology accuracy, report both raw generated CL IDs and label-mapped
CL IDs. The mapped file replaces generated `pred_cl_id` values using the
curated marker database while preserving `original_pred_cl_id`:

```bash
python -m deepseekcell_ft.cli map-prediction-ontology \
  --predictions outputs/deepseek_lora_label_overlap_predictions.jsonl \
  --marker-db data/raw/panglaodb.normalized.cl.curated.csv \
  --output outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl

python -m deepseekcell_ft.cli evaluate \
  --predictions outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl
```

The next constrained experiment uses marker-overlap to propose candidate labels
and the LoRA adapter only to rerank or justify one of those candidates:

```bash
python -m deepseekcell_ft.cli benchmark-lora-rerank \
  --marker-db data/raw/panglaodb.normalized.cl.curated.csv \
  --base-model /root/autodl-tmp/models/deepseek-llm-7b-chat \
  --adapter models/deepseekcell-ft-lora-label-overlap \
  --input data/processed/panglaodb_cl_curated_label_overlap_splits/test.jsonl \
  --output outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl \
  --top-k 5
```

Audit whether reranking helped or harmed the marker-overlap top candidate:

```bash
python -m deepseekcell_ft.cli analyze-rerank-predictions \
  --predictions outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl \
  --examples-output outputs/deepseek_lora_rerank_harm_examples.csv \
  --max-examples 50
```

For a harder stress test, perturb the label-overlap test split by dropping
markers and adding distractors, then rerun marker-overlap and reranking:

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
```

## Evaluation

Prediction files should be JSONL with these fields:

```json
{"y_true":"CD4+ T cell","y_pred":"CD4+ T cell","true_cl_id":"CL:0000624","pred_cl_id":"CL:0000624","confidence":0.84,"runtime_seconds":0.12}
```

Run:

```powershell
python -m deepseekcell_ft.cli evaluate --predictions outputs/predictions.jsonl
```

Metrics include accuracy, macro F1, Cell Ontology ID accuracy, expected
calibration error, mean runtime, and total runtime.

## Manuscript

The draft manuscript is in
`manuscript/deepseekcell_ft_article.md`. It is written as a study protocol and
paper draft with result placeholders, because this repository has not yet run
the full benchmark.
