"""Setup script for ATC Guardian development environment.

Creates virtual environments and installs dependencies for:
- Backend (project root venv)
- 5 agent venvs (each with own pyproject.toml)
- Frontend (npm install)

Usage:
    uv run python scripts/setup.py
"""

import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd: list[str], cwd: Path, label: str) -> None:
    """Execute a command and log the result.

    Args:
        cmd: Command and arguments to execute.
        cwd: Working directory for the command.
        label: Human-readable label for logging.

    Raises:
        SystemExit: If the command returns a non-zero exit code.
    """
    logger.info("Running: %s (in %s)", " ".join(cmd), cwd)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("%s FAILED:\n%s\n%s", label, result.stdout, result.stderr)
        sys.exit(1)
    logger.info("%s OK", label)


def setup_project_venv() -> None:
    """Create and sync the project-level virtual environment."""
    logger.info("=== Setting up project venv ===")
    run_cmd(["uv", "venv"], PROJECT_ROOT, "Project venv create")
    run_cmd(["uv", "sync"], PROJECT_ROOT, "Project venv sync")


def setup_agent_venvs() -> None:
    """Create and sync virtual environments for all 5 agents."""
    agents_dir = PROJECT_ROOT / "agents"
    agent_names = [
        "coordinator",
        "conflict_detector",
        "weather_analyst",
        "ground_ops",
        "emergency_response",
    ]

    for agent_name in agent_names:
        agent_dir = agents_dir / agent_name
        if not agent_dir.exists():
            logger.warning("Agent directory not found: %s — skipping", agent_dir)
            continue

        logger.info("=== Setting up agent: %s ===", agent_name)
        run_cmd(["uv", "venv"], agent_dir, f"Agent {agent_name} venv create")
        run_cmd(["uv", "sync"], agent_dir, f"Agent {agent_name} venv sync")


def setup_frontend() -> None:
    """Install frontend npm dependencies."""
    frontend_dir = PROJECT_ROOT / "frontend"
    if not frontend_dir.exists():
        logger.warning("Frontend directory not found — skipping")
        return

    logger.info("=== Setting up frontend ===")
    run_cmd(["npm", "install"], frontend_dir, "Frontend npm install")


def main() -> None:
    """Run all setup steps."""
    logger.info("ATC Guardian Environment Setup")
    logger.info("Project root: %s", PROJECT_ROOT)

    setup_project_venv()
    setup_agent_venvs()
    setup_frontend()

    logger.info("=== Setup complete ===")
    logger.info("To start the system, run: uv run python scripts/start_all.py")


if __name__ == "__main__":
    main()
