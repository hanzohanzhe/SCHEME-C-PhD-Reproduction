param(
    [int]$StartYear = 2025,
    [int]$EndYear = 2034,
    [string]$BatchId = ""
)

$ErrorActionPreference = "Stop"
if (-not $BatchId) { $BatchId = "scheme-c-thesis-$(Get-Date -Format 'yyyyMMdd-HHmmss')" }
$runner = Join-Path $PSScriptRoot "run-scheme-c.ps1"
$scenarios = @("existing_decarb_base", "subsidy_as_usual", "governmental_target", "base", "base_with_cm")

foreach ($scenario in $scenarios) {
    Write-Host "Starting $scenario ($StartYear-$EndYear)"
    & $runner -Scenario $scenario -StartYear $StartYear -EndYear $EndYear -RunId "$BatchId-$scenario"
    if ($LASTEXITCODE -ne 0) { throw "Benchmark stopped after $scenario" }
}

Write-Host "All five Scheme C thesis scenarios completed under outputs/$BatchId-*"
