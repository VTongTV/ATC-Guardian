@echo off
REM ============================================================================
REM ATC Guardian - local dev launcher (Windows)
REM   Detects BAND_MODE and starts the right processes:
REM
REM     BAND_MODE=sim   -> backend + frontend only (offline, no API keys)
REM     BAND_MODE=live  -> backend + 6 agent processes + frontend
REM
REM   Each service opens its own console window. Close a window (or Ctrl+C)
REM   to stop that service.
REM
REM   WHY the agents are separate processes in live mode:
REM   In live mode the backend only POSTs @mentions into the Band room; it
REM   does NOT run the LLMs. The six specialist agents (conflict-detector,
REM   weather-analyst, emergency-response, safety-reviewer, ground-ops,
REM   coordinator) are standalone processes that connect to Band over
REM   WebSocket and actually answer the @mentions. If they are not running,
REM   the Band room fills with "Coordinator" dispatches that nobody replies
REM   to and the AGENT COMMS panel stays at (0).
REM ============================================================================

setlocal enabledelayedexpansion

REM --- resolve project root (location of this script) ------------------------
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

echo ATC Guardian local launcher
echo Project root: %ROOT%
echo.

REM --- sanity: warn if .env is missing ---------------------------------------
if not exist ".env" (
    echo [WARN] No .env found. Copy .env.example to .env and fill it in.
    echo        Backend will still start but agent LLM calls will fail.
    echo.
)

REM --- pick a python: prefer the project venv, else fall back to uv ----------
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [INFO]  .venv not found, using 'uv run python'.
    set "PYCMD=uv run python"
) else (
    set "PYCMD=%PYTHON%"
)

REM ---------------------------------------------------------------------------
REM Read BAND_MODE and validate live-mode credentials from .env using Python
REM (batch parsing of .env is too error-prone). The helper prints one of:
REM   sim              -> offline mode
REM   live:ok          -> live mode, all 6 agent creds look real
REM   live:skip:REASON -> live mode but creds are placeholders; do NOT launch
REM ---------------------------------------------------------------------------
set "MODE=live:skip:unread"
for /f "delims=" %%i in ('"%PYCMD%" "%ROOT%\scripts\_check_band_mode.py" 2^>nul') do set "MODE=%%i"

echo [INFO]  Band mode check: !MODE!
echo.

REM --- 1) backend ------------------------------------------------------------
echo Starting backend on http://localhost:8000 ...
start "ATC Backend" cmd /k "cd /d "%ROOT%" && %PYCMD% -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"

REM give the backend a moment before the agents/frontend poll it
timeout /t 2 /nobreak >nul

REM --- 2) agents (live mode only) -------------------------------------------
REM    Each agent is launched from its own directory so that:
REM      - `from prompts import ...` resolves (script dir on sys.path), and
REM      - python-dotenv's load_dotenv() finds .env by searching up to ROOT.
set "AGENTS=coordinator conflict_detector weather_analyst safety_reviewer ground_ops emergency_response"

if /i "!MODE!"=="live:ok" (
    echo.
    echo [INFO] BAND_MODE=live with valid agent credentials.
    echo [INFO] Starting 6 agent processes ^(one window each^)...
    echo [INFO] Agent logs: %ROOT%\logs\agent_*.log
    echo.
    for %%A in (!AGENTS!) do (
        if exist "%ROOT%\agents\%%A\agent.py" (
            echo   - starting %%A  ^>  logs\agent_%%A.log
            start "ATC Agent: %%A" cmd /k "%ROOT%\scripts\_run_agent.bat" "%%A" "%ROOT%" "%PYCMD%" "%ROOT%\logs"
        ) else (
            echo   [WARN] agents\%%A\agent.py not found - skipping %%A
        )
        timeout /t 1 /nobreak >nul
    )
) else if "!MODE:~0,10!"=="live:skip:" (
    echo [WARN] BAND_MODE=live but agent credentials are not configured:
    echo        !MODE!
    echo [WARN] Skipping agent launch. The Band room will receive @mentions
    echo        that NOBODY answers, and AGENT COMMS will stay at (0).
    echo        Set the 6 *_AGENT_ID / *_API_KEY pairs in .env, then re-run.
    echo.
) else if /i "!MODE!"=="sim" (
    echo [INFO] BAND_MODE=sim - offline simulation, no agent processes needed.
    echo.
)

REM --- 3) frontend -----------------------------------------------------------
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] npm not found on PATH - skipping frontend.
    echo        Install Node.js from https://nodejs.org to run the frontend.
    goto :done
)

echo Starting frontend on http://localhost:5173 ...
start "ATC Frontend" cmd /k "cd /d "%ROOT%\frontend" && npm.cmd run dev"

:done
echo.
echo ============================================================
if /i "!MODE!"=="live:ok" (
    echo  Mode:     LIVE  ^(backend + 6 agents + frontend^)
) else if "!MODE:~0,4!"=="live" (
    echo  Mode:     LIVE  ^(backend + frontend ONLY - agents NOT started!^)
) else (
    echo  Mode:     SIM   ^(backend + frontend^)
)
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo  Docs:     http://localhost:8000/docs
echo.
echo  Close each console window (or Ctrl+C) to stop that service.
echo ============================================================
echo.
echo This window can be closed; services keep running in their own windows.

endlocal
