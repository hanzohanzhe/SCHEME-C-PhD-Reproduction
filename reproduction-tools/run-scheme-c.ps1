param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("existing_decarb_base", "subsidy_as_usual", "governmental_target", "base", "base_with_cm")]
    [string]$Scenario,
    [int]$StartYear = 2025,
    [int]$EndYear = 2025,
    [string]$RunId = "",
    [switch]$NoGenerationTrace,
    [switch]$SkipIntegrityCheck
)

$ErrorActionPreference = "Stop"
if ($EndYear -lt $StartYear) { throw "EndYear must not be earlier than StartYear" }
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$modelDir = Join-Path $repoRoot "work\model"
$storageDir = Join-Path $repoRoot "work\storage_expansion_corrected_caps"
$entryPoint = Join-Path $modelDir "run_investment_analysis_case3_decarbonization_breakdown_cm.py"

if (-not (Test-Path -LiteralPath $python)) { throw "Run create-environment.ps1 first" }
if (-not (Test-Path -LiteralPath $entryPoint)) { throw "Run prepare-data.ps1 first" }
if (-not (Test-Path -LiteralPath "F:\newfinalweather\average_annual_wind_profile.nc")) {
    throw "The historical F:\newfinalweather path is not ready. Run mount-weather-drive.ps1."
}
if (-not $SkipIntegrityCheck) {
    & $python (Join-Path $PSScriptRoot "verify_repository.py")
    if ($LASTEXITCODE -ne 0) { throw "Repository integrity check failed" }
}

$settings = switch ($Scenario) {
    "existing_decarb_base" { @{ RUN_SUITE=""; SCENARIO_V2="1"; DECARB_V2_SCENARIO="existing_decarb_base"; DECARB_SCENARIO="existing_decarb_base_2025_2035"; OUTPUT_SUFFIX="case3_v2_existing_decarb_base" } }
    "subsidy_as_usual" { @{ RUN_SUITE=""; SCENARIO_V2="1"; DECARB_V2_SCENARIO="subsidy_as_usual"; DECARB_SCENARIO="subsidy_as_usual_2025_2035"; OUTPUT_SUFFIX="case3_v2_subsidy_as_usual" } }
    "governmental_target" { @{ RUN_SUITE=""; SCENARIO_V2="1"; DECARB_V2_SCENARIO="governmental_target"; DECARB_SCENARIO="governmental_target_2025_2035"; OUTPUT_SUFFIX="case3_v2_governmental_target" } }
    "base" { @{ RUN_SUITE="basic"; SCENARIO_V2="0"; DECARB_V2_SCENARIO=""; DECARB_SCENARIO="future_base_2025_2035"; OUTPUT_SUFFIX="future_base_2025_2035" } }
    "base_with_cm" { @{ RUN_SUITE="with_cm"; SCENARIO_V2="0"; DECARB_V2_SCENARIO=""; DECARB_SCENARIO="future_base_with_cm_2025_2035"; OUTPUT_SUFFIX="archive_with_cm" } }
}

if (-not $RunId) {
    $RunId = "scheme-c-$Scenario-$StartYear-$EndYear-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}
$outputDir = Join-Path $repoRoot ("outputs\" + $RunId)
if (Test-Path -LiteralPath $outputDir) { throw "Output directory already exists: $outputDir" }
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

$environment = [ordered]@{
    PYTHONHASHSEED = "0"
    START_YEAR = [string]$StartYear
    END_YEAR = [string]$EndYear
    OUTPUT_DIR = $outputDir
    ENABLE_CHECKPOINT = "1"
    PLANNING_USE_MEDIAN = "1"
    PIPELINE_DEFER_SPREAD_YEARS = "3"
    CAPITAL_COST_PROFILE = "arup_medium"
    PHYSICAL_PERIOD_HOURS = "0.5"
    FAST_ANALYSIS_OUTPUT = "1"
    TRACE_FORMAT = "sqlite"
    SAVE_GENERATION_TRACE = $(if ($NoGenerationTrace) { "0" } else { "1" })
    SAVE_MARKET_TRACE = "0"
    MARKET_TRACE_RUN_ID = $RunId
    MARKET_TRACE_BASE_DIR = (Join-Path $repoRoot "outputs")
    PYTHONIOENCODING = "utf-8"
    PYTHONUNBUFFERED = "1"
    VALIDATION_MODE = "0"
    VALIDATION_DISABLE_EXTERNAL_PROJECTS = "0"
    VALIDATION_HISTORICAL_DECARB = "0"
    VALIDATION_INITIAL_CAPACITY_YEAR = ""
    VALIDATION_REPD_FILE = ""
    REPD_ZOMBIE_STATUS_STALE_YEAR = "2015"
    REPD_ZOMBIE_SNAPSHOT_YEAR = [string]$StartYear
    APPLY_REPD_INITIAL_SNAPSHOT = "1"
    REPD_INCLUDE_UNCERTAIN_PROJECTS = "1"
    REPD_UNCERTAIN_AS_MODEL_DECISION = "0"
    STORAGE_EXPANSION_CAP_FRACTION = "0.20"
    STORAGE_EXPANSION_MODULE_DIR = $storageDir
    STORAGE_CAP_CREDIT_MODE = "scheme_c"
    STORAGE_CAP_METHOD = "scheme_c_sim_trace"
    STORAGE_VIRTUAL_POOL_ENERGY_MWH = "1000000000"
    STORAGE_VIRTUAL_POOL_POWER_MW = "1000000000"
    MODEL_SUCCESS_MODE = "expected"
    RUN_SUITE = $settings.RUN_SUITE
    SCENARIO_V2 = $settings.SCENARIO_V2
    DECARB_V2_SCENARIO = $settings.DECARB_V2_SCENARIO
    DECARB_SCENARIO = $settings.DECARB_SCENARIO
    OUTPUT_SUFFIX = $settings.OUTPUT_SUFFIX
}

$headRef = Join-Path $repoRoot ".git\refs\heads\main"
$sourceCommit = if (Test-Path -LiteralPath $headRef) {
    (Get-Content -LiteralPath $headRef -Raw).Trim()
} else {
    "uncommitted"
}
$declaration = [ordered]@{
    schema_version = "scheme-c.pre-run-declaration/v1"
    run_id = $RunId
    declared_at = (Get-Date).ToString("o")
    git_commit = $sourceCommit
    release_tag = "scheme-c-1000twh-2026-07-18_19"
    benchmark_asset_sha256 = "0bc3a78d535fbb6198ee16d708343e6d70a01de76fa2e5459ffb27cebd2cb672"
    scenario = $Scenario
    start_year = $StartYear
    end_year = $EndYear
    periods_per_full_year = 17520
    generation_trace = (-not $NoGenerationTrace)
    environment = $environment
}
$declaration | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outputDir "pre-run-declaration.json") -Encoding UTF8

$previous = @{}
foreach ($item in $environment.GetEnumerator()) {
    $previous[$item.Key] = [Environment]::GetEnvironmentVariable($item.Key, "Process")
    [Environment]::SetEnvironmentVariable($item.Key, [string]$item.Value, "Process")
}

$logPath = Join-Path $outputDir "console.log"
$exitCode = 1
try {
    Push-Location $modelDir
    & $python -B -u $entryPoint 2>&1 | Tee-Object -FilePath $logPath
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
    foreach ($key in $environment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previous[$key], "Process")
    }
}

$result = [ordered]@{
    schema_version = "scheme-c.run-result/v1"
    run_id = $RunId
    finished_at = (Get-Date).ToString("o")
    return_code = $exitCode
    output_dir = $outputDir
    console_log = $logPath
}
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputDir "run-result.json") -Encoding UTF8
if ($exitCode -ne 0) { throw "Scheme C exited with return code $exitCode. See $logPath" }
Write-Host "Scheme C run completed: $outputDir"
