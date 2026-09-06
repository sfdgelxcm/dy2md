@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo [ERROR] Project virtual environment not found: .venv
    echo Run setup.bat first.
    pause
    exit /b 1
)

if not exist "%~dp0config.yaml" (
    echo [ERROR] config.yaml not found.
    echo Copy config.example.yaml to config.yaml and edit it first.
    pause
    exit /b 1
)

start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launcher.py"
exit /b 0
