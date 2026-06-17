"""Embedded agent runner — launches all 6 Band agents as asyncio tasks.

When ``BAND_MODE=live`` and all agent credentials are configured, this
module builds each agent's adapter and Band ``Agent`` instance, then
runs them all as background ``asyncio.Task`` objects inside the backend
process.  This eliminates the need for separate subprocesses on Render
where launching 7+ OS processes from a single web service is fragile.

Design
------
The 6 agents share a single event loop.  Three agents (conflict_detector,
safety_reviewer, weather_analyst) mutate ``os.environ["OPENAI_API_KEY"]``
and ``os.environ["OPENAI_BASE_URL"]`` at adapter-construction time so
that PydanticAI / CrewAI's internal OpenAI clients pick up the right
provider.  This is safe **as long as adapters are built sequentially** —
each adapter captures the credentials internally at construction time,
so the env-var writes only need to be correct at that instant.

The LangGraph agents (coordinator, ground_ops, emergency_response) pass
credentials directly to ``ChatOpenAI`` and never touch ``os.environ``.

Usage::

    tasks, errors = await launch_agents()
    # tasks: list[asyncio.Task] — cancel them on shutdown
    # errors: list[str] — agent names that failed to build
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent registry — name → (env_id_key, env_api_key, adapter_builder_module,
#                         adapter_builder_func)
# ---------------------------------------------------------------------------

_AGENTS: list[dict[str, str]] = [
    {
        "name": "coordinator",
        "agent_id_env": "COORDINATOR_AGENT_ID",
        "api_key_env": "COORDINATOR_API_KEY",
        "adapter_module": "agents.coordinator.agent",
        "adapter_func": "create_coordinator_adapter",
    },
    {
        "name": "conflict_detector",
        "agent_id_env": "CONFLICT_DETECTOR_AGENT_ID",
        "api_key_env": "CONFLICT_DETECTOR_API_KEY",
        "adapter_module": "agents.conflict_detector.agent",
        "adapter_func": "create_conflict_detector_adapter",
    },
    {
        "name": "weather_analyst",
        "agent_id_env": "WEATHER_ANALYST_AGENT_ID",
        "api_key_env": "WEATHER_ANALYST_API_KEY",
        "adapter_module": "agents.weather_analyst.agent",
        "adapter_func": "create_weather_analyst_adapter",
    },
    {
        "name": "safety_reviewer",
        "agent_id_env": "SAFETY_REVIEWER_AGENT_ID",
        "api_key_env": "SAFETY_REVIEWER_API_KEY",
        "adapter_module": "agents.safety_reviewer.agent",
        "adapter_func": "create_safety_reviewer_adapter",
    },
    {
        "name": "ground_ops",
        "agent_id_env": "GROUND_OPS_AGENT_ID",
        "api_key_env": "GROUND_OPS_API_KEY",
        "adapter_module": "agents.ground_ops.agent",
        "adapter_func": "create_ground_ops_adapter",
    },
    {
        "name": "emergency_response",
        "agent_id_env": "EMERGENCY_RESPONSE_AGENT_ID",
        "api_key_env": "EMERGENCY_RESPONSE_API_KEY",
        "adapter_module": "agents.emergency_response.agent",
        "adapter_func": "create_emergency_response_adapter",
    },
]


def _ensure_agent_import_paths() -> None:
    """Add agent directories to sys.path so their prompts modules resolve."""
    project_root = Path(__file__).resolve().parent.parent.parent
    agents_dir = project_root / "agents"
    for agent_entry in _AGENTS:
        agent_subdir = agents_dir / agent_entry["name"]
        agent_str = str(agent_subdir)
        if agent_str not in sys.path:
            sys.path.insert(0, agent_str)
    # Also ensure project root is importable for shared.*
    project_str = str(project_root)
    if project_str not in sys.path:
        sys.path.insert(0, project_str)


def _build_agent(agent_entry: dict[str, str]):
    """Build a single Band Agent from the registry entry.

    This handles adapter construction (which may set env vars) and
    Band Agent creation.  Must be called sequentially for agents that
    mutate os.environ.

    Returns:
        (name, band_agent) tuple on success.

    Raises:
        ValueError: If required env vars are missing.
        Exception: If adapter construction fails.
    """
    name = agent_entry["name"]
    agent_id = os.environ.get(agent_entry["agent_id_env"], "")
    api_key = os.environ.get(agent_entry["api_key_env"], "")

    if not agent_id or not api_key:
        raise ValueError(
            f"Missing credentials for agent '{name}': "
            f"{agent_entry['agent_id_env']}={'SET' if agent_id else 'MISSING'}, "
            f"{agent_entry['api_key_env']}={'SET' if api_key else 'MISSING'}"
        )

    # Import the adapter builder module
    mod = importlib.import_module(agent_entry["adapter_module"])
    builder = getattr(mod, agent_entry["adapter_func"])
    adapter = builder()

    # Import and create the Band Agent
    from band import Agent

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
    )

    logger.info("Built agent: %s (id=%s...)", name, agent_id[:8])
    return name, agent


async def _run_agent(name: str, agent) -> None:
    """Run a single agent, logging reconnection attempts."""
    logger.info("Agent '%s' connecting to Band...", name)
    try:
        await agent.run()
    except asyncio.CancelledError:
        logger.info("Agent '%s' cancelled (shutdown)", name)
    except Exception:
        logger.exception("Agent '%s' crashed", name)


async def launch_agents() -> tuple[list[asyncio.Task], list[str]]:
    """Build and launch all 6 Band agents as background tasks.

    Returns:
        Tuple of (tasks, errors) where tasks is the list of running
        asyncio.Task objects and errors is a list of agent names that
        failed to build.
    """
    _ensure_agent_import_paths()

    tasks: list[asyncio.Task] = []
    errors: list[str] = []

    logger.info("Building Band agents for embedded launch...")

    for entry in _AGENTS:
        name = entry["name"]
        try:
            _, band_agent = _build_agent(entry)
            task = asyncio.create_task(
                _run_agent(name, band_agent),
                name=f"agent-{name}",
            )
            tasks.append(task)
            logger.info("Agent '%s' launched (task=%s)", name, task.get_name())
        except Exception as exc:
            logger.warning("Failed to build agent '%s': %s", name, exc)
            errors.append(name)

    logger.info(
        "Agent launch complete: %d running, %d failed",
        len(tasks),
        len(errors),
    )
    return tasks, errors


def shutdown_agents(tasks: list[asyncio.Task]) -> None:
    """Cancel all agent tasks gracefully."""
    for task in tasks:
        if not task.done():
            task.cancel()
    logger.info("Cancelled %d agent tasks", len(tasks))
