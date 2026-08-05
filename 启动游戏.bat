@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Chinese Checkers Launcher

echo.
echo ==========================================
echo       Chinese Checkers - Launcher
echo ==========================================
echo.

if not exist "launcher.py" (
    echo [ERROR] launcher.py is missing.
    echo Please extract the complete ZIP package before starting the game.
    echo Do not run the BAT directly inside the ZIP preview window.
    echo.
    pause
    exit /b 1
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 "launcher.py"
    set "EXIT_CODE=%errorlevel%"
    goto :finished
)

where python >nul 2>&1
if not errorlevel 1 (
    python "launcher.py"
    set "EXIT_CODE=%errorlevel%"
    goto :finished
)

echo [ERROR] Python 3.10 or newer was not found.
echo Install Python and enable "Add Python to PATH".
echo https://www.python.org/downloads/
set "EXIT_CODE=1"

:finished
echo.
if "%EXIT_CODE%"=="0" (
    echo The game server has stopped.
) else (
    echo Startup failed. Open startup.log in this folder for details.
)
echo.
pause
exit /b %EXIT_CODE%
