@echo off
REM ============================================================================
REM ATC Guardian - local dev launcher
REM   Opens two console windows:
REM     1) FastAPI backend  -> http://localhost:8000   (docs: /docs)
REM     2) Vite frontend    -> http://localhost:5173
REM   Close a window (or Ctrl+C) to stop that service.
REM ============================================================================

setlocal

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
    set "PYCMD="%PYTHON%""
)

REM --- 1) backend ------------------------------------------------------------
echo Starting backend on http://localhost:8000 ...
start "ATC Backend" cmd /k ^
    "cd /d "%ROOT%" && %PYCMD% -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"

REM give the backend a moment before the frontend polls it
timeout /t 2 /nobreak >nul

REM --- 2) frontend -----------------------------------------------------------
echo Starting frontend on http://localhost:5173 ...
start "ATC Frontend" cmd /k "cd /d "%ROOT%\frontend" && npm run dev"

echo.
echo ============================================================
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo  Docs:     http://localhost:8000/docs
echo.
echo  Close each console window (or Ctrl+C) to stop that service.
echo ============================================================
echo.
echo This window can be closed; services keep running in their own windows.

endlocal
