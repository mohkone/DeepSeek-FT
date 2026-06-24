param(
  [string]$SplitDir = "data/processed/panglaodb_cl_curated_label_overlap_splits",
  [string]$PreflightOutput = "outputs/finetune_preflight_label_overlap.gpu.json",
  [string]$BaseModel = "deepseek-ai/deepseek-llm-7b-chat",
  [string]$ModelOutputDir = "models/deepseekcell-ft-lora-label-overlap",
  [int]$MaxSeqLength = 2048,
  [int]$PerDeviceTrainBatchSize = 1,
  [int]$GradientAccumulationSteps = 8,
  [double]$LearningRate = 2e-4,
  [double]$NumTrainEpochs = 3.0,
  [int]$LoraR = 16,
  [int]$LoraAlpha = 32,
  [double]$LoraDropout = 0.05,
  [string]$GroupBy = "",
  [switch]$DisableGroupCheck,
  [switch]$AllowCpu
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

  $preflightArgs = @(
    "preflight-finetune",
    "--split-dir", $SplitDir,
    "--output", $PreflightOutput,
    "--base-model", $BaseModel,
    "--model-output-dir", $ModelOutputDir,
    "--max-seq-length", $MaxSeqLength
  )
  if ($DisableGroupCheck -or [string]::IsNullOrWhiteSpace($GroupBy)) {
    $preflightArgs += "--disable-group-check"
  }
  else {
    $preflightArgs += @("--group-by", $GroupBy)
  }

  Invoke-DeepSeekCellCli @preflightArgs

  $preflight = Get-Content -Path $PreflightOutput -Raw | ConvertFrom-Json
  $hasAccelerator = [bool]$preflight.hardware.cuda_available -or [bool]$preflight.hardware.mps_available
  if (-not $hasAccelerator -and -not $AllowCpu) {
    $warnings = ($preflight.warnings -join "; ")
    throw "No GPU accelerator detected. Refusing to launch LoRA training. Use -AllowCpu only for tiny smoke tests. Preflight warnings: $warnings"
  }

  Invoke-DeepSeekCellCli train-lora `
    --base-model $BaseModel `
    --train-jsonl (Join-Path $SplitDir "train.jsonl") `
    --validation-jsonl (Join-Path $SplitDir "validation.jsonl") `
    --output-dir $ModelOutputDir `
    --max-seq-length $MaxSeqLength `
    --per-device-train-batch-size $PerDeviceTrainBatchSize `
    --gradient-accumulation-steps $GradientAccumulationSteps `
    --learning-rate $LearningRate `
    --num-train-epochs $NumTrainEpochs `
    --lora-r $LoraR `
    --lora-alpha $LoraAlpha `
    --lora-dropout $LoraDropout
}
finally {
  Pop-Location
}
