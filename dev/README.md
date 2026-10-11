# Local development

Build and test both halves of Poros on this machine, without waiting for CI.
Nothing here touches your system installs or needs admin rights.

## One-time setup

```powershell
powershell -ExecutionPolicy Bypass -File dev\setup.ps1
```

It downloads two things into `D:\dev\poros-tools` (override with the
`POROS_TOOLS` environment variable):

| What | Why |
|------|-----|
| Temurin **JDK 17** | AGP 8.7 needs JDK 17-21. Your system JDK is 25, which Gradle rejects. |
| **Android SDK** + platform 35, build-tools 35, platform-tools | To compile the APK. |

It also creates `.venv` in the repo (Python + PySide6, aiortc, sounddevice,
PyInstaller, ...) and writes `android/local.properties` so Gradle and Android
Studio find our SDK copy.

Roughly 700 MB of downloads, one time.

## Everyday use

```powershell
dev\run-host.ps1      # run the host from source - use this while fixing things
dev\build-host.ps1    # dist\Poros\ + dist\Poros-Host-Portable-<version>-windows-x64.exe
dev\build-installer.ps1  # dist\Poros-Host-Setup-<version>-windows-x64.exe (needs Inno Setup 6)
dev\build-apk.ps1     # dist\Poros-Client-<version>.apk
```

`run-host.ps1` is the fast loop: it launches `main.py` directly, so a code
change just needs a restart rather than a full PyInstaller build.

`build-host.ps1` and `build-apk.ps1` deliberately match what the release
workflow produces - same spec file, same release build type, same committed
signing key, same version numbers - so an APK you build here installs over a
released one instead of being rejected as a different signer.

Version comes from `VERSION` in `main.py`; bump that and both scripts follow.
The APK `versionCode` is derived the same way locally and in CI
(`0.1.6` -> `106`), so builds from either place order correctly.

## Before you tag a release

```powershell
.venv\Scripts\python.exe desktop\smoke_test.py   # headless UI/N-API check
dev\run-host.ps1                                  # then click around
```

`desktop/smoke_test.py` builds the real window, runs every setter, forces a
repaint and checks the window does not resize itself. It catches missing Qt
APIs (it exists because `QApplication.applicationIcon()` shipped once). Add
`QT_QPA_PLATFORM=offscreen` to run it without a window.

## Notes

- The venv uses your system **Python 3.14**; CI builds with **3.11**. All
  dependencies have wheels for both, but if something behaves differently
  between a local build and a released one, that is the first thing to check.
- The **Linux** host needs `libportaudio2` installed to play audio
  (`sudo apt install libportaudio2`); it is a system library and is not bundled.
- `dist/` and `.venv/` are gitignored, as is `android/local.properties`.

## Troubleshooting

**`Timeout of 120000 reached waiting for exclusive access to file: ...gradle-8.11.1-bin.zip`**

A Gradle process was killed mid-download (Ctrl+C, or closing the terminal) and
left a lock behind. Clear it:

```powershell
Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
  Where-Object { $_.CommandLine -like '*gradle*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Remove-Item "$env:USERPROFILE\.gradle\wrapper\dists\gradle-8.11.1-bin\*\*.lck" -Force
```

**Gradle's first run is very slow**

`services.gradle.org` is much slower than `dl.google.com` on some
connections, and the first build pulls the 137 MB distribution plus the
Android dependencies. It only happens once. To watch progress, check the size
of `%USERPROFILE%\.gradle\wrapper\dists\gradle-8.11.1-bin\*\gradle-8.11.1-bin.zip`.
If it stalls at 0 bytes, the lock above is the usual cause.
