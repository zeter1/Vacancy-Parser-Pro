@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

rem Vacancy Parser Pro - verified Windows build entrypoint.
rem Double-click for a full ready build. Detailed guide: BUILD_EXE.md
rem Modes: --fast --clean --diagnose --ci --no-pause

set "NO_PAUSE="
set "PS_ARGS="
:parse
if "%~1"=="" goto run
if /i "%~1"=="--ci" (
  set "NO_PAUSE=1"
  set "PS_ARGS=!PS_ARGS! -Ci"
) else if /i "%~1"=="--no-pause" (
  set "NO_PAUSE=1"
) else if /i "%~1"=="--fast" (
  set "PS_ARGS=!PS_ARGS! -Fast"
) else if /i "%~1"=="--clean" (
  set "PS_ARGS=!PS_ARGS! -Clean"
) else if /i "%~1"=="--diagnose" (
  set "PS_ARGS=!PS_ARGS! -Diagnose"
) else (
  echo [ERROR] Unknown option: %~1
  goto fail
)
shift
goto parse

:run
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_windows.ps1" !PS_ARGS!
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" goto failcode
echo.
echo [OK] Verified distribution is ready in %CD%\dist
goto ok

:failcode
echo.
echo [ERROR] Build failed with exit code !RC!.
echo Check build_logs\last_build_summary.json and newest build_*.log.
if not defined NO_PAUSE pause
exit /b !RC!

:fail
echo.
echo [ERROR] Build was not started successfully.
if not defined NO_PAUSE pause
exit /b 1

:ok
if not defined NO_PAUSE pause
exit /b 0
