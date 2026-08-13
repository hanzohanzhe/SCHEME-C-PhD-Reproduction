param(
    [string]$ArchivePath = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$py = (Get-Command py.exe -ErrorAction Stop).Source

& $py -3.10 -c "import sys; assert sys.version_info[:2] == (3, 10), sys.version"
if ($LASTEXITCODE -ne 0) {
    throw "Install 64-bit CPython 3.10.11 with the Windows py launcher, then run this installer again."
}

Write-Host "1/4 Verifying the frozen Scheme C archive..."
& $py -3.10 (Join-Path $PSScriptRoot "verify_repository.py")
if ($LASTEXITCODE -ne 0) { throw "The frozen Scheme C archive failed integrity verification." }

Write-Host "2/4 Creating the locked Python 3.10 environment..."
& (Join-Path $PSScriptRoot "create-environment.ps1")

Write-Host "3/4 Preparing the separately governed UK benchmark data..."
$prepare = Join-Path $PSScriptRoot "prepare-data.ps1"
if ($ArchivePath) {
    & $prepare -ArchivePath $ArchivePath -Force:$Force
} else {
    & $prepare -Force:$Force
}

Write-Host "4/4 Mounting the retained F: weather path..."
& (Join-Path $PSScriptRoot "mount-weather-drive.ps1")

Write-Host "Scheme C reproduction environment is ready."
Write-Host "Recommended first run:"
Write-Host 'powershell -ExecutionPolicy Bypass -File reproduction-tools/run-scheme-c.ps1 -Scenario existing_decarb_base -StartYear 2025 -EndYear 2025'
