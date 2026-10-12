@echo off
rem IronyLab launcher. Uses the project environment:
rem   1) Scripts\python.exe in the project root, 2) .venv\Scripts\python.exe
rem Usage: run.cmd                    -- open the app
rem        run.cmd cli.py --text "x"  -- run any project script
rem        run.cmd check_llm.py       -- check the local LLM
setlocal
set "ROOT=%~dp0"
set "PY="
if exist "%ROOT%Scripts\python.exe" set "PY=%ROOT%Scripts\python.exe"
if not defined PY if exist "%ROOT%.venv\Scripts\python.exe" set "PY=%ROOT%.venv\Scripts\python.exe"
if not defined PY (
  echo Environment not found: neither Scripts\python.exe nor .venv\Scripts\python.exe
  echo Installation guide: INSTALL_RU.md
  pause
  exit /b 1
)
set "SCRIPT=app.py"
if not "%~1"=="" (
  set "SCRIPT=%~1"
  shift
)
echo Python: %PY%
echo Script: %SCRIPT%
"%PY%" "%ROOT%%SCRIPT%" %1 %2 %3 %4 %5 %6 %7 %8 %9
if errorlevel 1 pause