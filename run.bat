@echo off
setlocal enabledelayedexpansion

REM FemtoBot Windows Launcher
REM This script sets up and runs FemtoBot on Windows

set "VENV_NAME=venv_bot"
set "PYTHON_CMD=python"

REM Check if Python 3.12 is available
%PYTHON_CMD% --version 2>nul | find "3.12" >nul
if errorlevel 1 (
    echo [WARNING] Python 3.12 not found as default python
    
    REM Try python3
    python3 --version 2>nul | find "3.12" >nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python3"
    ) else (
        REM Try py
        py -3.12 --version 2>nul
        if not errorlevel 1 (
            set "PYTHON_CMD=py -3.12"
        ) else (
            echo [ERROR] Python 3.12 is required but not found.
            echo Please install Python 3.12 from https://www.python.org/downloads/
            pause
            exit /b 1
        )
    )
)

echo ===================================
echo   FemtoBot - Windows Setup
echo ===================================

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

REM Check if dependencies are installed
%PYTHON_CMD% -c "import telegram" 2>nul
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    
    REM Upgrade pip
    python -m pip install --upgrade pip --quiet
    
    REM Install requirements
    if exist "requirements.txt" (
        pip install -r requirements.txt
        if errorlevel 1 (
            echo [ERROR] Failed to install dependencies
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] requirements.txt not found
        pause
        exit /b 1
    )
    
    echo [SUCCESS] Dependencies installed!
) else (
    echo [OK] Dependencies already installed
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
