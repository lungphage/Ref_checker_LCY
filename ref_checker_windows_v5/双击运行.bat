@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

python -X utf8 "%~dp0ref_checker_gui.py"
if errorlevel 1 (
    echo.
    echo Program failed. Please try RUN_ME_FIRST.cmd or 环境检查.cmd first.
    pause
)
