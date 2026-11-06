@echo off
rem Scripted wsl.exe stand-in for the fake-WSL tests; see fake_wsl.py. Never calls a real WSL.
setlocal
set "GEO_FAKE_PY=python"
if defined GEO_FAKE_WSL_PYTHON set "GEO_FAKE_PY=%GEO_FAKE_WSL_PYTHON%"
"%GEO_FAKE_PY%" "%~dp0fake_wsl.py" %*
exit /b %ERRORLEVEL%
