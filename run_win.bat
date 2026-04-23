@echo off
cd /d "%~dp0"

echo SkyWave - Brain Interface
echo.

:: ── Find Python ───────────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=python
    goto :found_python
)
py --version >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=py
    goto :found_python
)
echo Python 3.10+ is required but was not found.
echo Download it from: https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found_python
for /f "tokens=2" %%v in ('%PYTHON% --version 2^>^&1') do echo Python %%v found.

:: ── Create virtual environment if needed ──────────────────────────────────────
if not exist ".venv\" (
    echo Setting up virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: ── Install / update dependencies ─────────────────────────────────────────────
echo Installing dependencies (first run may take a minute)...
.venv\Scripts\pip install --quiet --upgrade pip
.venv\Scripts\pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency installation failed. Check your internet connection.
    pause
    exit /b 1
)

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo Launching SkyWave...
echo.
.venv\Scripts\python main.py

echo.
pause
