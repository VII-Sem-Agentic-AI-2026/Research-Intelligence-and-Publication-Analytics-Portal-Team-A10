@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_cloudflare.ps1" %*
set "PORTAL_EXIT=%ERRORLEVEL%"
if not "%PORTAL_EXIT%"=="0" (
  echo.
  echo Cloudflare launcher stopped with an error. See the message above.
  pause
)
exit /b %PORTAL_EXIT%
