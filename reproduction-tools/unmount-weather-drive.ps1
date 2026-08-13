$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$weatherRoot = (Join-Path $repoRoot "work\weather-root").TrimEnd('\')
$mappingLine = @(subst | Where-Object { $_ -match '^F:\\:\s*=>\s*' })

if ($mappingLine.Count -eq 0) {
    Write-Host "F: is not a SUBST mapping. Nothing was removed."
    exit 0
}

$current = ($mappingLine[0] -replace '^F:\\:\s*=>\s*', '').TrimEnd('\')
if ($current -ine $weatherRoot) {
    throw "F: belongs to '$current', not this repository. It will not be removed."
}

& subst F: /D
if ($LASTEXITCODE -ne 0) { throw "Could not remove the Scheme C F: mapping" }
Write-Host "Removed the Scheme C F: mapping."
