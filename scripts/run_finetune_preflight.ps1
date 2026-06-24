param(
  [string]$SplitDir = "data/processed/panglaodb_cl_curated_grouped_splits",
  [string]$Output = "outputs/finetune_preflight.json",
  [string]$BaseModel = "deepseek-ai/deepseek-llm-7b-chat",
  [string]$ModelOutputDir = "models/deepseekcell-ft-lora",
  [int]$MaxSeqLength = 2048,
  [string]$GroupBy = "tissue,cell_type,source"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  $env:PYTHONPATH = (Resolve-Path "src").Path

  python -m deepseekcell_ft.cli preflight-finetune `
    --split-dir $SplitDir `
    --output $Output `
    --base-model $BaseModel `
    --model-output-dir $ModelOutputDir `
    --max-seq-length $MaxSeqLength `
    --group-by $GroupBy

  if ($LASTEXITCODE -ne 0) {
    throw "preflight-finetune failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
