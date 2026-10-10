# Build the Android client APK, exactly like the release workflow does:
# same release build type, same committed signing key, same version numbers.
#
#   powershell -ExecutionPolicy Bypass -File dev\build-apk.ps1
#
param(
    [string]$ToolsRoot = $(if ($env:POROS_TOOLS) { $env:POROS_TOOLS } else { 'D:\dev\poros-tools' })
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

$jdk = Join-Path $ToolsRoot 'jdk-17'
$sdk = Join-Path $ToolsRoot 'android-sdk'
if (-not (Test-Path (Join-Path $jdk 'bin\java.exe'))) { throw "No JDK 17 at $jdk. Run dev\setup.ps1 first." }
if (-not (Test-Path $sdk)) { throw "No Android SDK at $sdk. Run dev\setup.ps1 first." }

$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk

# Same scheme as CI so a locally built APK and a released one upgrade cleanly
# over each other: 0.1.6 -> 106.
$version = (Select-String -Path (Join-Path $repo 'main.py') -Pattern 'VERSION = "v([\d.]+)"').Matches[0].Groups[1].Value
$parts = $version.Split('.')
$code = [int]$parts[0] * 10000 + [int]$parts[1] * 100 + [int]$parts[2]

Write-Host "Building Poros Client $version (versionCode $code) ..."

Push-Location (Join-Path $repo 'android')
try {
    & .\gradlew.bat assembleRelease --no-daemon "-PversionName=$version" "-PversionCode=$code"
    if ($LASTEXITCODE -ne 0) { throw "Gradle failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$apk = Join-Path $repo 'android\app\build\outputs\apk\release\app-release.apk'
if (-not (Test-Path $apk)) { throw "Gradle finished but $apk is missing." }

$dist = Join-Path $repo 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$out = Join-Path $dist "Poros-Client-$version.apk"
Copy-Item $apk $out -Force

Write-Host ""
Write-Host "Client built: $out"
Write-Host "Signed with the same key as the release, so it upgrades over the released app."
