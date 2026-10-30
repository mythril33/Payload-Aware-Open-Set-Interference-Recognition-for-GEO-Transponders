@echo off
title Uygulamalari Durdur
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_apps.ps1"
pause
