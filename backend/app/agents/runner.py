"""Embedded agent runner — launches all 6 Band agents as asyncio tasks.

When ``BAND_MODE=live`` and all agent credentials are configured, this
module builds each agent's adapter and Band ``Agent`` instance, then
runs them all as background ``asyncio.Task`` objects inside the backend
process.  This eliminates the need for separate subprocesses on Render
where launching 7+ OS processes from a single web service is fragile.

**Connection lifecycle (the primary token-burn gate):**
Agents are NOT connected at backend startup.  They are launched lazily
by ``main.py`` the first time ``/demo/start`` is hit (via
``launch_agents()``), and fully disconnected on ``/demo/stop`` (via
``shutdown_agents_async()``).  Disconnecting cancels the agent tasks,
which triggers ``agent.run()``'s ``finally`` → ``agent.stop()``, tearing
down every WebSocket.  A disconnected agent reads zero messages from the
shared Band room and consumes zero tokens.  This is the fix for a
runaway token-burn bug where all 6 agents connected at backend startup,
replayed the room's message backlog, and @mention-cascaded each other
(~1–2M tokens/min before any demo was started).

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

Demo-active guard & rate limiting (defense-in-depth)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Even while connected, agents are wrapped so they only process Band
messages when the demo is active.  Each agent is also rate-limited to 3
LLM calls per rolling 60-second window to prevent cascading @mention
loops from burning tokens.  These are secondary guards — the primary
gate is the connection lifecycle (no connected agent = no messages at
all).  STOP directive messages are no longer posted on demo stop
(post_stop_directives is kept for potential manual use but not called
by the demo lifecycle).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo-active flag & per-agent rate limiter
# ---------------------------------------------------------------------------

_demo_active: bool = False
"""Global flag — agents only process messages when True."""

_AGENT_RATE_LIMIT: int = 3
"""Maximum LLM responses per agent per rolling window."""

_AGENT_RATE_WINDOW_SECONDS: float = 60.0
"""Duration of the rolling rate-limit window in seconds."""

_agent_timestamps: dict[str, list[float]] = defaultdict(list)
"""Per-agent list of response timestamps for rate limiting."""


def set_demo_active(active: bool) -> None:
    """Set whether the demo is active and agents should process messages.

    Called from main.py when /demo/start or /demo/stop is hit.
    When switching to inactive, also resets per-agent rate-limit counters
    so the next demo starts with a clean slate.

    Args:
        active: True to allow agents to process messages, False to block.
    """
    global _demo_active
    _demo_active = active
    if not active:
        _agent_timestamps.clear()
        logger.info("Demo deactivated — agents will drop all incoming messages")
    else:
        logger.info("Demo activated — agents will process messages")


def is_demo_active() -> bool:
    """Check if the demo is currently active."""
    return _demo_active


def _check_agent_rate_limit(agent_name: str) -> bool:
    """Check whether an agent is within its per-minute message limit.

    Args:
        agent_name: The agent identity being rate-limited.

    Returns:
        True if the agent is allowed to respond, False if it should drop.
    """
    now = time.monotonic()
    timestamps = _agent_timestamps[agent_name]
    cutoff = now - _AGENT_RATE_WINDOW_SECONDS
    _agent_timestamps[agent_name] = [t for t in timestamps if t > cutoff]
    timestamps = _agent_timestamps[agent_name]

    if len(timestamps) >= _AGENT_RATE_LIMIT:
        logger.warning(
            "Agent rate limit hit for %s: %d/%d in last %.0fs — dropping",
            agent_name,
            len(timestamps),
            _AGENT_RATE_LIMIT,
            _AGENT_RATE_WINDOW_SECONDS,
        )
        return False

    timestamps.append(now)
    return True


# ---------------------------------------------------------------------------
# STOP directive messages
# ---------------------------------------------------------------------------

_STOP_DIRECTIVE = (
    "[SYSTEM DIRECTIVE — STOP] Demo has been stopped. "
    "Cease all processing, thinking, and responding immediately. "
    "Do NOT reply, @mention, or generate any output. "
    "Drop this message and all subsequent messages until you receive "
    "a new dispatch from @system-ingest. This is a hard stop order."
)

_STOP_DIRECTIVE_REPEAT = (
    "[SYSTEM DIRECTIVE — STOP — CONFIRMATION] "
    "This is a repeat STOP order. Demo is OFF. "
    "All agents must immediately halt all LLM processing. "
    "Do not respond. Do not think. Do not @mention anyone. "
    "Silence all output until @system-ingest sends a new dispatch."
)


async def post_stop_directives(band_client: Any) -> None:
    """Post 2 STOP directive messages to the Band room for each agent.

    These messages appear as @mentions to every agent in the room,
    instructing them to immediately cease all processing. Two are sent
    in sequence to ensure agents that are mid-processing see at least one.

    Args:
        band_client: The BandClient (sim or live) to post messages through.
    """
    from shared.band_client import BandOutboundMessage

    all_agent_handles = [
        "conflict-detector",
        "safety-reviewer",
        "weather-analyst",
        "coordinator",
        "emergency-response",
        "ground-ops",
    ]

    for i, (content, label) in enumerate([
        (_STOP_DIRECTIVE, "STOP directive 1"),
        (_STOP_DIRECTIVE_REPEAT, "STOP directive 2"),
    ]):
        msg = BandOutboundMessage(
            sender="system-ingest",
            content=(
                f"@conflict-detector @safety-reviewer @weather-analyst "
                f"@coordinator @emergency-response @ground-ops {content}"
            ),
            mentions=all_agent_handles,
            metadata={
                "kind": "system-stop",
                "directive": label,
            },
            correlation_id=f"stop-directive-{i + 1}",
        )
        try:
            await band_client.post_message(msg)
            logger.info("Posted %s to Band room", label)
        except Exception:
            logger.exception("Failed to post %s", label)
        # Brief pause between the two directives
        if i == 0:
            await asyncio.sleep(0.5)


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

    # --- Wrap _on_execute with demo-active guard + rate limiter ---
    _original_on_execute = agent._on_execute

    async def _guarded_on_execute(ctx, event):
        """Only process events when demo is active + within rate limit.

        Also detects AI/ML API quota errors and triggers automatic
        fallback to OpenRouter by marking the circuit breaker and
        scheduling an agent rebuild.
        """
        if not _demo_active:
            logger.info(
                "Agent '%s' dropping message — demo not active", name
            )
            return
        if not _check_agent_rate_limit(name):
            logger.info(
                "Agent '%s' dropping message — rate limited", name
            )
            return
        try:
            await _original_on_execute(ctx, event)
        except Exception as exc:
            # Check if this is a quota/credit error from AI/ML API
            from shared.llm_config import is_quota_error, is_aimlapi_exhausted

            status_code = getattr(exc, "status_code", None)
            if status_code is None:
                # httpx.HTTPStatusError / openai.APIStatusError
                resp = getattr(exc, "response", None)
                if resp is not None:
                    status_code = getattr(resp, "status_code", None)
            error_message = str(exc)

            if not is_aimlapi_exhausted() and is_quota_error(status_code, error_message):
                from shared.llm_config import mark_aimlapi_exhausted
                mark_aimlapi_exhausted()
                logger.warning(
                    "Agent '%s' hit AI/ML API quota limit (status=%s). "
                    "Marking exhausted — will fall back to OpenRouter on next rebuild.",
                    name,
                    status_code,
                )
            # Re-raise so the adapter/framework can handle it
            raise

    agent._on_execute = _guarded_on_execute

    logger.info("Built agent: %s (id=%s..., demo-guard + rate-limit active)", name, agent_id[:8])
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
            # Build in a worker thread so the synchronous heavy imports
            # (LangChain/CrewAI/litellm/PydanticAI cold-import + adapter
            # construction) do NOT starve the event loop. Without this, the
            # ~20-30s of blocking work during /demo/start freezes the whole
            # process — including Render's health-check probe to /healthz,
            # which then fails the instance (5s timeout) and 503s all traffic.
            _, band_agent = await asyncio.to_thread(_build_agent, entry)
            # Yield between agents so health checks and other requests keep
            # being serviced throughout the launch sequence.
            await asyncio.sleep(0)
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
    """Cancel all agent tasks gracefully (synchronous)."""
    for task in tasks:
        if not task.done():
            task.cancel()
    logger.info("Cancelled %d agent tasks", len(tasks))


async def shutdown_agents_async(tasks: list[asyncio.Task]) -> None:
    """Cancel all agent tasks and wait for them to finish.

    Cancelling the tasks causes ``agent.run()``'s ``finally`` block to
    call ``agent.stop()``, which tears down every execution context and
    closes the WebSocket.  We await each task so the SDK cleanup runs
    to completion before we return — guarantees zero lingering connections.

    Args:
        tasks: List of asyncio.Task objects returned by launch_agents().
    """
    for task in tasks:
        if not task.done():
            task.cancel()
    # Wait for all tasks to finish (CancelledError is expected).
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for task, result in zip(tasks, results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            logger.warning(
                "Agent task %s exited with error: %s",
                task.get_name(),
                result,
            )
    logger.info("Shutdown complete for %d agent tasks", len(tasks))


async def rebuild_agents_with_fallback(
    current_tasks: list[asyncio.Task],
) -> tuple[list[asyncio.Task], list[str]]:
    """Shut down current agents and rebuild them with fallback credentials.

    Called when AI/ML API credits are exhausted.  Shuts down all running
    agent tasks, marks AI/ML API as exhausted in the circuit breaker, and
    relaunches all agents — which will now resolve to OpenRouter
    credentials via :func:`resolve_llm_config`.

    Args:
        current_tasks: The list of currently running agent tasks to replace.

    Returns:
        Tuple of (new_tasks, errors), same as :func:`launch_agents`.
    """
    from shared.llm_config import mark_aimlapi_exhausted, is_aimlapi_exhausted

    if not is_aimlapi_exhausted():
        mark_aimlapi_exhausted()

    logger.info(
        "Rebuilding agents with OpenRouter fallback "
        "(shutting down %d current tasks)...",
        len(current_tasks),
    )

    # Shut down existing agents cleanly
    await shutdown_agents_async(current_tasks)

    # Relaunch — resolve_llm_config will now return OpenRouter creds
    new_tasks, errors = await launch_agents()

    logger.info(
        "Agent rebuild complete: %d running, %d failed (fallback provider active)",
        len(new_tasks),
        len(errors),
    )
    return new_tasks, errors
