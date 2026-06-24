param(
  [string]$Adata = "data/matrix/baron_pancreas_labeled.h5ad",
  [string]$Tag = "baron_pancreas",
  [int]$NTop = 25,
  [switch]$SkipPrepare
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  if (-not $SkipPrepare) {
    python scripts/prepare_baron_pancreas_h5ad.py --output $Adata
    if ($LASTEXITCODE -ne 0) { throw "prepare_baron_pancreas_h5ad.py failed" }
  }

  .\scripts\run_matrix_marker_benchmark.ps1 `
    -Adata $Adata `
    -Tissue Pancreas `
    -Tag $Tag `
    -GroupBy cell_type `
    -LabelKey cell_type `
    -OntologyKey cell_ontology_id `
    -NTop $NTop `
    -NoNormalize
}
finally {
  Pop-Location
}
