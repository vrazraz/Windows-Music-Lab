@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\Start-Full.ps1" %*
if errorlevel 1 (
  echo.
  echo Full studio stopped with an error. Read the message above.
  pause
)
endlocal
