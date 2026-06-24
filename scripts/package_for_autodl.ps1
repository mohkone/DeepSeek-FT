param(
  [string]$OutputPath = "dist/deepseek-ft-autodl.zip",
  [switch]$IncludeOutputs
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputFullPath = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
  [System.IO.Path]::GetFullPath($OutputPath)
}
else {
  [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $OutputPath))
}
$DistDir = [System.IO.Path]::GetFullPath((Split-Path -Parent $OutputFullPath))
$StagingRoot = [System.IO.Path]::GetFullPath((Join-Path $DistDir ".autodl_package_staging"))

if (-not $StagingRoot.StartsWith($DistDir, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to use staging path outside dist directory: $StagingRoot"
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

if (Test-Path $StagingRoot) {
  Remove-Item -LiteralPath $StagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StagingRoot | Out-Null

$items = @(
  "configs",
  "data",
  "docs",
  "manuscript",
  "scripts",
  "src",
  "tests",
  ".gitignore",
  "pyproject.toml",
  "README.md"
)

if ($IncludeOutputs) {
  $items += "outputs"
}

foreach ($item in $items) {
  $source = Join-Path $ProjectRoot $item
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination $StagingRoot -Recurse -Force
  }
}

$cacheDirectoryNames = @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
Get-ChildItem -LiteralPath $StagingRoot -Recurse -Force -Directory |
  Where-Object { $cacheDirectoryNames -contains $_.Name -or $_.Name.EndsWith(".egg-info") } |
  Sort-Object FullName -Descending |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

if (-not $IncludeOutputs) {
  $generatedDataPaths = @(
    "data/matrix",
    "data/pbmc3k_processed.h5ad"
  )
  foreach ($relativePath in $generatedDataPaths) {
    $generatedPath = Join-Path $StagingRoot $relativePath
    if (Test-Path $generatedPath) {
      Remove-Item -LiteralPath $generatedPath -Recurse -Force
    }
  }
}

if (Test-Path $OutputFullPath) {
  Remove-Item -LiteralPath $OutputFullPath -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = [System.IO.Compression.ZipFile]::Open($OutputFullPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
  Get-ChildItem -LiteralPath $StagingRoot -Recurse -Force -File | ForEach-Object {
    $relativePath = $_.FullName.Substring($StagingRoot.Length).TrimStart("\", "/")
    $entryName = $relativePath -replace "\\", "/"
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
      $zip,
      $_.FullName,
      $entryName,
      [System.IO.Compression.CompressionLevel]::Optimal
    ) | Out-Null
  }
}
finally {
  $zip.Dispose()
}

$entries = [System.IO.Compression.ZipFile]::OpenRead($OutputFullPath)
try {
  $entryNames = @($entries.Entries | ForEach-Object { $_.FullName })
  $requiredEntries = @(
    "pyproject.toml",
    "README.md",
    "scripts/run_lora_training.sh",
    "scripts/run_prompt_baselines_autodl.sh",
    "src/deepseekcell_ft/cli.py",
    "tests/test_annotation.py"
  )
  foreach ($requiredEntry in $requiredEntries) {
    if ($entryNames -notcontains $requiredEntry) {
      throw "Packaged zip is missing required entry: $requiredEntry"
    }
  }
  if ($entryNames | Where-Object { $_ -match "\\" }) {
    throw "Packaged zip contains Windows backslashes. Refusing to emit an AutoDL zip."
  }
}
finally {
  $entries.Dispose()
}

Remove-Item -LiteralPath $StagingRoot -Recurse -Force

$summary = [ordered]@{
  output = $OutputFullPath
  include_outputs = [bool]$IncludeOutputs
  next_step = "Upload this zip to AutoDL and extract it in /root/autodl-tmp/DeepSeek-FT"
}
$summary | ConvertTo-Json
