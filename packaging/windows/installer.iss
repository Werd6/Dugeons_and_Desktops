; Inno Setup script — builds a per-user Windows installer (no admin / UAC).
; Compile from repo root after PyInstaller:
;   "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" packaging\windows\installer.iss

#define MyAppName "Dungeons and Desktops"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Werd6"
#define MyAppURL "https://github.com/Werd6/Dugeons_and_Desktops"
#define MyAppExeName "Dungeons and Desktops.exe"

[Setup]
; Stable ID so upgrades/uninstall stay consistent across builds.
AppId={{8F3C2A91-6B4E-4D17-9C5A-2E7F0B1D4A68}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\
OutputBaseFilename=Dungeons-and-Desktops-Windows-Setup
SetupIconFile=..\icons\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
InfoBeforeFile=README.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checked

[Files]
; Entire PyInstaller onedir — exe stays next to _internal inside {app}.
Source: "..\..\dist\Dungeons and Desktops\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "Launch {#MyAppName}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\*"
