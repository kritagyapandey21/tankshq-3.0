@echo off
REM Trading Signal System - Windows Startup Script

echo.
echo ========================================
echo Trading Signal System - Startup
echo ========================================
echo.

REM Resolve Python. Windows may have a Microsoft Store placeholder earlier on PATH.
set "PYTHON_EXE=python"
if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Python\bin\python.exe"

REM Check if Python is installed
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Setup backend
echo Setting up backend...
cd backend

REM Check if venv exists
if not exist "venv" (
    echo Creating virtual environment...
    "%PYTHON_EXE%" -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install requirements
echo Installing dependencies...
pip install -r requirements.txt --quiet

REM Start backend
echo.
echo ========================================
echo Starting Backend Server...
echo ========================================
echo Backend will start on http://localhost:8000
echo API Documentation: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop the server
echo.

"%PYTHON_EXE%" app.py

pause
