@echo off
setlocal
cd /d "%~dp0"
py -3 vacancy_parser.py
if errorlevel 1 (
  echo.
  echo Program exited with an error.
  pause
)
