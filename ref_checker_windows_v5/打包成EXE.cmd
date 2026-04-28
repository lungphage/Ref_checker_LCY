@echo off
setlocal
chcp 65001 >nul
title Pack Reference Checker EXE
cd /d "%~dp0"

echo ==========================================================
echo Pack EXE
echo ==========================================================
echo Current folder: %CD%
echo.
echo Default mode: small-size preferred
echo Output type: folder package (not onefile)
echo.

set "PY_CMD=python"
py -3.13 -V >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.13"
)

if "%PY_CMD%"=="python" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python was not found.
        pause
        exit /b 1
    )
)

echo Preferred Python command: %PY_CMD%
echo.

for /f "usebackq delims=" %%i in (`%PY_CMD% -X utf8 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{sys.version_info.releaselevel}')"`) do set "PY_INFO=%%i"
for /f "tokens=1,2 delims=|" %%a in ("%PY_INFO%") do (
    set "PY_VER=%%a"
    set "PY_LEVEL=%%b"
)

echo Detected Python: %PY_VER% [%PY_LEVEL%]
echo.

if /i not "%PY_LEVEL%"=="final" (
    echo [ERROR] This Python is a prerelease build: %PY_VER% [%PY_LEVEL%]
    echo PyInstaller packaging is not reliable in this environment.
    echo Please install a stable Python 3.12, 3.13, or 3.14, then run this script again.
    echo.
    echo Suggested stable installers:
    echo - Python 3.13.x 64-bit
    echo - Python 3.12.x 64-bit
    pause
    exit /b 1
)

for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)

if "%PY_MAJOR%"=="3" if %PY_MINOR% GEQ 15 (
    echo [ERROR] Python %PY_VER% is too new for this packaging workflow.
    echo Please switch to stable Python 3.12, 3.13, or 3.14.
    pause
    exit /b 1
)

echo [1/2] Install or update build dependencies
echo Upgrading PyInstaller and keeping setuptools compatible with older hooks...
%PY_CMD% -m pip install --upgrade "pip" "wheel" "setuptools<82" -i https://pypi.org/simple
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to prepare pip / wheel / setuptools.
    pause
    exit /b 1
)
%PY_CMD% -m pip install --upgrade "pyinstaller" "pyinstaller-hooks-contrib" -i https://pypi.org/simple
if errorlevel 1 (
    echo.
    echo [ERROR] pyinstaller install failed.
    pause
    exit /b 1
)
echo.

echo [2/2] Build EXE
echo Using --onedir to avoid the very large single-file EXE created by --onefile
%PY_CMD% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name ReferenceChecker ^
  ref_checker_gui.py
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Please check the output above.
    pause
    exit /b 1
)
echo.

echo Build finished.
echo Output folder: dist\ReferenceChecker\
echo Main EXE: dist\ReferenceChecker\ReferenceChecker.exe
echo.
echo Note:
echo - This mode keeps the EXE itself much smaller than --onefile.
echo - Keep the whole dist\ReferenceChecker folder together.
echo - A single EXE is possible, but it will usually be much larger.
echo - If you are using a prerelease Python such as 3.15 alpha, build stability may still vary.
pause
