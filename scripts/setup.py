"""Setup script for ATC Guardian development environment.

Creates the project venv and installs dependencies for:
- Backend + agents (single project venv)
- Frontend (npm install)

Usage:
    uv run python scripts/setup.py
"""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd: list[str], cwd: Path, label: str, *, shell: bool = False) -> None:
    """Execute a command and log the result.

    Args:
        cmd: Command and arguments to execute.
        cwd: Working directory for the command.
        label: Human-readable label for logging.
        shell: Pass shell=True to subprocess (needed on Windows for .cmd tools).

    Raises:
        SystemExit: If the command returns a non-zero exit code.
    """
    logger.info("Running: %s (in %s)", " ".join(cmd), cwd)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=shell)
    if result.returncode != 0:
        logger.error("%s FAILED:\n%s\n%s", label, result.stdout, result.stderr)
        sys.exit(1)
    logger.info("%s OK", label)


def setup_project_venv() -> None:
    """Create and sync the project-level virtual environment."""
    logger.info("=== Setting up project venv ===")
    # Skip `uv venv --clear` here — if invoked via `uv run`, the project venv
    # is the *currently running* Python and cannot be deleted.  `uv run`
    # already creates/syncs the project venv on entry; just ensure deps match.
    run_cmd(["uv", "sync"], PROJECT_ROOT, "Project venv sync")


def setup_frontend() -> None:
    """Install frontend npm dependencies."""
    frontend_dir = PROJECT_ROOT / "frontend"
    if not frontend_dir.exists():
        logger.warning("Frontend directory not found — skipping")
        return

    if shutil.which("npm") is None:
        logger.warning("npm not found on PATH — skipping frontend setup")
        return

    logger.info("=== Setting up frontend ===")
    run_cmd(["npm", "install"], frontend_dir, "Frontend npm install", shell=True)


def main() -> None:
    """Run all setup steps."""
    logger.info("ATC Guardian Environment Setup")
    logger.info("Project root: %s", PROJECT_ROOT)

    setup_project_venv()
    setup_frontend()

    logger.info("=== Setup complete ===")
    logger.info("To start the system, run: uv run python scripts/start_all.py")


if __name__ == "__main__":
    main()
