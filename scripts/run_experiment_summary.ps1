param(
  [string]$GroupedSplitDir = "data/processed/panglaodb_cl_curated_grouped_splits",
  [string]$LabelOverlapSplitDir = "data/processed/panglaodb_cl_curated_label_overlap_splits",
  [string]$GroupedPredictions = "outputs/panglaodb_cl_curated_marker_overlap_grouped.jsonl",
  [string]$LabelOverlapPredictions = "outputs/panglaodb_cl_curated_marker_overlap_label_overlap.jsonl",
  [string]$LabelOverlapDeepSeekPromptPredictions = "outputs/deepseek_prompt_label_overlap_predictions.mapped.jsonl",
  [string]$LabelOverlapQwenPromptPredictions = "outputs/qwen25_7b_prompt_label_overlap_predictions.mapped.jsonl",
  [string]$LabelOverlapLlamaPromptPredictions = "outputs/llama3_8b_prompt_label_overlap_predictions.mapped.jsonl",
  [string]$LabelOverlapLoraPredictions = "outputs/deepseek_lora_label_overlap_predictions.mapped.jsonl",
  [string]$LabelOverlapLoraRerankPredictions = "outputs/deepseek_lora_rerank_label_overlap_predictions.jsonl",
  [string]$Drop50MarkerPredictions = "outputs/marker_overlap_label_overlap_perturbed_drop50_noise3.jsonl",
  [string]$Drop50LoraRerankPredictions = "outputs/deepseek_lora_rerank_label_overlap_perturbed_drop50_noise3.jsonl",
  [string]$Drop75MarkerPredictions = "outputs/marker_overlap_label_overlap_perturbed_drop75_noise5.jsonl",
  [string]$Drop75LoraRerankPredictions = "outputs/deepseek_lora_rerank_label_overlap_perturbed_drop75_noise5.jsonl",
  [string]$Drop90MarkerPredictions = "outputs/marker_overlap_label_overlap_perturbed_drop90_noise8.jsonl",
  [string]$Drop90LoraRerankPredictions = "outputs/deepseek_lora_rerank_label_overlap_perturbed_drop90_noise8.jsonl",
  [string]$Pbmc3kMarkerPredictions = "outputs/pbmc3k.matrix_marker_overlap.jsonl",
  [string]$Pbmc3kLoraRerankPredictions = "outputs/pbmc3k.deepseek_lora_rerank.jsonl",
  [string]$Pbmc3kSingleRPredictions = "outputs/pbmc3k.singler.jsonl",
  [string]$BaronMarkerPredictions = "outputs/baron_pancreas.matrix_marker_overlap.jsonl",
  [string]$BaronLoraRerankPredictions = "outputs/baron_pancreas.deepseek_lora_rerank.jsonl",
  [string]$BaronSingleRPredictions = "outputs/baron_pancreas.singler.jsonl",
  [string]$ZeiselMarkerPredictions = "outputs/zeisel_brain.matrix_marker_overlap.jsonl",
  [string]$ZeiselLoraRerankPredictions = "outputs/zeisel_brain.deepseek_lora_rerank.jsonl",
  [string]$ZeiselSingleRPredictions = "outputs/zeisel_brain.singler.jsonl",
  [string]$GroupedPreflight = "outputs/finetune_preflight_grouped.json",
  [string]$LabelOverlapPreflight = "outputs/finetune_preflight_label_overlap.gpu.json",
  [string]$OutputJson = "outputs/experiment_summary.json",
  [string]$OutputMarkdown = "outputs/experiment_summary.md",
  [switch]$RefreshPreflight
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-DeepSeekCellCli {
  & python -m deepseekcell_ft.cli @args
  if ($LASTEXITCODE -ne 0) {
    throw "python -m deepseekcell_ft.cli $($args -join ' ') failed with exit code $LASTEXITCODE"
  }
}

function Invoke-PreflightIfNeeded {
  param(
    [string]$SplitDir,
    [string]$Output,
    [string]$ModelOutputDir,
    [switch]$DisableGroupCheck
  )

  if ((Test-Path $Output) -and -not $RefreshPreflight) {
    Write-Host "Using existing preflight: $Output"
    return
  }

  $args = @(
    "preflight-finetune",
    "--split-dir", $SplitDir,
    "--output", $Output,
    "--base-model", "deepseek-ai/deepseek-llm-7b-chat",
    "--model-output-dir", $ModelOutputDir
  )
  if ($DisableGroupCheck) {
    $args += "--disable-group-check"
  }

  Invoke-DeepSeekCellCli @args
}

Push-Location $ProjectRoot
try {
  $env:PYTHONPATH = (Resolve-Path "src").Path

  Invoke-PreflightIfNeeded `
    -SplitDir $GroupedSplitDir `
    -Output $GroupedPreflight `
    -ModelOutputDir "models/deepseekcell-ft-lora-grouped"

  Invoke-PreflightIfNeeded `
    -SplitDir $LabelOverlapSplitDir `
    -Output $LabelOverlapPreflight `
    -ModelOutputDir "models/deepseekcell-ft-lora-label-overlap" `
    -DisableGroupCheck

  $summaryArgs = @(
    "summarize-experiments",
    "--prediction", "label_held_out_marker_overlap=$GroupedPredictions",
    "--prediction", "label_overlap_marker_overlap=$LabelOverlapPredictions",
    "--preflight", "label_held_out=$GroupedPreflight",
    "--preflight", "label_overlap=$LabelOverlapPreflight",
    "--output-json", $OutputJson,
    "--output-markdown", $OutputMarkdown
  )

  $promptPredictions = @(
    @("label_overlap_deepseek_prompt", $LabelOverlapDeepSeekPromptPredictions),
    @("label_overlap_qwen25_7b_prompt", $LabelOverlapQwenPromptPredictions),
    @("label_overlap_llama3_8b_prompt", $LabelOverlapLlamaPromptPredictions)
  )

  foreach ($prediction in $promptPredictions) {
    $name = $prediction[0]
    $path = $prediction[1]
    if (Test-Path $path) {
      $summaryArgs += @("--prediction", "$name=$path")
    } else {
      Write-Host "Skipping missing optional prediction: $path"
    }
  }

  if (Test-Path $LabelOverlapLoraPredictions) {
    $summaryArgs += @("--prediction", "label_overlap_deepseek_lora=$LabelOverlapLoraPredictions")
  } else {
    Write-Host "Skipping missing optional prediction: $LabelOverlapLoraPredictions"
  }
  if (Test-Path $LabelOverlapLoraRerankPredictions) {
    $summaryArgs += @("--prediction", "label_overlap_deepseek_lora_rerank=$LabelOverlapLoraRerankPredictions")
  } else {
    Write-Host "Skipping missing optional prediction: $LabelOverlapLoraRerankPredictions"
  }

  $optionalPredictions = @(
    @("label_overlap_drop50_noise3_marker_overlap", $Drop50MarkerPredictions),
    @("label_overlap_drop50_noise3_deepseek_lora_rerank", $Drop50LoraRerankPredictions),
    @("label_overlap_drop75_noise5_marker_overlap", $Drop75MarkerPredictions),
    @("label_overlap_drop75_noise5_deepseek_lora_rerank", $Drop75LoraRerankPredictions),
    @("label_overlap_drop90_noise8_marker_overlap", $Drop90MarkerPredictions),
    @("label_overlap_drop90_noise8_deepseek_lora_rerank", $Drop90LoraRerankPredictions),
    @("pbmc3k_matrix_marker_overlap", $Pbmc3kMarkerPredictions),
    @("pbmc3k_matrix_deepseek_lora_rerank", $Pbmc3kLoraRerankPredictions),
    @("pbmc3k_matrix_singler", $Pbmc3kSingleRPredictions),
    @("baron_pancreas_matrix_marker_overlap", $BaronMarkerPredictions),
    @("baron_pancreas_matrix_deepseek_lora_rerank", $BaronLoraRerankPredictions),
    @("baron_pancreas_matrix_singler", $BaronSingleRPredictions),
    @("zeisel_brain_matrix_marker_overlap", $ZeiselMarkerPredictions),
    @("zeisel_brain_matrix_deepseek_lora_rerank", $ZeiselLoraRerankPredictions),
    @("zeisel_brain_matrix_singler", $ZeiselSingleRPredictions)
  )

  foreach ($prediction in $optionalPredictions) {
    $name = $prediction[0]
    $path = $prediction[1]
    if (Test-Path $path) {
      $summaryArgs += @("--prediction", "$name=$path")
    } else {
      Write-Host "Skipping missing optional prediction: $path"
    }
  }

  Invoke-DeepSeekCellCli @summaryArgs
}
finally {
  Pop-Location
}
