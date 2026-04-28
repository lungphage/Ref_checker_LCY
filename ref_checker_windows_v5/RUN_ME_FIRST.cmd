@echo off
setlocal
chcp 65001 >nul
title Reference Checker v5
cd /d "%~dp0"

echo ==========================================================
echo Reference Checker v5
echo ==========================================================
echo Current folder: %CD%
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Please install Python and enable "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/4] Python path
where python
echo.

echo [2/4] Python version
python --version
echo.

echo [3/4] Check tkinter
python -X utf8 -c "import tkinter; print('tkinter OK')"
if errorlevel 1 (
    echo.
    echo [ERROR] tkinter is not available.
    echo Re-run the Python installer, choose Modify, and enable tcl/tk and IDLE.
    echo.
    pause
    exit /b 1
)
echo.

echo [4/4] Launch program
echo If the window does not appear, check debug_log.txt in this folder.
echo.

python -X utf8 "%~dp0ref_checker_gui.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Program exited unexpectedly.
    echo Please send this window output and debug_log.txt.
    echo.
    pause
    exit /b 1
)

echo.
echo Program closed.
pause
