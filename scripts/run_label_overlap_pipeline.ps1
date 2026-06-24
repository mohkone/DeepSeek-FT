param(
  [string]$CuratedMarkerDb = "data/raw/panglaodb.normalized.cl.curated.csv",
  [string]$InstructionJsonl = "data/processed/panglaodb.cl.curated.instructions.jsonl",
  [string]$SplitDir = "data/processed/panglaodb_cl_curated_label_overlap_splits",
  [string]$PredictionJsonl = "outputs/panglaodb_cl_curated_marker_overlap_label_overlap.jsonl",
  [string]$PreflightOutput = "outputs/finetune_preflight_label_overlap.json",
  [string]$BaseModel = "deepseek-ai/deepseek-llm-7b-chat",
  [string]$ModelOutputDir = "models/deepseekcell-ft-lora-label-overlap",
  [int]$MaxSeqLength = 2048
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

  Invoke-DeepSeekCellCli build-dataset `
    --input $CuratedMarkerDb `
    --output $InstructionJsonl `
    --examples-per-record 4 `
    --min-markers 3 `
    --max-markers 10

  Invoke-DeepSeekCellCli split-stratified `
    --input $InstructionJsonl `
    --output-dir $SplitDir `
    --stratify-by cell_type

  Invoke-DeepSeekCellCli benchmark-marker-overlap `
    --marker-db $CuratedMarkerDb `
    --input (Join-Path $SplitDir "test.jsonl") `
    --output $PredictionJsonl

  Invoke-DeepSeekCellCli preflight-finetune `
    --split-dir $SplitDir `
    --output $PreflightOutput `
    --base-model $BaseModel `
    --model-output-dir $ModelOutputDir `
    --max-seq-length $MaxSeqLength `
    --disable-group-check
}
finally {
  Pop-Location
}
