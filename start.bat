@echo off
REM ---------------------------------------------------------------------------
REM  Double-click this file to start the app.
REM  It runs the real logic in scripts\start.ps1 so behaviour is identical
REM  whether you double-click or run the script by hand.
REM ---------------------------------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed - see the messages above.
  pause
)
