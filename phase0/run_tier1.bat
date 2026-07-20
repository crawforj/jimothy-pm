@echo off
rem Jimothy Phase 0 — runs spike_check.py with whatever Python is available.
rem Order: embeddable python in .\python-embed\, then py launcher, then PATH python.
setlocal
if exist "%~dp0python-embed\python.exe" (
  "%~dp0python-embed\python.exe" "%~dp0spike_check.py"
  goto :done
)
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 "%~dp0spike_check.py"
  goto :done
)
where python >nul 2>&1
if %errorlevel%==0 (
  python "%~dp0spike_check.py"
  goto :done
)
echo No Python found. See README.md: extract the embeddable zip to python-embed\ first.
:done
pause
