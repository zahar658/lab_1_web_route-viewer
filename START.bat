@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 start.py
) else (
  python start.py
)
if errorlevel 1 (
  echo Install Python 3 from https://www.python.org/downloads/windows/
  echo Enable Add python.exe to PATH, then run START.bat again.
)
pause
