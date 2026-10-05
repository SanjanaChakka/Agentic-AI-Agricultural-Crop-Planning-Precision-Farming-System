@echo off
REM ---------------------------------------------------------------------------
REM  Stops the app. The database lives in a Docker volume, so demo data and
REM  any approvals you recorded survive a stop/start. Pass -v to delete it too.
REM ---------------------------------------------------------------------------
cd /d "%~dp0"

docker compose down
if errorlevel 1 (
  echo.
  echo Could not reach Docker. Is Docker Desktop running?
  pause
  exit /b 1
)

echo.
echo Stopped. Your data is kept in the Docker volume "appdata".
echo Run start.bat to start the app again.
echo.
pause
