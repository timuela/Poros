; Poros host installer (Inno Setup 6).
;
; Per-user install: no UAC, and the app folder stays writable so the host can
; keep its poros-host.ini next to the exe the way the portable build does.
;
; Build with:  dev\build-installer.ps1
; or directly: ISCC.exe /DAppVersion=0.1.23 /DDistDir=..\dist\Poros poros.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist\Poros"
#endif
#ifndef TargetName
  #define TargetName "windows-x64"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

#define AppName "Poros"
#define AppExeName "Poros.exe"
; Must match the id desktop\app.py sets for installed builds.
#define AppUserModelID "Poros.Desktop.Host"

[Setup]
AppId={{8E4A2F1C-3D5B-4E6A-9C7D-1F2B3A4C5D6E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Poros
AppPublisherURL=https://github.com/timuela/Poros
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Poros-Host-Setup-{#AppVersion}-{#TargetName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
SetupIconFile=..\icon.ico
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Start {#AppName} when Windows starts"; Flags: checkedonce

[Files]
; The one-dir build: the exe plus its _internal payload, installed as a folder.
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; The AppUserModelID is what lets the shell resolve the taskbar identity and
; icon from this shortcut (see desktop\app.py for the matching call).
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; AppUserModelID: "{#AppUserModelID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Registry]
; Read by the app to learn it was installed (so it may set the AppUserModelID).
Root: HKCU; Subkey: "Software\{#AppName}"; ValueType: string; ValueName: "AppUserModelID"; ValueData: "{#AppUserModelID}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
