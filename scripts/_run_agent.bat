@echo off
REM Helper: launch a single agent with log redirection.
REM Called by start.bat as:  _run_agent.bat <agent_name> <root> <python_cmd> <log_dir>
REM   %1 = agent name (e.g. conflict_detector)
REM   %2 = project root (e.g. D:\Web Project\lablab)
REM   %3 = python command (e.g. D:\Web Project\lablab\.venv\Scripts\python.exe)
REM   %4 = log directory (e.g. D:\Web Project\lablab\logs)

set "AGENT=%~1"
set "ROOT=%~2"
set "PYCMD=%~3"
set "LOGDIR=%~4"

cd /d "%ROOT%\agents\%AGENT%"
set "PYTHONPATH=%ROOT%"

if "%LOGDIR%"=="" (
    "%PYCMD%" agent.py
) else (
    if not exist "%LOGDIR%" mkdir "%LOGDIR%"
    "%PYCMD%" agent.py > "%LOGDIR%\agent_%AGENT%.log" 2>&1
)
