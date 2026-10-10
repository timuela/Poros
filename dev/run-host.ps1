# Run the host straight from source - no packaging, so a change is visible in
# seconds. This is the loop to use while fixing something.
#
#   powershell -ExecutionPolicy Bypass -File dev\run-host.ps1
#
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

$py = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "No .venv found. Run dev\setup.ps1 first." }

Write-Host "Starting Poros Host from source (Ctrl+C to stop) ..."
Push-Location $repo
try {
    & $py main.py
} finally {
    Pop-Location
}
