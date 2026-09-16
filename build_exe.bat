@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

rem ============================================================================
rem Vacancy Parser Pro - ready Windows EXE builder
rem
rem Double-click this file. It will:
rem   1. Find tested Python 3.13 or install it with winget for the current user.
rem   2. Create isolated .build-venv so normal Python is not modified.
rem   3. Install all requirements.txt dependencies and pinned PyInstaller tools.
rem   4. Compile sources, run unit tests and an offline source self-test.
rem   5. Build one-file Windows GUI EXE.
rem   6. Copy icon.ico next to the EXE because the frozen app resolves writable
rem      files/resources from the EXE directory.
rem   7. Launch the packaged EXE with --self-test and fail if it is incomplete.
rem
rem Result: dist\Vacancy Parser Pro.exe + dist\icon.ico
rem Keep these two files together. No Python installation is needed to RUN the EXE.
rem CI/Codex: build_exe.bat --ci
rem Full guide: BUILD_EXE.md
rem ============================================================================

set "NO_PAUSE="
if /i "%~1"=="--ci" set "NO_PAUSE=1"
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"

call :find_python313
if not defined BASE_PY call :install_python
if not defined BASE_PY goto :fail

set "BUILD_VENV=%CD%\.build-venv"
set "BUILD_PY=%BUILD_VENV%\Scripts\python.exe"

if exist "%BUILD_PY%" (
    "%BUILD_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [SETUP] Existing build environment uses another Python version. Recreating it...
        rmdir /s /q "%BUILD_VENV%" || goto :fail
    )
)

if not exist "%BUILD_PY%" (
    echo [1/7] Creating isolated Python 3.13 build environment...
    "%BASE_PY%" -m venv "%BUILD_VENV%" || goto :fail
) else (
    echo [1/7] Reusing isolated Python 3.13 build environment...
)

echo [2/7] Installing application and packaging dependencies...
"%BUILD_PY%" -m pip install --disable-pip-version-check --no-input --timeout 60 --retries 2 -r requirements.txt || goto :fail
"%BUILD_PY%" -m pip install --disable-pip-version-check --no-input --timeout 60 --retries 2 "pyinstaller==6.22.3" "pyinstaller-hooks-contrib>=2026.6" || goto :fail
"%BUILD_PY%" -m pip check || goto :fail

echo [3/7] Compiling sources and running offline verification...
"%BUILD_PY%" -m compileall -q vacancy_parser.py vacancy_gui.py job_scraper.py problem_logging.py tests || goto :fail
"%BUILD_PY%" -m unittest discover -s tests -v || goto :fail
"%BUILD_PY%" vacancy_parser.py --self-test || goto :fail

echo [4/7] Checking required build resources...
if not exist "icon.ico" (
    echo [ERROR] Required icon.ico is missing.
    goto :fail
)

echo [5/7] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "Vacancy Parser Pro.spec" del /q "Vacancy Parser Pro.spec"

echo [6/7] Building Vacancy Parser Pro.exe...
"%BUILD_PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "Vacancy Parser Pro" ^
  --icon "icon.ico" ^
  vacancy_parser.py || goto :fail

if not exist "dist\Vacancy Parser Pro.exe" (
    echo [ERROR] PyInstaller finished without the expected EXE.
    goto :fail
)
copy /Y "icon.ico" "dist\icon.ico" >nul || goto :fail

echo [7/7] Running packaged offline self-test...
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath '.\dist\Vacancy Parser Pro.exe' -ArgumentList '--self-test' -PassThru -Wait; exit $p.ExitCode" || goto :fail

echo.
echo [OK] READY BUILD CREATED AND VERIFIED.
echo EXE : %CD%\dist\Vacancy Parser Pro.exe
echo ICON: %CD%\dist\icon.ico
echo.
echo Copy the whole dist folder when moving the application to another PC.
goto :success

:find_python313
set "BASE_PY="
if defined pythonLocation if exist "%pythonLocation%\python.exe" (
    "%pythonLocation%\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>nul
    if not errorlevel 1 set "BASE_PY=%pythonLocation%\python.exe"
)
if defined BASE_PY exit /b 0
where py >nul 2>nul && for /f "delims=" %%P in ('py -3.13 -c "import sys; print(sys.executable)" 2^>nul') do set "BASE_PY=%%P"
if defined BASE_PY exit /b 0
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%ProgramFiles%\Python313\python.exe") do if exist "%%~P" set "BASE_PY=%%~P"
if defined BASE_PY exit /b 0
where python >nul 2>nul && python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>nul && for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)"') do set "BASE_PY=%%P"
exit /b 0

:install_python
echo [SETUP] Tested Python 3.13 was not found. Trying automatic per-user installation...
where winget >nul 2>nul || (
    echo [ERROR] Python 3.13 is missing and Windows Package Manager ^(winget^) is unavailable.
    echo Install Python 3.13 from python.org, then run this file again.
    exit /b 1
)
winget install --id Python.Python.3.13 -e --scope user --silent --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo [ERROR] Automatic Python 3.13 installation failed.
    exit /b 1
)
call :find_python313
exit /b 0

:fail
echo.
echo [ERROR] EXE build failed. Read the first error above.
echo A stale or incomplete output is NOT reported as ready.
if not defined NO_PAUSE pause
exit /b 1

:success
if not defined NO_PAUSE pause
exit /b 0
