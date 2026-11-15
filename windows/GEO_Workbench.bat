@echo off
setlocal
title GEO Workbench
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0geo_workbench.ps1" -Action open
set GEO_SONUC=%ERRORLEVEL%
if not "%GEO_SONUC%"=="0" pause
exit /b %GEO_SONUC%
