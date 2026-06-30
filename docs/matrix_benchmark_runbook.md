# Matrix-Derived Benchmark Runbook

This runbook covers the reviewer-facing benchmark that starts from expression
matrices rather than curated marker records:

```text
AnnData matrix -> clustering -> marker ranking -> marker-list annotation -> evaluation
```

The workflow is dataset-agnostic. Use it for PBMC3k, Baron pancreas, Zeisel
brain, or any `.h5ad` file that contains a gold cell-type label column in
`adata.obs`.

## 1. Install Single-Cell Dependencies

```bash
python -m pip install -e ".[single-cell]"
```

For SingleR, install the R/Bioconductor dependencies in the R environment:

```r
install.packages("BiocManager")
BiocManager::install(c("SingleR", "celldex", "scrapper", "SummarizedExperiment"))
install.packages("jsonlite")
```

On AutoDL/conda systems, the helper below installs the same stack from
conda-forge and bioconda when `Rscript` is not already available:

```bash
bash scripts/setup_singler_conda_autodl.sh
```

## 2. Run PBMC3k First

PBMC3k is the best first matrix benchmark because reviewers recognize it. The
included helper downloads Scanpy's processed PBMC3k object and adds the
standard tutorial louvain-cluster labels and Cell Ontology IDs:

PowerShell:

```powershell
.\scripts\run_pbmc3k_matrix_benchmark.ps1
```

Bash:

```bash
bash scripts/run_pbmc3k_matrix_benchmark.sh
```

Outputs:

```text
data/matrix/pbmc3k_tutorial_labeled.h5ad
data/raw/pbmc3k.matrix_markers.csv
data/processed/pbmc3k.matrix.instructions.jsonl
outputs/pbmc3k.matrix_marker_overlap.jsonl
```

For manuscript wording, call this the "PBMC3k tutorial-labeled" benchmark
unless you replace the tutorial labels with independent expert labels.

## 3. Run The PBMC3k Comparison Table

After LoRA training has produced `models/deepseekcell-ft-lora-label-overlap`,
run the first reviewer-facing matrix comparison:

PowerShell:

```powershell
.\scripts\run_pbmc3k_full_comparison.ps1
```

Bash/AutoDL:

```bash
BASE_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
ADAPTER=models/deepseekcell-ft-lora-label-overlap \
bash scripts/run_pbmc3k_full_comparison.sh
```

This runs the same PBMC3k-derived instruction file through:

- Marker overlap
- DeepSeek LoRA candidate reranking
- scType-style marker-set scoring
- SingleR
- Optional prompt-only inference when `RUN_PROMPT=1` or `-RunPrompt` is used

Outputs:

```text
outputs/pbmc3k.comparison.md
outputs/pbmc3k.comparison.csv
outputs/pbmc3k.comparison.json
```

The comparison table reports `Method`, `Accuracy`, `Macro-F1`, and
`CL Accuracy`. If SingleR labels have not been harmonized to Cell Ontology IDs,
the table reports `NA` for SingleR CL accuracy rather than silently forcing a
broad label mapping.

## 4. Prepare Marker Evidence From Any AnnData

The command below clusters the matrix if `leiden` is not already present,
ranks marker genes with Scanpy `rank_genes_groups`, assigns each cluster the
majority gold label from `adata.obs[cell_type]`, and writes a standard marker
evidence CSV.

PowerShell:

```powershell
.\scripts\run_matrix_marker_benchmark.ps1 `
  -Adata data/matrix/pbmc3k.h5ad `
  -Tissue PBMC `
  -Tag pbmc3k `
  -LabelKey cell_type `
  -OntologyKey cell_ontology_id `
  -RunClustering
```

Bash:

```bash
ADATA=data/matrix/pbmc3k.h5ad \
TISSUE=PBMC \
TAG=pbmc3k \
LABEL_KEY=cell_type \
ONTOLOGY_KEY=cell_ontology_id \
RUN_CLUSTERING=1 \
bash scripts/run_matrix_marker_benchmark.sh
```

Outputs:

```text
data/raw/<tag>.matrix_markers.csv
data/processed/<tag>.matrix.instructions.jsonl
outputs/<tag>.matrix_marker_overlap.jsonl
```

Repeat the same pattern for Baron pancreas and Zeisel brain, changing `ADATA`,
`TISSUE`, `TAG`, and the observed metadata column names.

## 5. Run Baron Pancreas

The Baron pancreas helper uses Scanpy's pancreas integration tutorial object,
filters to `sample=Baron`, and maps the Baron `celltype` labels to standard
labels and Cell Ontology IDs.

PowerShell:

```powershell
.\scripts\run_baron_pancreas_matrix_benchmark.ps1
```

Bash:

```bash
bash scripts/run_baron_pancreas_matrix_benchmark.sh
```

Outputs:

```text
data/matrix/baron_pancreas_labeled.h5ad
data/raw/baron_pancreas.matrix_markers.csv
data/processed/baron_pancreas.matrix.instructions.jsonl
outputs/baron_pancreas.matrix_marker_overlap.jsonl
```

After the LoRA adapter is available on AutoDL, run:

```bash
SKIP_SINGLER=1 \
BASE_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
ADAPTER=models/deepseekcell-ft-lora-label-overlap \
bash scripts/run_baron_pancreas_full_comparison.sh
```

This writes:

```text
outputs/baron_pancreas.comparison.md
outputs/baron_pancreas.comparison.csv
outputs/baron_pancreas.comparison.json
```

## 6. Run Zeisel Brain

The Zeisel brain helper downloads the UCSC Cell Browser `zeisel2015`
expression matrix and metadata, maps clean metadata groups to Cell Ontology IDs,
and skips unresolved ambiguous cells from combined broad classes.

PowerShell:

```powershell
.\scripts\run_zeisel_brain_matrix_benchmark.ps1
```

Bash:

```bash
bash scripts/run_zeisel_brain_matrix_benchmark.sh
```

Outputs:

```text
data/matrix/zeisel_brain_labeled.h5ad
data/raw/zeisel_brain.matrix_markers.csv
data/processed/zeisel_brain.matrix.instructions.jsonl
outputs/zeisel_brain.matrix_marker_overlap.jsonl
```

After the LoRA adapter is available on AutoDL, run:

```bash
SKIP_SINGLER=1 \
BASE_MODEL=/root/autodl-tmp/models/deepseek-llm-7b-chat \
ADAPTER=models/deepseekcell-ft-lora-label-overlap \
bash scripts/run_zeisel_brain_full_comparison.sh
```

This writes:

```text
outputs/zeisel_brain.comparison.md
outputs/zeisel_brain.comparison.csv
outputs/zeisel_brain.comparison.json
```

## 7. Benchmark LoRA Reranking On Matrix Markers

On AutoDL, reuse the saved base model and LoRA adapter:

```bash
python -m deepseekcell_ft.cli benchmark-lora-rerank \
  --marker-db data/raw/pbmc3k.matrix_markers.csv \
  --base-model /root/autodl-tmp/models/deepseek-llm-7b-chat \
  --adapter models/deepseekcell-ft-lora-label-overlap \
  --input data/processed/pbmc3k.matrix.instructions.jsonl \
  --output outputs/pbmc3k.deepseek_lora_rerank.jsonl \
  --top-k 5
```

## 8. Run scType And SingleR

The in-repository scType-style baseline scores each candidate cell type by
positive marker overlap and optional negative marker penalties from columns such
as `negative_markers`. It does not require R:

```bash
python -m deepseekcell_ft.cli benchmark-sctype \
  --marker-db data/raw/pbmc3k.matrix_markers.csv \
  --input data/processed/pbmc3k.matrix.instructions.jsonl \
  --output outputs/pbmc3k.sctype.jsonl
```

To run the three matrix-derived scType baselines together and refresh the
comparison tables:

```bash
bash scripts/run_matrix_sctype_baselines.sh
```

The included wrapper exports the same `.h5ad` to Matrix Market plus metadata,
runs cluster-level SingleR in R, and writes JSONL compatible with
`deepseekcell_ft.cli evaluate`. This avoids the reticulate/basilisk Python bridge
used by `zellkonverter`.

```bash
Rscript scripts/singler_cluster_baseline.R \
  --adata data/matrix/pbmc3k.h5ad \
  --cluster-key leiden \
  --label-key cell_type \
  --ontology-key cell_ontology_id \
  --tissue PBMC \
  --reference hpca \
  --output outputs/pbmc3k.singler.jsonl

python -m deepseekcell_ft.cli evaluate \
  --predictions outputs/pbmc3k.singler.jsonl
```

Available `--reference` values are `hpca`, `blueprint_encode`, and
`mouse_rna_seq`. Use `hpca` or `blueprint_encode` for human PBMC/pancreas and
`mouse_rna_seq` for mouse brain datasets such as Zeisel.

To run the three matrix-derived SingleR baselines together on AutoDL after the
PBMC3k, Baron, and Zeisel `.h5ad` files have been produced:

```bash
bash scripts/run_matrix_singler_baselines.sh
```

This writes `outputs/pbmc3k.singler.jsonl`,
`outputs/baron_pancreas.singler.jsonl`,
`outputs/zeisel_brain.singler.jsonl`, refreshes the three comparison tables,
and packages `singler-matrix-baselines-results.tar.gz` for transfer back to the
Windows workspace.

## 9. Manuscript Interpretation

Report matrix-derived results separately from PanglaoDB marker-record results.
The key reviewer-facing claim should be whether the PanglaoDB conclusions hold
when marker lists are extracted from expression matrices with realistic dropout,
cluster impurity, and preprocessing noise.
