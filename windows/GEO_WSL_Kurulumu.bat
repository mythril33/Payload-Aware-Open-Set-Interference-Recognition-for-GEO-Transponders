@echo off
setlocal
title GEO WSL Kurulumu
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_wsl_backend.ps1"
set GEO_SONUC=%ERRORLEVEL%
echo.
pause
exit /b %GEO_SONUC%
