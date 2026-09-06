@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
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

if "%~1"=="" (
    echo Drag a text file or folder onto this batch file.
    echo Or run: run_text_cleaner.bat input.txt
    pause
    exit /b 1
)

"%~dp0.venv\Scripts\python.exe" "%~dp0text_cleaner.py" %*
pause
