; Inno Setup script for the Printer Supply Monitor.
;
; Build (from the tools\printer-monitor folder, after PyInstaller has produced
; dist\PrinterMonitor\):
;
;     iscc installer\PrinterMonitor.iss
;
; Produces installer\Output\PrinterMonitor-Setup.exe -- one file you can hand
; to someone with "double-click this, press Install".

#define AppName        "Printer Supply Monitor"
#define AppVersion     "1.1.0"
#define AppPublisher   "Fenix 5ive"
#define AppExeName     "PrinterMonitor.exe"
#define CliExeName     "printer-monitor.exe"
#define AppId          "{{9C2F7E31-5B4D-4A86-97C3-1D6E0B84A2F5}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\Printer Supply Monitor
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; The one screen worth keeping: it says what the program does before it runs.
InfoBeforeFile=before-install.txt
OutputDir=Output
OutputBaseFilename=PrinterMonitor-Setup
SetupIconFile=..\build\printermonitor.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Writing to Program Files needs administrator rights. Nothing the program
; does at run time does -- settings and history live in the user's own folder.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0
; Warns "close it first" rather than replacing files under a running copy.
AppMutex=PrinterSupplyMonitorRunningMutex
; Broadcast the environment change for the "add to PATH" task, so a newly
; opened terminal sees it without waiting for a reboot.
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put a shortcut on the Desktop"; \
    GroupDescription: "Shortcuts:"
; Ticked by default: a supply monitor that only runs when somebody remembers
; to open it is not doing its job.
Name: "startup"; \
    Description: "Start monitoring when Windows starts (minimised)"; \
    GroupDescription: "Monitoring:"
; Off by default -- handy for Task Scheduler and terminal use, but changing
; PATH is not something to do to somebody without asking.
Name: "addtopath"; \
    Description: "Add printer-monitor to the command line (PATH)"; \
    GroupDescription: "Monitoring:"; Flags: unchecked

[Files]
; The whole PyInstaller folder: two programs sharing one copy of Python.
Source: "..\dist\PrinterMonitor\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt"; \
    Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon
; {autostartup}, not {userstartup}: this installer elevates, so the per-user
; folder would be the administrator's, and on a PC where the everyday account
; is not an admin the shortcut would sit somewhere that never runs. In admin
; mode {autostartup} is the all-users Startup folder, which is what a shop PC
; wants anyway. Minimised, so logging in does not mean a window in your face.
Name: "{autostartup}\{#AppName}";     Filename: "{app}\{#AppExeName}"; \
    Parameters: "gui --minimized"; Tasks: startup

[Registry]
; The machine-wide PATH lives under Session Manager, not HKLM\Environment --
; writing to the latter looks like it worked and changes nothing.
Root: HKLM; \
    Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
; Ticked by default, so finishing the installer drops them straight into the
; program rather than leaving them to go looking for it.
Filename: "{app}\{#AppExeName}"; \
    Description: "Start {#AppName} now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller unpacks nothing here, but a crash can leave a log behind.
Type: filesandordirs; Name: "{app}\logs"

[Code]
{ True when the folder is not already on PATH -- appending it twice on an
  upgrade would grow the variable every time. }
function NeedsAddPath(Param: string): Boolean;
var
  OrigPath: string;
begin
  { Reads the same key the [Registry] entry writes. Checking a different one
    would append the folder again on every upgrade until PATH burst. }
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;
