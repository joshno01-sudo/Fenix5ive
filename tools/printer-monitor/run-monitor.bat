@echo off
REM Open the Printer Supply Monitor window.
REM Double-click this file, or make a shortcut to it on the desktop.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m printer_monitor
    goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
    python -m printer_monitor
    goto :end
)

echo Python was not found on this computer.
echo Install it from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH" during setup, then run this file again.
pause

:end
if %errorlevel% neq 0 pause
