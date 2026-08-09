@echo off
setlocal
chcp 65001 >nul
title IFC Quality Copilot - Benchmark

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -PackageRoot "%~dp0"
set "IFCQC_EXIT=%ERRORLEVEL%"

echo.
if not "%IFCQC_EXIT%"=="0" echo Falha. Consulte a mensagem exibida acima.
if not "%IFCQC_NO_PAUSE%"=="1" pause

endlocal & exit /b %IFCQC_EXIT%
