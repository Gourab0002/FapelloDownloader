@echo off
setlocal
title Fapello Downloader
cd /d "%~dp0"

echo ===================================================
echo               Fapello Downloader
echo ===================================================
echo.

:: Check for Python Launcher (py)
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py main.py
    goto end
)

:: Check for python
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python main.py
    goto end
)

:: Check for python3
where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python3 main.py
    goto end
)

echo [ERROR] Python is not installed or not found in PATH!
echo Please install Python 3.8+ from https://www.python.org/
echo.

:end
echo.
pause
