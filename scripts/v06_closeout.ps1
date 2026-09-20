param(
    [Parameter(Mandatory = $true)]
    [string]$SourceBaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$SourceModel,

    [Parameter(Mandatory = $true)]
    [string]$SourceFamily,

    [Parameter(Mandatory = $true)]
    [string]$TargetBaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$TargetModel,

    [Parameter(Mandatory = $true)]
    [string]$TargetFamily,

    [string]$SourceApiKey = "",
    [string]$TargetApiKey = "",
    [int]$Repeats = 3,
    [int]$MaxTokens = 64,
    [double]$Timeout = 120,
    [string]$OutputDir = ".\artifacts\v06-closeout"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$continuity = Join-Path $OutputDir "continuity-v06.json"
$library = Join-Path $OutputDir "library-v06.json"

$continuityArgs = @(
    "--source-base-url", $SourceBaseUrl,
    "--source-model", $SourceModel,
    "--source-family", $SourceFamily,
    "--target-base-url", $TargetBaseUrl,
    "--target-model", $TargetModel,
    "--target-family", $TargetFamily,
    "--repeats", "$Repeats",
    "--max-tokens", "$MaxTokens",
    "--timeout", "$Timeout",
    "--output", $continuity
)

if ($SourceApiKey) {
    $continuityArgs += @("--source-api-key", $SourceApiKey)
}
if ($TargetApiKey) {
    $continuityArgs += @("--target-api-key", $TargetApiKey)
}

Write-Host "[1/4] Running live cross-family continuity + Roland retrieval..."
& yisang-eval-continuity @continuityArgs
if ($LASTEXITCODE -ne 0) {
    throw "v0.6 continuity evaluation failed with exit code $LASTEXITCODE"
}

Write-Host "[2/4] Checking saved v0.6 continuity evidence..."
$continuityCheckArgs = @(
    "--input", $continuity,
    "--min-repeats", "$Repeats",
    "--phase", "v0.6"
)
& yisang-eval-continuity-check @continuityCheckArgs
if ($LASTEXITCODE -ne 0) {
    throw "v0.6 continuity closeout check failed with exit code $LASTEXITCODE"
}

Write-Host "[3/4] Running 10/50/100/500 Book Roland benchmark..."
& yisang-eval-library --output $library
if ($LASTEXITCODE -ne 0) {
    throw "v0.6 Library benchmark failed with exit code $LASTEXITCODE"
}

& yisang-eval-library-check --input $library
if ($LASTEXITCODE -ne 0) {
    throw "v0.6 Library benchmark check failed with exit code $LASTEXITCODE"
}

Write-Host "[4/4] Evaluating composite v0.6 closeout evidence..."
$closeoutArgs = @(
    "--continuity", $continuity,
    "--library", $library,
    "--min-repeats", "$Repeats"
)
& yisang-eval-v06-closeout @closeoutArgs
if ($LASTEXITCODE -ne 0) {
    throw "v0.6 closeout is not ready"
}

Write-Host ""
Write-Host "YiSang v0.6 closeout evidence is READY."
Write-Host "Continuity: $continuity"
Write-Host "Library:    $library"
