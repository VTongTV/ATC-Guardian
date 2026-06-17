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

Import isolation
~~~~~~~~~~~~~~~~
Each agent has a ``prompts.py`` with its own system prompt.  When all
agent directories are on ``sys.path`` simultaneously, Python finds the
wrong ``prompts.py`` first.  To avoid this, each agent's directory is
added to ``sys.path`` **only during its own adapter import**, then
removed immediately after so the next agent gets a clean path.
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
# Agent registry
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


def _get_project_root() -> Path:
    """Return the project root (4 levels up from runner.py)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _build_agent(agent_entry: dict[str, str]):
    """Build a single Band Agent from the registry entry.

    Temporarily adds the agent's subdirectory to ``sys.path`` so that
    its ``from prompts import ...`` resolves correctly, then removes it
    before the next agent runs.
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

    # --- Isolated import path for this agent's prompts module ---
    project_root = _get_project_root()
    agent_dir = str(project_root / "agents" / name)
    project_str = str(project_root)

    # Ensure project root is on sys.path (for shared.* imports)
    if project_str not in sys.path:
        sys.path.insert(0, project_str)

    # Set AIMLAPI_CALLER_TAG so key rotation picks a different key per agent
    old_caller_tag = os.environ.get("AIMLAPI_CALLER_TAG")
    os.environ["AIMLAPI_CALLER_TAG"] = name

    # Temporarily add THIS agent's directory at position 0
    sys.path.insert(0, agent_dir)
    try:
        # Force fresh import so this agent's prompts module is found.
        # Remove any cached modules from previous agents to avoid
        # "cannot import name 'X' from 'prompts'" cross-contamination.
        mod_name = agent_entry["adapter_module"]
        # e.g. "agents.coordinator.agent" → remove agents.coordinator.prompts
        parts = mod_name.rsplit(".", 1)  # ["agents.coordinator", "agent"]
        pkg_prefix = parts[0]  # "agents.coordinator"
        stale_keys = [
            k for k in list(sys.modules)
            if k == pkg_prefix or k.startswith(pkg_prefix + ".")
        ]
        for k in stale_keys:
            del sys.modules[k]
        # Also remove the bare "prompts" module cached by the previous
        # agent's `from prompts import X`.  Without this, the next agent
        # finds the wrong prompts.py in sys.modules.
        sys.modules.pop("prompts", None)

        mod = importlib.import_module(mod_name)
        builder = getattr(mod, agent_entry["adapter_func"])
        adapter = builder()
    finally:
        # Remove the agent directory from sys.path
        if agent_dir in sys.path:
            sys.path.remove(agent_dir)
        # Restore AIMLAPI_CALLER_TAG
        if old_caller_tag is None:
            os.environ.pop("AIMLAPI_CALLER_TAG", None)
        else:
            os.environ["AIMLAPI_CALLER_TAG"] = old_caller_tag

    # Create the Band Agent
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
