@echo off
setlocal
title GEO Workbench Kapat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0geo_workbench.ps1" -Action close
set GEO_SONUC=%ERRORLEVEL%
if not "%GEO_SONUC%"=="0" pause
exit /b %GEO_SONUC%
