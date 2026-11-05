@echo off
setlocal
title GEO Pilot Baslat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0geo_workbench.ps1" -Action pilot -Groups 1
set GEO_SONUC=%ERRORLEVEL%
if not "%GEO_SONUC%"=="0" pause
exit /b %GEO_SONUC%
