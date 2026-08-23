@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Snap Memory Rescue needs Python 3.10 or newer.
  echo Download it from https://www.python.org/downloads/windows/
  echo Make sure "Add Python to PATH" is selected during installation.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the private Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :failed
)

echo Installing Snap Memory Rescue and its private tools...
".venv\Scripts\python.exe" -m pip install -e . --quiet
if errorlevel 1 goto :failed

".venv\Scripts\python.exe" -m app.launcher
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Setup did not finish. Copy the error above when asking for help.
pause
exit /b 1
