param(
  [string]$PanglaoRaw = "data/raw/panglaodb_markers.tsv",
  [string]$PanglaoNormalized = "data/raw/panglaodb.normalized.csv",
  [string]$CellOntologyObo = "data/raw/cl.obo",
  [string]$CellOntologyMap = "data/raw/cell_ontology_labels.csv",
  [string]$CellOntologyAmbiguous = "data/raw/cell_ontology_labels.ambiguous.csv",
  [string]$PanglaoWithCl = "data/raw/panglaodb.normalized.cl.csv",
  [string]$InstructionJsonl = "data/processed/panglaodb.cl.instructions.jsonl",
  [string]$SplitDir = "data/processed/panglaodb_cl_grouped_splits",
  [string]$PredictionJsonl = "outputs/panglaodb_cl_marker_overlap_grouped.jsonl",
  [string]$UnmappedOutput = "outputs/panglaodb_unmapped_cl.csv",
  [string]$CurationTemplate = "outputs/panglaodb_cl_curation_template.csv",
  [string]$CurationAutoaccepted = "outputs/panglaodb_cl_curation_autoaccepted.csv"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  $env:PYTHONPATH = (Resolve-Path "src").Path

  if (-not (Test-Path $PanglaoRaw)) {
    python -m deepseekcell_ft.cli download-panglaodb-markers `
      --output $PanglaoRaw
  }

  python -m deepseekcell_ft.cli normalize-markers `
    --input $PanglaoRaw `
    --output $PanglaoNormalized `
    --source PanglaoDB `
    --species Human `
    --min-markers 2

  if (-not (Test-Path $CellOntologyObo)) {
    python -m deepseekcell_ft.cli download-cell-ontology `
      --output $CellOntologyObo
  }

  python -m deepseekcell_ft.cli build-ontology-map `
    --input $CellOntologyObo `
    --output $CellOntologyMap `
    --ambiguous-output $CellOntologyAmbiguous

  python -m deepseekcell_ft.cli map-marker-db-ontology `
    --marker-db $PanglaoNormalized `
    --ontology-map $CellOntologyMap `
    --output $PanglaoWithCl `
    --unmapped-output $UnmappedOutput

  python -m deepseekcell_ft.cli propose-ontology-curation `
    --unmapped $UnmappedOutput `
    --ontology-map $CellOntologyMap `
    --output $CurationTemplate `
    --max-suggestions 5

  python -m deepseekcell_ft.cli auto-accept-ontology-curation `
    --curation $CurationTemplate `
    --output $CurationAutoaccepted `
    --min-score 0.8

  python -m deepseekcell_ft.cli build-dataset `
    --input $PanglaoWithCl `
    --output $InstructionJsonl `
    --examples-per-record 4 `
    --min-markers 3 `
    --max-markers 10

  python -m deepseekcell_ft.cli split-grouped `
    --input $InstructionJsonl `
    --output-dir $SplitDir `
    --group-by tissue,cell_type,source

  python -m deepseekcell_ft.cli benchmark-marker-overlap `
    --marker-db $PanglaoWithCl `
    --input (Join-Path $SplitDir "test.jsonl") `
    --output $PredictionJsonl
}
finally {
  Pop-Location
}
