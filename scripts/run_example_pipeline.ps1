param(
  [string]$RawMarkerTable = "data/raw/cellmarker_raw.example.csv",
  [string]$NormalizedMarkerDb = "data/raw/cellmarker.normalized.example.csv",
  [string]$InstructionJsonl = "data/processed/cellmarker.instructions.example.jsonl",
  [string]$SplitDir = "data/processed/cellmarker_splits_example",
  [string]$PredictionJsonl = "outputs/cellmarker_marker_overlap.example.jsonl"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  $env:PYTHONPATH = (Resolve-Path "src").Path

  if (-not (Test-Path $NormalizedMarkerDb)) {
    python -m deepseekcell_ft.cli normalize-markers `
      --input $RawMarkerTable `
      --output $NormalizedMarkerDb `
      --source CellMarker `
      --species Human `
      --tissue-column tissueType `
      --cell-type-column cellName `
      --marker-column geneSymbol `
      --cl-id-column CellOntologyID `
      --species-column speciesType `
      --evidence-column PMID
  }

  python -m deepseekcell_ft.cli validate-marker-db `
    --input $NormalizedMarkerDb

  python -m deepseekcell_ft.cli build-dataset `
    --input $NormalizedMarkerDb `
    --output $InstructionJsonl `
    --examples-per-record 8

  python -m deepseekcell_ft.cli split-grouped `
    --input $InstructionJsonl `
    --output-dir $SplitDir `
    --group-by tissue,cell_type,source

  python -m deepseekcell_ft.cli benchmark-marker-overlap `
    --marker-db $NormalizedMarkerDb `
    --input (Join-Path $SplitDir "test.jsonl") `
    --output $PredictionJsonl
}
finally {
  Pop-Location
}
