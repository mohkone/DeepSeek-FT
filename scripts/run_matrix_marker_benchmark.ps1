param(
  [Parameter(Mandatory = $true)]
  [string]$Adata,
  [Parameter(Mandatory = $true)]
  [string]$Tissue,
  [string]$Tag = "matrix",
  [string]$GroupBy = "leiden",
  [string]$LabelKey = "",
  [string]$OntologyKey = "",
  [int]$NTop = 25,
  [string]$Method = "wilcoxon",
  [switch]$RunClustering,
  [switch]$NoNormalize
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  $env:PYTHONPATH = (Resolve-Path "src").Path

  $markerDb = "data/raw/$Tag.matrix_markers.csv"
  $instructions = "data/processed/$Tag.matrix.instructions.jsonl"
  $predictions = "outputs/$Tag.matrix_marker_overlap.jsonl"

  $prepareArgs = @(
    "prepare-matrix-benchmark",
    "--adata", $Adata,
    "--output-marker-db", $markerDb,
    "--tissue", $Tissue,
    "--groupby", $GroupBy,
    "--n-top", "$NTop",
    "--method", $Method
  )
  if ($LabelKey) { $prepareArgs += @("--label-key", $LabelKey) }
  if ($OntologyKey) { $prepareArgs += @("--ontology-key", $OntologyKey) }
  if ($RunClustering) { $prepareArgs += "--run-clustering" }
  if ($NoNormalize) { $prepareArgs += "--no-normalize" }

  python -m deepseekcell_ft.cli @prepareArgs
  if ($LASTEXITCODE -ne 0) { throw "prepare-matrix-benchmark failed" }

  python -m deepseekcell_ft.cli validate-marker-db --input $markerDb
  if ($LASTEXITCODE -ne 0) { throw "validate-marker-db failed" }

  python -m deepseekcell_ft.cli build-dataset `
    --input $markerDb `
    --output $instructions `
    --examples-per-record 1 `
    --min-markers $NTop `
    --max-markers $NTop `
    --noise-rate 0
  if ($LASTEXITCODE -ne 0) { throw "build-dataset failed" }

  python -m deepseekcell_ft.cli benchmark-marker-overlap `
    --marker-db $markerDb `
    --input $instructions `
    --output $predictions
  if ($LASTEXITCODE -ne 0) { throw "benchmark-marker-overlap failed" }

  Write-Host "marker_db: $markerDb"
  Write-Host "instructions: $instructions"
  Write-Host "predictions: $predictions"
}
finally {
  Pop-Location
}
