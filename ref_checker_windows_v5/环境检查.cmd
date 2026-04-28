@echo off
setlocal
chcp 65001 >nul
title Reference Checker Environment Check
cd /d "%~dp0"

echo ==========================================================
echo Environment Check
echo ==========================================================
echo Current folder: %CD%
echo.

echo [1/5] where python
where python
echo.

echo [2/5] python --version
python --version
echo.

echo [3/5] tkinter
python -X utf8 -c "import tkinter; print('tkinter OK')"
echo.

echo [4/5] Crossref network test
python -X utf8 -c "import urllib.request; print(urllib.request.urlopen('https://api.crossref.org/works?rows=0', timeout=20).status)"
echo.

echo [5/5] OpenAlex network test
python -X utf8 -c "import urllib.request; print(urllib.request.urlopen('https://api.openalex.org/works?per-page=1', timeout=20).status)"
echo.

echo Check finished.
echo If any step fails, please send a screenshot and debug_log.txt.
pause
