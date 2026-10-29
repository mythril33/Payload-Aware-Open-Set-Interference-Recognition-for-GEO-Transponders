@echo off
title GEO Arastirma Panosu
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_app.ps1" -App dashboard
if not "%ERRORLEVEL%"=="0" pause
