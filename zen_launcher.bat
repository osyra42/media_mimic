@echo off
title Media Mimic

REM Change to the directory where the batch file is located
cd /d "%~dp0"

REM Activate the virtual environment
call venv\Scripts\activate

REM Run the Python script using a relative path
python main.py

REM Deactivate the virtual environment
call venv\Scripts\deactivate

REM Pause to keep the window open
pause