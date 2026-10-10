# One-time local toolchain setup for building both halves of Poros.
#
# Everything lands under $ToolsRoot (default D:\dev\poros-tools) so nothing
# touches your system installs and no admin rights are needed. The Python
# virtualenv is created inside the repo at .venv (gitignored).
#
#   powershell -ExecutionPolicy Bypass -File dev\setup.ps1
#
param(
    [string]$ToolsRoot = $(if ($env:POROS_TOOLS) { $env:POROS_TOOLS } else { 'D:\dev\poros-tools' })
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = Split-Path -Parent $PSScriptRoot

New-Item -ItemType Directory -Force -Path $ToolsRoot | Out-Null
Write-Host "Tools root: $ToolsRoot"

# --- JDK 17 -------------------------------------------------------------
# AGP 8.7 needs JDK 17-21. A newer JDK (25 is installed here) will not work,
# so keep our own copy instead of relying on the system one.
$jdk = Join-Path $ToolsRoot 'jdk-17'
if (Test-Path (Join-Path $jdk 'bin\java.exe')) {
    Write-Host "[1/4] JDK 17 already present"
} else {
    Write-Host "[1/4] Downloading Temurin JDK 17 (about 190 MB) ..."
    $zip = Join-Path $ToolsRoot 'jdk17.zip'
    curl.exe -L --retry 3 -o $zip 'https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk'
    if ($LASTEXITCODE -ne 0) { throw "JDK download failed" }
    $tmp = Join-Path $ToolsRoot 'jdk17-extract'
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    Move-Item (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName $jdk
    Remove-Item -Recurse -Force $tmp, $zip
}

# --- Android SDK command line tools -------------------------------------
$sdk = Join-Path $ToolsRoot 'android-sdk'
$sdkmanager = Join-Path $sdk 'cmdline-tools\latest\bin\sdkmanager.bat'
if (Test-Path $sdkmanager) {
    Write-Host "[2/4] Android command line tools already present"
} else {
    Write-Host "[2/4] Downloading Android command line tools (about 150 MB) ..."
    $zip = Join-Path $ToolsRoot 'cmdline-tools.zip'
    curl.exe -L --retry 3 -o $zip 'https://dl.google.com/android/repository/commandlinetools-win-12266719_latest.zip'
    if ($LASTEXITCODE -ne 0) { throw "cmdline-tools download failed" }
    $tmp = Join-Path $ToolsRoot 'cmdline-extract'
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $sdk 'cmdline-tools') | Out-Null
    Move-Item (Join-Path $tmp 'cmdline-tools') (Join-Path $sdk 'cmdline-tools\latest')
    Remove-Item -Recurse -Force $tmp, $zip
}

$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk

Write-Host "[3/4] Accepting licences and installing platform 35 + build-tools (about 300 MB) ..."
('y' + [Environment]::NewLine) * 100 | & $sdkmanager --sdk_root="$sdk" --licenses | Out-Null
& $sdkmanager --sdk_root="$sdk" 'platform-tools' 'platforms;android-35' 'build-tools;35.0.0'
if ($LASTEXITCODE -ne 0) { throw "sdkmanager failed" }

# Point Gradle (and Android Studio) at our SDK copy.
Set-Content -Path (Join-Path $repo 'android\local.properties') -Value "sdk.dir=$($sdk -replace '\\','\\')" -Encoding ascii

# --- Python virtualenv --------------------------------------------------
$py = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host "[4/4] Creating Python virtualenv ..."
    python -m venv (Join-Path $repo '.venv')
}
Write-Host "[4/4] Installing desktop dependencies ..."
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r (Join-Path $repo 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host ""
Write-Host "Ready. Next:"
Write-Host "  dev\run-host.ps1     run the host from source (fastest way to test)"
Write-Host "  dev\build-host.ps1   build dist\Poros-Host-Portable-<version>-windows-x64.exe"
Write-Host "  dev\build-apk.ps1    build dist\Poros-Client-<version>.apk"
