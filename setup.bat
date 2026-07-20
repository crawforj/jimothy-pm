@echo off
REM Double-click this file to set up and start Jimothy on Windows.
REM All the real logic lives in setup.ps1 -- this just runs it with
REM -ExecutionPolicy Bypass so it works even if your system's default
REM PowerShell script policy would otherwise block it (a common first-run
REM blocker that has nothing to do with this project specifically).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
echo.
pause
