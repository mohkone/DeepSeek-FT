param(
  [string]$Adata = "data/matrix/zeisel_brain_labeled.h5ad",
  [string]$Tag = "zeisel_brain",
  [int]$NTop = 25,
  [switch]$SkipPrepare
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  if (-not $SkipPrepare) {
    python scripts/prepare_zeisel_brain_h5ad.py --output $Adata
    if ($LASTEXITCODE -ne 0) { throw "prepare_zeisel_brain_h5ad.py failed" }
  }

  .\scripts\run_matrix_marker_benchmark.ps1 `
    -Adata $Adata `
    -Tissue Brain `
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
