# Build the Windows installer (Inno Setup) from the one-dir host build.
#
#   powershell -ExecutionPolicy Bypass -File dev\build-installer.ps1
#
# Needs Inno Setup 6 (https://jrsoftware.org/isdl.php). Produces
# dist\Poros-Host-Setup-<version>-windows-x64.exe.
#
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

$version = (Select-String -Path (Join-Path $repo 'main.py') -Pattern 'VERSION = "v([\d.]+)"').Matches[0].Groups[1].Value

# The one-dir build the host script leaves in dist\Poros.
$dist = Join-Path $repo 'dist\Poros'
if (-not (Test-Path (Join-Path $dist 'Poros.exe'))) {
    throw "No built host folder in dist\Poros. Run dev\build-host.ps1 first."
}

$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe"
    )) {
        if (Test-Path $candidate) { $iscc = $candidate; break }
    }
}
if (-not $iscc) { throw "Inno Setup not found. Install it from https://jrsoftware.org/isdl.php" }

Write-Host "Building Poros installer $version ..."
Write-Host "  payload: $dist"
Write-Host "  iscc: $iscc"

# The target name comes from the script's own default (windows-x64), so no /D
# define has to be threaded through.
$iss = Join-Path $repo 'installer\poros.iss'
& $iscc "/DAppVersion=$version" "/DDistDir=$dist" $iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

$out = Join-Path $repo "dist\Poros-Host-Setup-$version-windows-x64.exe"
if (-not (Test-Path $out)) { throw "ISCC finished but $out is missing." }

Write-Host ""
Write-Host "Installer built: $out"
Write-Host "Installs per-user (no UAC); Start Menu + optional desktop shortcut, and an optional run-at-login entry."
