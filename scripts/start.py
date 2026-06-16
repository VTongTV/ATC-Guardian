"""ATC Guardian system launcher — single entry point for all modes.

Detects ``BAND_MODE`` from ``.env``, validates agent credentials, and
starts the right combination of services:

- **sim**  → backend + frontend (offline, no API keys)
- **live** → backend + 6 agent processes + frontend

Agent output is captured to ``logs/agent_<name>.log`` so you can inspect
all agents without juggling console windows.

Usage::

    python scripts/start.py           # auto-detect mode from .env
    python scripts/start.py --sim    # force sim mode
    python scripts/start.py --live   # force live mode (warn if creds bad)
    python scripts/start.py --no-agents   # live mode but skip agent launch
    python scripts/start.py --help

Or from cmd.exe::

    start.bat            # delegates to this script
"""

from __future__ import annotations

import argparse
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

AGENT_NAMES = [
    "coordinator",
    "conflict_detector",
    "weather_analyst",
    "safety_reviewer",
    "ground_ops",
    "emergency_response",
]

# Track all child processes for cleanup
_processes: list[subprocess.Popen] = []
# Track open log-file handles so they stay alive until cleanup
_log_file_handles: list[object] = []


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


def _check_band_mode() -> str:
    """Run ``scripts/_check_band_mode.py`` and return its output.

    Returns one of:
        ``sim``, ``live:ok``, ``live:skip:<reason>``
    """
    script = PROJECT_ROOT / "scripts" / "_check_band_mode.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=15,
        )
        return result.stdout.strip() or "live:skip:check_failed"
    except Exception as exc:
        logger.warning("Band mode check failed: %s", exc)
        return f"live:skip:check_error:{exc}"


def _resolve_mode(args: argparse.Namespace) -> tuple[str, bool]:
    """Determine the effective mode and whether to launch agents.

    Returns:
        (mode_label, launch_agents) — e.g. ``("LIVE", True)``.
    """
    if args.sim:
        return "SIM", False

    mode_raw = _check_band_mode()

    if mode_raw == "sim":
        return "SIM", False

    if mode_raw == "live:ok":
        if args.no_agents:
            return "LIVE (no agents)", False
        return "LIVE", True

    # live:skip:* — agents can't launch
    if mode_raw.startswith("live:skip:"):
        reason = mode_raw[len("live:skip:"):]
        logger.warning(
            "BAND_MODE=live but agent credentials issue: %s", reason
        )
        logger.warning(
            "Agents will NOT be launched. AGENT COMMS will stay at (0)."
        )
        return "LIVE (agents skipped)", False

    return "LIVE (agents skipped)", False


# ---------------------------------------------------------------------------
# Service launchers
# ---------------------------------------------------------------------------


def start_backend() -> subprocess.Popen:
    """Start the FastAPI backend server."""
    logger.info("Starting backend on port %d...", BACKEND_PORT)
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.app.main:app",
            "--host", "0.0.0.0",
            "--port", str(BACKEND_PORT),
            "--reload",
        ],
        cwd=PROJECT_ROOT,
    )
    _processes.append(proc)
    logger.info("Backend started (PID %d)", proc.pid)
    return proc


def start_agent(
    agent_name: str, log_dir: Path | None = None
) -> subprocess.Popen | None:
    """Start a single agent process.

    Args:
        agent_name: Directory name under ``agents/``.
        log_dir: If given, redirect stdout+stderr to
            ``<log_dir>/agent_<name>.log``.

    Returns:
        Subprocess handle, or None if the agent directory is missing.
    """
    agent_dir = PROJECT_ROOT / "agents" / agent_name
    if not agent_dir.exists():
        logger.warning("Agent directory not found: %s — skipping", agent_dir)
        return None

    logger.info("Starting agent: %s...", agent_name)

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


def start_agents(log_dir: Path | None = None) -> int:
    """Start all 6 specialist agents.

    Args:
        log_dir: If given, each agent writes to a log file.

    Returns:
        Number of agents successfully launched.
    """
    count = 0
    for name in AGENT_NAMES:
        proc = start_agent(name, log_dir=log_dir)
        if proc is not None:
            count += 1
            time.sleep(0.5)  # Stagger starts
    return count


def start_frontend() -> subprocess.Popen | None:
    """Start the Vite frontend dev server."""
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


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


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
    for lf in _log_file_handles:
        try:
            lf.close()  # type: ignore[union-attr]
        except Exception:
            pass
    logger.info("All processes stopped")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(
        description="ATC Guardian system launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/start.py           # auto-detect from .env\n"
            "  python scripts/start.py --sim     # force offline mode\n"
            "  python scripts/start.py --live    # force live mode\n"
            "  python scripts/start.py --no-agents  # live, skip agents\n"
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--sim", action="store_true",
        help="Force sim (offline) mode — no Band agents launched",
    )
    mode.add_argument(
        "--live", action="store_true",
        help="Force live mode — validates credentials before launching agents",
    )
    p.add_argument(
        "--no-agents", action="store_true",
        help="Start in live mode but skip agent processes "
             "(AGENT COMMS will stay at 0)",
    )
    return p


def main() -> None:
    """Parse args, detect mode, launch services, and wait."""
    args = build_parser().parse_args()
    mode_label, launch_agents = _resolve_mode(args)
    log_dir = PROJECT_ROOT / "logs"

    logger.info("=" * 60)
    logger.info("  ATC Guardian System Starter")
    logger.info("  Project root:  %s", PROJECT_ROOT)
    logger.info("  Mode:          %s", mode_label)
    logger.info("  Agent logs:    %s", log_dir)
    logger.info("  Press Ctrl+C to stop all services")
    logger.info("=" * 60)

    # Register cleanup on exit
    signal.signal(signal.SIGINT, lambda *_: (cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), sys.exit(0)))

    # --- 1) Backend (always) ------------------------------------------------
    start_backend()
    time.sleep(2)

    # --- 2) Agents (live mode only) -----------------------------------------
    agent_count = 0
    if launch_agents:
        agent_count = start_agents(log_dir=log_dir)
        logger.info("Launched %d/%d agents", agent_count, len(AGENT_NAMES))

    # --- 3) Frontend (always) -----------------------------------------------
    start_frontend()

    # --- Summary ------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("  All services started")
    logger.info("  Backend:   http://localhost:%d", BACKEND_PORT)
    logger.info("  Frontend:  http://localhost:%d", FRONTEND_PORT)
    logger.info("  Docs:      http://localhost:%d/docs", BACKEND_PORT)
    if agent_count:
        logger.info("  Agents:    %d running  (logs in %s\\)", agent_count, log_dir)
    elif mode_label != "SIM":
        logger.info("  Agents:    NONE — AGENT COMMS will stay at (0)")
    logger.info("=" * 60)

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
