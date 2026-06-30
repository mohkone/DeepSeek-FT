param(
  [string]$Adata = "data/matrix/pbmc3k_tutorial_labeled.h5ad",
  [string]$Tag = "pbmc3k",
  [string]$BaseModel = "/root/autodl-tmp/models/deepseek-llm-7b-chat",
  [string]$Adapter = "models/deepseekcell-ft-lora-label-overlap",
  [int]$TopK = 5,
  [int]$NTop = 25,
  [string]$SingleRReference = "hpca",
  [string]$ScTypeTissue = "Immune system",
  [switch]$SkipPrepare,
  [switch]$SkipRerank,
  [switch]$SkipSingleR,
  [switch]$SkipScType,
  [switch]$RunPrompt,
  [string]$PromptModel = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
  $env:PYTHONPATH = (Resolve-Path "src").Path

  .\scripts\run_pbmc3k_matrix_benchmark.ps1 `
    -Adata $Adata `
    -Tag $Tag `
    -NTop $NTop `
    -SkipPrepare:$SkipPrepare

  $markerDb = "data/raw/$Tag.matrix_markers.csv"
  $instructions = "data/processed/$Tag.matrix.instructions.jsonl"
  $markerOutput = "outputs/$Tag.matrix_marker_overlap.jsonl"
  $rerankOutput = "outputs/$Tag.deepseek_lora_rerank.jsonl"
  $singleROutput = "outputs/$Tag.singler.jsonl"
  $scTypeRawOutput = "outputs/$Tag.sctype.raw.jsonl"
  $scTypeOutput = "outputs/$Tag.sctype.jsonl"
  $promptOutput = "outputs/$Tag.prompt.jsonl"
  $promptMappedOutput = "outputs/$Tag.prompt.mapped.jsonl"

  $predictions = @(
    "Marker overlap=$markerOutput"
  )

  if (-not $SkipRerank) {
    python -m deepseekcell_ft.cli benchmark-lora-rerank `
      --marker-db $markerDb `
      --base-model $BaseModel `
      --adapter $Adapter `
      --input $instructions `
      --output $rerankOutput `
      --top-k $TopK
    if ($LASTEXITCODE -ne 0) { throw "benchmark-lora-rerank failed" }
    $predictions += "DeepSeek LoRA rerank=$rerankOutput"
  }

  if (-not $SkipScType) {
    & Rscript scripts/official_sctype_cluster_baseline.R `
      --adata $Adata `
      --cluster-key louvain `
      --label-key cell_type `
      --ontology-key cell_ontology_id `
      --tissue PBMC `
      --sctype-tissue $ScTypeTissue `
      --output $scTypeRawOutput
    if ($LASTEXITCODE -ne 0) { throw "official scType baseline failed" }
    python -m deepseekcell_ft.cli map-prediction-ontology `
      --predictions $scTypeRawOutput `
      --marker-db $markerDb `
      --output $scTypeOutput
    if ($LASTEXITCODE -ne 0) { throw "map-prediction-ontology failed for scType output" }
    $predictions += "scType=$scTypeOutput"
  }

  if (-not $SkipSingleR) {
    & Rscript scripts/singler_cluster_baseline.R `
      --adata $Adata `
      --cluster-key louvain `
      --label-key cell_type `
      --ontology-key cell_ontology_id `
      --tissue PBMC `
      --reference $SingleRReference `
      --output $singleROutput
    if ($LASTEXITCODE -ne 0) { throw "SingleR baseline failed" }
    $predictions += "SingleR=$singleROutput"
  }

  if ($RunPrompt) {
    $model = if ($PromptModel) { $PromptModel } else { $BaseModel }
    python -m deepseekcell_ft.cli benchmark-prompt `
      --base-model $model `
      --input $instructions `
      --output $promptOutput
    if ($LASTEXITCODE -ne 0) { throw "benchmark-prompt failed" }
    python -m deepseekcell_ft.cli map-prediction-ontology `
      --predictions $promptOutput `
      --marker-db $markerDb `
      --output $promptMappedOutput
    if ($LASTEXITCODE -ne 0) { throw "map-prediction-ontology failed for prompt output" }
    $predictions += "Prompt-only=$promptMappedOutput"
  }

  $tableArgs = @(
    "--output-markdown", "outputs/$Tag.comparison.md",
    "--output-csv", "outputs/$Tag.comparison.csv",
    "--output-json", "outputs/$Tag.comparison.json"
  )
  foreach ($prediction in $predictions) {
    $tableArgs += @("--prediction", $prediction)
  }
  python scripts/write_prediction_metrics_table.py @tableArgs
  if ($LASTEXITCODE -ne 0) { throw "write_prediction_metrics_table.py failed" }
}
finally {
  Pop-Location
}
