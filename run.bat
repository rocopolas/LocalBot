@echo off
setlocal enabledelayedexpansion

REM FemtoBot Windows Launcher

REM cd to the directory where this script lives
cd /d "%~dp0"

set "VENV_NAME=venv_bot"
set "PYTHON_CMD="

REM Find Python 3.12 exactly
for %%P in (python3.12 python3 python py) do (
    %%P --version >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=2 delims= " %%V in ('%%P --version 2^>^&1') do (
            for /f "tokens=1,2 delims=." %%A in ("%%V") do (
                if %%A==3 if %%B==12 (
                    set "PYTHON_CMD=%%P"
                    goto :found_python
                )
            )
        )
    )
)

echo [ERROR] Python 3.12 is required but not found.
echo Please install Python 3.12 from https://www.python.org/downloads/release/python-3120/
pause
exit /b 1

:found_python
echo ===================================
echo   FemtoBot - Windows Setup
echo ===================================

for /f "tokens=*" %%V in ('%PYTHON_CMD% --version 2^>^&1') do echo [OK] %%V

REM Check if virtual environment exists
if not exist "%VENV_NAME%\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment...
    %PYTHON_CMD% -m venv %VENV_NAME%

    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)

echo [INFO] Activating virtual environment...
call %VENV_NAME%\Scripts\activate.bat

REM Always sync dependencies (pip skips already-installed packages)
if exist "requirements.txt" (
    echo [INFO] Syncing dependencies...
    python -m pip install --upgrade pip --quiet 2>nul
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
    echo [OK] Dependencies ready
) else (
    echo [ERROR] requirements.txt not found
    pause
    exit /b 1
)

REM Check if Ollama is running
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama no esta corriendo. Ejecuta 'ollama serve' en otra terminal.
) else (
    echo [OK] Ollama detectado
)

echo.
echo ===================================
echo   Starting FemtoBot...
echo ===================================
echo.

REM Run the bot
python src\telegram_bot.py

REM Deactivate virtual environment on exit
call deactivate

pause
