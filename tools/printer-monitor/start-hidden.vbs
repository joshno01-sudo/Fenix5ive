' Start the Printer Supply Monitor with no console window.
'
' Put a shortcut to this file in the Startup folder so monitoring begins when
' the shop PC is switched on:
'   press Win+R, type  shell:startup  , press Enter, and drop the shortcut in.

Dim shell, fso, here, exe
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = here

' pythonw.exe runs without a console window.
exe = "pythonw.exe"
If Not fso.FileExists(exe) Then exe = "pythonw"

' 0 = hidden window, False = don't wait for it to finish.
shell.Run """" & exe & """ -m printer_monitor", 0, False
