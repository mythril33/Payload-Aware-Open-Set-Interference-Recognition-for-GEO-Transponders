@echo off
title RF-ML Ogrenme Uygulamasi
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_app.ps1" -App rfml
if not "%ERRORLEVEL%"=="0" pause
