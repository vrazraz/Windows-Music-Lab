@echo off
cd /d "%~dp0"
powershell -NoProfile -File ".\windows\Start.ps1"
if errorlevel 1 pause
