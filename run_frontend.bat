@echo off
REM Trading Signal System - Frontend Startup Script (Windows)

echo.
echo ========================================
echo Trading Signal System - Frontend Server
echo ========================================
echo.

REM Resolve Python. Windows may have a Microsoft Store placeholder earlier on PATH.
set "PYTHON_EXE=python"
if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Python\bin\python.exe"

REM Check if Python is installed
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    pause
    exit /b 1
)

cd frontend

echo.
echo ========================================
echo Starting Frontend Server...
echo ========================================
echo Frontend will start on http://localhost:3000
echo.
echo Make sure the backend is running on http://localhost:8000
echo.
echo Press Ctrl+C to stop the server
echo.

"%PYTHON_EXE%" -m http.server 3000

pause
