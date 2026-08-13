$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$weatherRoot = Join-Path $repoRoot "work\weather-root"
$wind = Join-Path $weatherRoot "newfinalweather\average_annual_wind_profile.nc"
$solar = Join-Path $weatherRoot "newfinalweather\average_annual_solar_profile.nc"

if (-not (Test-Path -LiteralPath $wind) -or -not (Test-Path -LiteralPath $solar)) {
    throw "Prepared weather files are missing. Run prepare-data.ps1 first."
}

$mappingLine = @(subst | Where-Object { $_ -match '^F:\\:\s*=>\s*' })
if ($mappingLine.Count -gt 0) {
    $current = ($mappingLine[0] -replace '^F:\\:\s*=>\s*', '').TrimEnd('\')
    if ($current -ieq $weatherRoot.TrimEnd('\')) {
        Write-Host "F: is already mapped to the Scheme C weather root."
        exit 0
    }
    throw "F: is already assigned to '$current'. It will not be replaced."
}

if (Test-Path -LiteralPath "F:\") {
    $existingWind = "F:\newfinalweather\average_annual_wind_profile.nc"
    $existingSolar = "F:\newfinalweather\average_annual_solar_profile.nc"
    $expectedWind = "56ba374ddb9c2142ba5090f4e812e0d05ea6d27f588275ce1e04cbc7b0f5bfee"
    $expectedSolar = "634e22afa820b3e972fc8648e7e7d5ce6b9dd1caf025ac71ef30afe7950ec977"
    if ((Test-Path -LiteralPath $existingWind) -and (Test-Path -LiteralPath $existingSolar)) {
        $windHash = (Get-FileHash -LiteralPath $existingWind -Algorithm SHA256).Hash.ToLowerInvariant()
        $solarHash = (Get-FileHash -LiteralPath $existingSolar -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($windHash -eq $expectedWind -and $solarHash -eq $expectedSolar) {
            Write-Host "F: already contains the exact retained Scheme C weather files; reusing it without modification."
            exit 0
        }
    }
    throw "F: already exists and does not contain the exact retained weather pair. It will not be replaced."
}

& subst F: $weatherRoot
if ($LASTEXITCODE -ne 0) { throw "Could not map F: to $weatherRoot" }
Write-Host "Mapped F: to $weatherRoot for the historical weather paths."
