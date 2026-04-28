@echo off
setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0single_file_builder\build_single_file.ps1"
if errorlevel 1 pause
