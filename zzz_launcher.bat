@echo off
setlocal
REM === Variables ===
set "TITLE=Media Mimic"
set "ENTRY=main.py"
set "ARGS="
set "PYW=venv\Scripts\pythonw.exe"
set "PY=venv\Scripts\python.exe"

cd /d "%~dp0"

REM === Step 1: virtual environment exists ===
if not exist "%PY%" (
    echo The Python virtual environment is missing.
    echo Create it with: python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
    pause & exit /b 1
)

REM === Step 2: runtime new enough (3.10+) ===
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if %ERRORLEVEL% NEQ 0 (
    echo Python 3.10+ is required. Rebuild the venv with a newer Python.
    pause & exit /b 1
)

REM === Step 3: dependencies present ===
"%PY%" -m pip check >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Missing dependencies. Run: venv\Scripts\pip install -r requirements.txt
    pause & exit /b 1
)

REM === Step 4: entry file present ===
if not exist "%ENTRY%" (
    echo Cannot find %ENTRY% next to the launcher.
    pause & exit /b 1
)

REM === Step 5: launch windowless and detached, then close this window ===
title %TITLE%
start "" "%PYW%" "%ENTRY%" %ARGS%
exit
