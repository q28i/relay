; =====================================================================
; Relay - Modern WhatsApp Bulk Automation Desktop Product
; Inno Setup 6 Packaging Script
; Non-admin (%LOCALAPPDATA%\Programs\Relay) per-user installation
; Preserves all persistent user data in %LOCALAPPDATA%\Relay
; =====================================================================

#define MyAppName        "Relay"
#define MyAppVersion     "2.0.0"
#define MyAppPublisher   "Relay Automation Team"
#define MyAppURL         "https://github.com/q28i/relay"
#define MyAppExeName     "Relay.exe"

[Setup]
; --- Identity ---
AppId={{C6D273A8-1E74-453D-9477-E0A9D2423F7E}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; --- Installation Directory & Privileges (Modern Per-User Install) ---
; Non-admin install into %LOCALAPPDATA%\Programs\Relay (like VS Code, Chrome, Slack)
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest

; --- Output Configuration ---
OutputDir=dist
OutputBaseFilename=Relay-Setup-v{#MyAppVersion}-Windows-x64

; --- Visual Styling & Icons ---
WizardStyle=modern
SetupIconFile=assets\relay.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; --- High Compression (LZMA2 Ultra) ---
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; --- 64-bit Architecture Mode ---
ArchitecturesInstallIn64BitMode=x64compatible

; --- Process Management (Clean Update & Restart Handover) ---
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Relay\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
