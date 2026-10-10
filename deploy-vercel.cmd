@echo off
wsl.exe --distribution Ubuntu --cd /home/ezzed/defi-hackathon-2026 -- bash ./deploy-vercel.sh
if errorlevel 1 (
  echo.
  echo Deployment was not triggered. See the error above.
) else (
  echo.
  echo The deployment commit was pushed.
)
pause
