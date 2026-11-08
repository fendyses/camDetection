@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Run the Windows installation steps first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" web_app.py

if errorlevel 1 (
    echo.
    echo camDetection stopped with an error.
    pause
)
