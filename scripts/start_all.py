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


def start_agent(agent_name: str) -> subprocess.Popen | None:
    """Start a single agent process using the project venv.

    Args:
        agent_name: Directory name under agents/ (e.g. "coordinator").

    Returns:
        Subprocess handle, or None if the agent directory is missing.
    """
    agent_dir = PROJECT_ROOT / "agents" / agent_name
    if not agent_dir.exists():
        logger.warning("Agent directory not found: %s — skipping", agent_dir)
        return None

    logger.info("Starting agent: %s...", agent_name)
    proc = subprocess.Popen(
        [sys.executable, "agent.py"],
        cwd=agent_dir,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    _processes.append(proc)
    logger.info("Agent %s started (PID %d)", agent_name, proc.pid)
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
    """Terminate all child processes gracefully."""
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
    logger.info("All processes stopped")


def main() -> None:
    """Start all ATC Guardian services."""
    logger.info("ATC Guardian System Starter")
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Press Ctrl+C to stop all services")
    logger.info("=" * 50)

    # Register cleanup on exit
    signal.signal(signal.SIGINT, lambda *_: (cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), sys.exit(0)))

    # Start backend first
    start_backend()
    time.sleep(2)  # Give backend time to start

    # Start agents
    agent_names = [
        "coordinator",
        "conflict_detector",
        "weather_analyst",
        "safety_reviewer",
        "ground_ops",
        "emergency_response",
    ]
    for agent_name in agent_names:
        start_agent(agent_name)
        time.sleep(0.5)  # Stagger agent starts

    # Start frontend
    start_frontend()

    logger.info("=" * 50)
    logger.info("All services started")
    logger.info("Backend:  http://localhost:%d", BACKEND_PORT)
    logger.info("Frontend: http://localhost:%d", FRONTEND_PORT)
    logger.info("Docs:     http://localhost:%d/docs", BACKEND_PORT)

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
