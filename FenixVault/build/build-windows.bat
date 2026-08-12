@echo off
REM Build FenixVault.exe on Windows.
REM
REM Needs Python 3.10+ from python.org (tick "Add Python to PATH" when you
REM install it). Everything else is fetched automatically.
REM
REM Double-click this file, or run it from a command prompt. The finished
REM program lands in  dist\FenixVault.exe

setlocal
cd /d "%~dp0\.."

echo.
echo ============================================
echo   Building Fenix Vault for Windows
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on this PC.
    echo Install it free from https://www.python.org/downloads/
    echo Remember to tick "Add Python to PATH" during setup.
    pause
    exit /b 1
)

echo [1/4] Checking Python...
python --version || goto :failed

echo.
echo [2/4] Installing the build tool...
python -m pip install --upgrade --quiet pip pyinstaller || goto :failed

echo.
echo [3/4] Running the tests...
python -m unittest discover -s tests || goto :failed

echo.
echo [4/4] Building the program...
python -m PyInstaller build\FenixVault.spec --noconfirm --clean || goto :failed

echo.
echo ============================================
echo   Done.
echo   Your program is here:
echo     %CD%\dist\FenixVault.exe
echo ============================================
echo.
echo Copy that one file anywhere you like and double-click it.
echo.
pause
exit /b 0

:failed
echo.
echo Build failed - see the messages above.
pause
exit /b 1
