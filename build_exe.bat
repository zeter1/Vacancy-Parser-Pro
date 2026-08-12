@echo off
setlocal
cd /d "%~dp0"

py -3 -m pip install -r requirements.txt
if errorlevel 1 goto :error

py -3 -m pip install pyinstaller
if errorlevel 1 goto :error

py -3 -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "Vacancy Parser Pro" ^
  --icon "icon.ico" ^
  --add-data "icon.ico;." ^
  vacancy_parser.py
if errorlevel 1 goto :error

echo.
echo Build finished. See dist\Vacancy Parser Pro.exe
pause
exit /b 0

:error
echo.
echo Build failed.
pause
exit /b 1
