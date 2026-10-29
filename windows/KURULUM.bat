@echo off
title Payload-Aware GEO Workbench - Kurulum
echo Payload-Aware GEO Workbench kurulumu basliyor...
echo Ayrintilar asagida ve windows\logs klasorundeki install-*.log dosyasindadir.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set KURULUM_SONUC=%ERRORLEVEL%
echo.
if "%KURULUM_SONUC%"=="0" (
    echo [OK] Kurulum tamamlandi. Masaustundeki kisayollardan uygulamalari baslatabilirsiniz.
) else (
    echo [HATA] Kurulum basarisiz oldu. windows\logs klasorundeki son install-*.log dosyasina bakin.
)
echo.
pause
exit /b %KURULUM_SONUC%
