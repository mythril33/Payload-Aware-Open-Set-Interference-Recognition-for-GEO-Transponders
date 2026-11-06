@echo off
setlocal
title GEO Islem Durdur
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0geo_workbench.ps1" -Action stop-pilot
set GEO_SONUC=%ERRORLEVEL%
if not "%GEO_SONUC%"=="0" pause
exit /b %GEO_SONUC%
