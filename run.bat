@echo off
setlocal
title HIT401 Group 34 - NT Groundwater & Climate Explorer

echo =====================================================================
echo  HIT401 Group 34 Capstone Project
echo  Interactive Groundwater ^& Climate Explorer for the Northern Territory
echo =====================================================================
echo.

cd /d "%~dp0"

:: 1. Check Python installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in your system PATH.
    echo Please install Python 3.11+ from https://www.python.org/
    echo.
    pause
    exit /b 1
)

:: 2. Check virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment (.venv) not found. Creating it now...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo [INFO] Installing required dependencies from webapp/requirements.txt...
    pip install -r webapp/requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

:: 3. Check if cache exists
if not exist "webapp\cache\bores.parquet" (
    echo [INFO] Data cache not found. Building cache now (takes ~10-15 seconds)...
    python webapp/build_cache.py
)

:: 4. Launch browser and server
echo.
echo [INFO] Starting web application server...
echo [INFO] Opening http://127.0.0.1:8000 in your browser...
start http://127.0.0.1:8000

python webapp/server.py

pause
