@echo off
setlocal
chcp 65001 >nul
title IFC Quality Copilot - Ablacao de grounding (SEM bSDD)

rem Braco de tratamento da condicao de ablacao de grounding (2026-08-18).
rem Roda a MESMA fila do EXECUTAR_BENCHMARK.cmd com o bSDD desligado: a
rem identidade de execucao registra grounding_bsdd=false, entao os estagios
rem deste braco NAO colidem com os do braco padrao nem os reaproveitam.
rem
rem O braco COM bSDD ja esta medido (par unificado v7.7) e NAO precisa rodar
rem de novo — este pacote existe so para o lado que falta.

rem %~dp0 sempre termina em barra invertida, e a sequencia \" na linha de
rem comando do powershell.exe vira aspa literal: o parametro chegaria como
rem C:\pasta" e o install.ps1 abortaria antes de validar qualquer coisa.
set "IFCQC_PACKAGE_ROOT=%~dp0"
if "%IFCQC_PACKAGE_ROOT:~-1%"=="\" set "IFCQC_PACKAGE_ROOT=%IFCQC_PACKAGE_ROOT:~0,-1%"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -PackageRoot "%IFCQC_PACKAGE_ROOT%" -NoBsdd
set "IFCQC_EXIT=%ERRORLEVEL%"

echo.
if not "%IFCQC_EXIT%"=="0" echo Falha. Consulte a mensagem exibida acima.
if not "%IFCQC_NO_PAUSE%"=="1" pause

endlocal & exit /b %IFCQC_EXIT%
