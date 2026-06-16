@echo off
REM ATC Guardian launcher — delegates to Python for all the real work.
REM Batch is only kept so that double-clicking or running `start` from
REM cmd.exe works.  All logic (mode detection, agent launch, log
REM routing) lives in scripts/start.py where path handling is sane.
REM
REM Usage:  start          (same as: python scripts/start.py)
REM         start --sim    (force offline mode)
REM         start --live   (force live mode)
REM         start --help   (show all options)

setlocal

REM --- resolve project root (directory of this script) ---
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

REM --- prefer the project venv, else fall back to uv ---
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if exist "%PYTHON%" (
    "%PYTHON%" "%ROOT%\scripts\start.py" %*
) else (
    uv run python "%ROOT%\scripts\start.py" %*
)

endlocal
