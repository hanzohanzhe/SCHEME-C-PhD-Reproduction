param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $repoRoot ".venv"
$python = Join-Path $venv "Scripts\python.exe"

if ($Recreate -and (Test-Path -LiteralPath $venv)) {
    $resolved = (Resolve-Path -LiteralPath $venv).Path
    if (-not $resolved.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a virtual environment outside the repository: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

if (-not (Test-Path -LiteralPath $python)) {
    & py -3.10 -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw "CPython 3.10 could not create the virtual environment. Install Python 3.10.11 and the Windows py launcher."
    }
}

& $python -m pip install --upgrade "pip==25.1.1"
if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed" }
& $python -m pip install -r (Join-Path $repoRoot "requirements-py310.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }

& $python -c "import sys; assert sys.version_info[:2] == (3, 10), sys.version; print(sys.version)"
if ($LASTEXITCODE -ne 0) { throw "The virtual environment is not Python 3.10" }

Write-Host "Scheme C Python environment is ready: $python"
