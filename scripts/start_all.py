"""Start script for ATC Guardian — launches all services.

Starts:
1. FastAPI backend (on port 8000)
2. 6 agent processes (using the project venv)
3. Frontend dev server (Vite on port 5173)

All processes run concurrently. Press Ctrl+C to stop all.

Usage:
    uv run python scripts/start_all.py
"""

import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_PORT = 8000
FRONTEND_PORT = 5173

# Track all child processes for cleanup
_processes: list[subprocess.Popen] = []
# Track open log-file handles so they stay alive (Popen keeps a ref but
# Python could GC the wrapper) and cleanup can flush/close them.
_log_file_handles: list[object] = []


def start_backend() -> subprocess.Popen:
    """Start the FastAPI backend server.

    Returns:
        Subprocess handle for the backend process.
    """
    logger.info("Starting backend on port %d...", BACKEND_PORT)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app",
         "--host", "0.0.0.0", "--port", str(BACKEND_PORT), "--reload"],
        cwd=PROJECT_ROOT,
    )
    _processes.append(proc)
    logger.info("Backend started (PID %d)", proc.pid)
    return proc


def start_agent(agent_name: str, log_dir: Path | None = None) -> subprocess.Popen | None:
    """Start a single agent process using the project venv.

    If *log_dir* is provided, stdout and stderr are tee'd to
    ``<log_dir>/agent_<name>.log`` (created/overwritten on each start)
    so that agent output is capturable without juggling console windows.

    Args:
        agent_name: Directory name under agents/ (e.g. "coordinator").
        log_dir: Optional directory for agent log files.

    Returns:
        Subprocess handle, or None if the agent directory is missing.
    """
    agent_dir = PROJECT_ROOT / "agents" / agent_name
    if not agent_dir.exists():
        logger.warning("Agent directory not found: %s — skipping", agent_dir)
        return None

    logger.info("Starting agent: %s...", agent_name)

    # Resolve the log file path if a log directory is configured.
    lf = None
    log_path: Path | None = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"agent_{agent_name}.log"
        lf = log_path.open("w")

    proc = subprocess.Popen(
        [sys.executable, "agent.py"],
        cwd=agent_dir,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        stdout=lf,
        stderr=subprocess.STDOUT if lf else None,
    )
    _processes.append(proc)
    if lf is not None:
        _log_file_handles.append(lf)
    logger.info(
        "Agent %s started (PID %d)%s",
        agent_name,
        proc.pid,
        f" → {log_path}" if log_path else "",
    )
    return proc


def start_frontend() -> subprocess.Popen | None:
    """Start the Vite frontend dev server.

    Returns:
        Subprocess handle for the frontend process, or None if npm is unavailable.
    """
    if shutil.which("npm") is None:
        logger.warning("npm not found on PATH — skipping frontend")
        return None

    frontend_dir = PROJECT_ROOT / "frontend"
    if not frontend_dir.exists():
        logger.warning("Frontend directory not found — skipping")
        return None

    logger.info("Starting frontend on port %d...", FRONTEND_PORT)
    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=frontend_dir,
        shell=True,  # Required on Windows to resolve npm.cmd
    )
    _processes.append(proc)
    logger.info("Frontend started (PID %d)", proc.pid)
    return proc


def cleanup() -> None:
    """Terminate all child processes gracefully and close log files."""
    logger.info("Shutting down %d processes...", len(_processes))
    for proc in _processes:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception:
                pass
    # Close any open log-file handles inherited by Popen.
    for lf in _log_file_handles:
        try:
            lf.close()  # type: ignore[union-attr]
        except Exception:
            pass
    logger.info("All processes stopped")


def main() -> None:
    """Start all ATC Guardian services."""
    log_dir = PROJECT_ROOT / "logs"

    logger.info("ATC Guardian System Starter")
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Agent logs:  %s", log_dir)
    logger.info("Press Ctrl+C to stop all services")
    logger.info("=" * 50)

    # Register cleanup on exit
    signal.signal(signal.SIGINT, lambda *_: (cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), sys.exit(0)))

    # Start backend first
    start_backend()
    time.sleep(2)  # Give backend time to start

    # Start agents — each writes output to logs/agent_<name>.log
    agent_names = [
        "coordinator",
        "conflict_detector",
        "weather_analyst",
        "safety_reviewer",
        "ground_ops",
        "emergency_response",
    ]
    for agent_name in agent_names:
        start_agent(agent_name, log_dir=log_dir)
        time.sleep(0.5)  # Stagger agent starts

    # Start frontend
    start_frontend()

    logger.info("=" * 50)
    logger.info("All services started")
    logger.info("Backend:  http://localhost:%d", BACKEND_PORT)
    logger.info("Frontend: http://localhost:%d", FRONTEND_PORT)
    logger.info("Docs:     http://localhost:%d/docs", BACKEND_PORT)
    logger.info("Logs:     %s\\", log_dir)

    # Wait for any process to exit
    try:
        for proc in _processes:
            proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
