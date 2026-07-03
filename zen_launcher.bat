@echo off
REM === Variables ===
set "TITLE=Media Mimic"
set "ENTRY=main.py"
set "ARGS="
set "PYEXE=venv\Scripts\pythonw.exe"
set "PYCHECK=venv\Scripts\python.exe"

title %TITLE%
cd /d "%~dp0"

REM === Requirements ===
REM Runtime check: the project venv must exist.
if not exist "%PYCHECK%" (
    echo The Python virtual environment is missing.
    echo Create it with: python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM Dependency check: all requirements must be installed and consistent.
"%PYCHECK%" -m pip check >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Missing Python dependencies. Run: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM === Script ===
REM Launch windowless and detached so no console lingers behind the app.
start "" "%PYEXE%" "%ENTRY%" %ARGS%

REM === Execution ===
REM Checks passed and the app is launched - close the launcher immediately.
exit
