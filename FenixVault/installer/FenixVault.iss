; Inno Setup script for Fenix Vault.
;
; Build (from the FenixVault folder, after PyInstaller has produced
; dist\FenixVault.exe):
;
;     iscc installer\FenixVault.iss
;
; Produces installer\Output\FenixVault-Setup.exe -- a single file you can hand
; to someone with "double-click this, press Install".

#define AppName        "Fenix Vault"
#define AppVersion     "1.2.0"
#define AppPublisher   "Fenix 5ive"
#define AppExeName     "FenixVault.exe"
#define AppId          "{{6E4B1C4E-2C7A-4C4E-9E1B-FE5A17C0FA11}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; The one screen worth keeping: it says what the program does before it runs.
InfoBeforeFile=before-install.txt
OutputDir=Output
OutputBaseFilename=FenixVault-Setup
SetupIconFile=..\build\fenixvault.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Reading every user's folders and the machine-wide parts of the registry needs
; administrator rights, so ask once up front rather than failing halfway
; through somebody's backup.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Windows 10 and 11 only: the snapshot leans on PowerShell cmdlets and DPI
; calls that older versions do not have.
MinVersion=10.0
AppMutex=FenixVaultRunningMutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put a shortcut on the Desktop"; \
    GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";          DestDir: "{app}"; DestName: "README.txt"; \
    Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}";            Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";      Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon

[Run]
; Ticked by default, so finishing the installer drops them straight into the
; program rather than leaving them to go looking for it.
Filename: "{app}\{#AppExeName}"; \
    Description: "Start {#AppName} now"; \
    Flags: nowait postinstall skipifsilent
