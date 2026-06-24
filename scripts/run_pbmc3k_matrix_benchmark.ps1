param(
  [string]$Adata = "data/matrix/pbmc3k_tutorial_labeled.h5ad",
  [string]$Tag = "pbmc3k",
  [int]$NTop = 25,
  [switch]$SkipPrepare
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  if (-not $SkipPrepare) {
    python scripts/prepare_pbmc3k_tutorial_h5ad.py --output $Adata
    if ($LASTEXITCODE -ne 0) { throw "prepare_pbmc3k_tutorial_h5ad.py failed" }
  }

  .\scripts\run_matrix_marker_benchmark.ps1 `
    -Adata $Adata `
    -Tissue PBMC `
    -Tag $Tag `
    -GroupBy louvain `
    -LabelKey cell_type `
    -OntologyKey cell_ontology_id `
    -NTop $NTop `
    -NoNormalize
}
finally {
  Pop-Location
}
