@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python 3.10 or newer first.
    pause
    exit /b 1
)

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [1/3] Creating the project virtual environment...
    python -m venv "%~dp0.venv"
    if errorlevel 1 goto :failed
) else (
    echo [1/3] Project virtual environment already exists.
)

echo [2/3] Installing project dependencies...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :failed

echo [3/3] Preparing config.yaml...
if not exist "%~dp0config.yaml" copy /Y "%~dp0config.example.yaml" "%~dp0config.yaml" >nul

echo.
echo Setup complete. Edit config.yaml, then run run_gui_pro.bat.
pause
exit /b 0

:failed
echo.
echo [ERROR] Setup failed. Review the error output above.
pause
exit /b 1
