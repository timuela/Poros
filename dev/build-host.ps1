# Build the Windows host, in both shapes:
#
#   dist\Poros\                                       one-dir, the installer payload
#   dist\Poros-Host-Portable-<v>-<target>.exe         single-file portable
#
# The one-dir build runs straight from disk. The single-file exe unpacks the
# same payload into %TEMP% on every launch, so it starts slower - that is the
# price of being one file.
#
#   powershell -ExecutionPolicy Bypass -File dev\build-host.ps1
#
param(
    [string]$Target = 'windows-x64'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

$py = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "No .venv found. Run dev\setup.ps1 first." }

$version = (Select-String -Path (Join-Path $repo 'main.py') -Pattern 'VERSION = "v([\d.]+)"').Matches[0].Groups[1].Value
Write-Host "Building Poros Host $version ..."

Push-Location $repo
try {
    Remove-Item Env:POROS_ONEFILE -ErrorAction SilentlyContinue
    Write-Host "  [1/2] one-dir (installer payload) ..."
    & $py -m PyInstaller --noconfirm --workpath build\onedir --distpath dist main.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller (one-dir) failed with exit code $LASTEXITCODE" }
    if (-not (Test-Path (Join-Path $repo 'dist\Poros\Poros.exe'))) {
        throw "PyInstaller finished but dist\Poros\Poros.exe is missing."
    }

    Write-Host "  [2/2] single-file portable ..."
    # A separate --distpath keeps this run from touching the one-dir output the
    # installer step still needs.
    $env:POROS_ONEFILE = '1'
    & $py -m PyInstaller --noconfirm --workpath build\onefile --distpath dist-portable main.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller (single-file) failed with exit code $LASTEXITCODE" }
    if (-not (Test-Path (Join-Path $repo 'dist-portable\Poros-Portable.exe'))) {
        throw "PyInstaller finished but dist-portable\Poros-Portable.exe is missing."
    }
} finally {
    Remove-Item Env:POROS_ONEFILE -ErrorAction SilentlyContinue
    Pop-Location
}

$portable = Join-Path $repo "dist\Poros-Host-Portable-$version-$Target.exe"
Move-Item (Join-Path $repo 'dist-portable\Poros-Portable.exe') $portable -Force
Remove-Item (Join-Path $repo 'dist-portable') -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Host folder:  $(Join-Path $repo 'dist\Poros')   (single build, starts fastest)"
Write-Host "Portable exe: $portable   (one file, starts slower)"
Write-Host ""
Write-Host "Installer:    run dev\build-installer.ps1"
