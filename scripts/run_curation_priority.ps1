param(
  [string]$Curation = "outputs/panglaodb_cl_curation_reviewed.csv",
  [string]$SplitDir = "data/processed/panglaodb_cl_curated_grouped_splits",
  [string]$Output = "outputs/panglaodb_cl_curation_priority.csv"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  $env:PYTHONPATH = (Resolve-Path "src").Path

  python -m deepseekcell_ft.cli prioritize-ontology-curation `
    --curation $Curation `
    --split-dir $SplitDir `
    --output $Output
}
finally {
  Pop-Location
}
