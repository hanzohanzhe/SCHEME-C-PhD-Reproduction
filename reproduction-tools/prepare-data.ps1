param(
    [string]$ArchivePath = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$assetName = "force-uk-benchmark-2025-v1.zip"
$assetSha256 = "0bc3a78d535fbb6198ee16d708343e6d70a01de76fa2e5459ffb27cebd2cb672"
$downloadDir = Join-Path $repoRoot "downloads"
$workRoot = Join-Path $repoRoot "work"

if (-not $ArchivePath) {
    New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
    $ArchivePath = Join-Path $downloadDir $assetName
    if (-not (Test-Path -LiteralPath $ArchivePath)) {
        if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
            throw "GitHub CLI is required to download the private benchmark. Install gh or pass -ArchivePath."
        }
        & gh auth status | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated" }
        & gh release download "force-uk-benchmark-2025-v1" `
            --repo "hanzohanzhe/FORCE-UK-Benchmark-Data" `
            --pattern $assetName `
            --dir $downloadDir
        if ($LASTEXITCODE -ne 0) { throw "Private benchmark download failed" }
    }
}

$ArchivePath = (Resolve-Path -LiteralPath $ArchivePath).Path
$actualHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $assetSha256) {
    throw "Benchmark SHA-256 mismatch. Expected $assetSha256, received $actualHash"
}

if (Test-Path -LiteralPath $workRoot) {
    if (-not $Force) {
        throw "The work directory already exists. Review it, then rerun with -Force to replace only this repository's disposable work directory."
    }
    $resolvedWork = (Resolve-Path -LiteralPath $workRoot).Path
    if (-not $resolvedWork.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a work directory outside the repository: $resolvedWork"
    }
    Remove-Item -LiteralPath $resolvedWork -Recurse -Force
}

$unpackRoot = Join-Path $workRoot "unpacked"
$modelWork = Join-Path $workRoot "model"
$storageWork = Join-Path $workRoot "storage_expansion_corrected_caps"
$weatherDir = Join-Path $workRoot "weather-root\newfinalweather"
New-Item -ItemType Directory -Path $unpackRoot,$modelWork,$storageWork,$weatherDir -Force | Out-Null

Expand-Archive -LiteralPath $ArchivePath -DestinationPath $unpackRoot
$packRoot = Join-Path $unpackRoot "force-uk-benchmark-2025-v1"
if (-not (Test-Path -LiteralPath (Join-Path $packRoot "manifest.json"))) {
    throw "The benchmark archive does not contain the expected release root"
}

Copy-Item -Path (Join-Path $repoRoot "original-model\*") -Destination $modelWork -Recurse -Force
Copy-Item -Path (Join-Path $repoRoot "external-storage\*") -Destination $storageWork -Recurse -Force

$relativeInputs = @(
    "files\demand__forecast\2022fd.csv",
    "files\demand__real\2022reald.csv",
    "files\market__belgium__price\Belgium_price.csv",
    "files\market__belgium__profile\belgium_profile.csv",
    "files\market__france__price\France.csv",
    "files\market__france__profile\France_profile.csv",
    "files\market__ireland__price\Ireland.csv",
    "files\market__ireland__profile\Ireland_profile.csv",
    "files\market__netherlands__price\Netherlands.csv",
    "files\market__netherlands__profile\nehtheralnd_profile.csv",
    "files\market__norway__price\Norway.csv",
    "files\market__norway__profile\Norway_profile.csv",
    "files\planning__success_rates\regional_technology_success_rates.csv",
    "files\policy__support\mechansim cost.xlsx",
    "files\profiles__vre_offshore\we.csv",
    "files\profiles__vre_onshore\wa.csv",
    "files\profiles__vre_solar\sa.csv",
    "files\source__repd_raw\repd-q2-jul-2025.csv"
)

foreach ($relative in $relativeInputs) {
    $source = Join-Path $packRoot $relative
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing benchmark input: $relative" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $modelWork (Split-Path $relative -Leaf))
}

Copy-Item -LiteralPath (Join-Path $packRoot "files\weather__wind\average_annual_wind_profile.nc") -Destination $weatherDir
Copy-Item -LiteralPath (Join-Path $packRoot "files\weather__solar\average_annual_solar_profile.nc") -Destination $weatherDir

$sourceCommit = (& git -C $repoRoot rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $sourceCommit) {
    $sourceCommit = "uncommitted"
} else {
    $sourceCommit = ([string]$sourceCommit).Trim()
}
$prepared = [ordered]@{
    schema_version = "scheme-c.reproduction-prepared/v1"
    prepared_at = (Get-Date).ToString("o")
    source_commit = $sourceCommit
    benchmark_asset = $assetName
    benchmark_sha256 = $actualHash
    model_work_dir = $modelWork
    storage_work_dir = $storageWork
    weather_root = (Split-Path $weatherDir -Parent)
}
$prepared | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $workRoot "prepared.json") -Encoding UTF8

Write-Host "Prepared a disposable reproduction tree under $workRoot"
Write-Host "Next: powershell -ExecutionPolicy Bypass -File reproduction-tools/mount-weather-drive.ps1"
