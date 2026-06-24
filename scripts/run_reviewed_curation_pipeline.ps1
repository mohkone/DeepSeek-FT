param(
  [string]$BaseMarkerDb = "data/raw/panglaodb.normalized.cl.csv",
  [string]$CurationTemplate = "outputs/panglaodb_cl_curation_template.csv",
  [string]$Decisions = "data/curation/panglaodb_cl_decisions.example.csv",
  [string]$ReviewedCuration = "outputs/panglaodb_cl_curation_reviewed.csv",
  [string]$CuratedMarkerDb = "data/raw/panglaodb.normalized.cl.curated.csv",
  [string]$InstructionJsonl = "data/processed/panglaodb.cl.curated.instructions.jsonl",
  [string]$SplitDir = "data/processed/panglaodb_cl_curated_grouped_splits",
  [string]$PredictionJsonl = "outputs/panglaodb_cl_curated_marker_overlap_grouped.jsonl",
  [string]$UnmappedOutput = "outputs/panglaodb_unmapped_cl_after_curation.csv"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-DeepSeekCellCli {
  & python -m deepseekcell_ft.cli @args
  if ($LASTEXITCODE -ne 0) {
    throw "python -m deepseekcell_ft.cli $($args -join ' ') failed with exit code $LASTEXITCODE"
  }
}

Push-Location $ProjectRoot
try {
  $env:PYTHONPATH = (Resolve-Path "src").Path

  Invoke-DeepSeekCellCli accept-ontology-decisions `
    --curation $CurationTemplate `
    --decisions $Decisions `
    --output $ReviewedCuration `
    --skip-missing

  Invoke-DeepSeekCellCli apply-ontology-curation `
    --marker-db $BaseMarkerDb `
    --curation $ReviewedCuration `
    --output $CuratedMarkerDb `
    --unmapped-output $UnmappedOutput

  Invoke-DeepSeekCellCli build-dataset `
    --input $CuratedMarkerDb `
    --output $InstructionJsonl `
    --examples-per-record 4 `
    --min-markers 3 `
    --max-markers 10

  Invoke-DeepSeekCellCli split-grouped `
    --input $InstructionJsonl `
    --output-dir $SplitDir `
    --group-by "tissue,cell_type,source"

  Invoke-DeepSeekCellCli benchmark-marker-overlap `
    --marker-db $CuratedMarkerDb `
    --input (Join-Path $SplitDir "test.jsonl") `
    --output $PredictionJsonl
}
finally {
  Pop-Location
}
