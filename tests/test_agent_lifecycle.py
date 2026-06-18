"""Unit tests for the agent lifecycle in backend/app/agents/runner.py.

Covers the demo-active flag, per-agent rate limiter, and
shutdown_agents_async — the three mechanisms that prevent runaway
token burn. No network, no Band credentials, no LLM calls.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from backend.app.agents.runner import (
    _AGENT_RATE_LIMIT,
    _AGENT_RATE_WINDOW_SECONDS,
    _agent_timestamps,
    _check_agent_rate_limit,
    is_demo_active,
    set_demo_active,
    shutdown_agents,
    shutdown_agents_async,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset the module-level demo flag and rate-limit counters between tests."""
    set_demo_active(False)
    _agent_timestamps.clear()
    yield
    set_demo_active(False)
    _agent_timestamps.clear()


# ---------------------------------------------------------------------------
# Demo-active flag
# ---------------------------------------------------------------------------


class TestDemoActiveFlag:
    """Tests for set_demo_active / is_demo_active."""

    def test_default_is_inactive(self) -> None:
        """Before any call, the demo is inactive."""
        assert is_demo_active() is False

    def test_set_active(self) -> None:
        """set_demo_active(True) makes is_demo_active() return True."""
        set_demo_active(True)
        assert is_demo_active() is True

    def test_set_inactive(self) -> None:
        """set_demo_active(False) makes is_demo_active() return False."""
        set_demo_active(True)
        set_demo_active(False)
        assert is_demo_active() is False

    def test_deactivating_clears_rate_limits(self) -> None:
        """Switching to inactive resets per-agent rate-limit counters."""
        _check_agent_rate_limit("agent-a")
        _check_agent_rate_limit("agent-b")
        assert len(_agent_timestamps) == 2

        set_demo_active(False)
        assert len(_agent_timestamps) == 0

    def test_activating_does_not_clear_rate_limits(self) -> None:
        """Switching to active preserves existing rate-limit counters."""
        _check_agent_rate_limit("agent-a")
        assert len(_agent_timestamps) == 1

        set_demo_active(True)
        assert len(_agent_timestamps) == 1


# ---------------------------------------------------------------------------
# Per-agent rate limiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Tests for _check_agent_rate_limit."""

    def test_allows_up_to_limit(self) -> None:
        """The first _AGENT_RATE_LIMIT calls are allowed."""
        for _ in range(_AGENT_RATE_LIMIT):
            assert _check_agent_rate_limit("agent-a") is True

    def test_blocks_beyond_limit(self) -> None:
        """The call after the limit is blocked."""
        for _ in range(_AGENT_RATE_LIMIT):
            _check_agent_rate_limit("agent-a")
        assert _check_agent_rate_limit("agent-a") is False

    def test_per_agent_independent(self) -> None:
        """Each agent has its own independent rate-limit counter."""
        for _ in range(_AGENT_RATE_LIMIT):
            assert _check_agent_rate_limit("agent-a") is True
        # agent-a is now blocked
        assert _check_agent_rate_limit("agent-a") is False
        # agent-b has a fresh counter
        assert _check_agent_rate_limit("agent-b") is True

    def test_window_expiry_resets_limit(self) -> None:
        """After the rolling window expires, the limit resets."""
        for _ in range(_AGENT_RATE_LIMIT):
            _check_agent_rate_limit("agent-a")
        assert _check_agent_rate_limit("agent-a") is False

        # Fast-forward time past the window.
        with patch("backend.app.agents.runner.time.monotonic", return_value=time.monotonic() + _AGENT_RATE_WINDOW_SECONDS + 1):
            assert _check_agent_rate_limit("agent-a") is True

    def test_partial_window_expiry(self) -> None:
        """Only timestamps within the rolling window count."""
        # First call at t=0
        with patch("backend.app.agents.runner.time.monotonic", return_value=0.0):
            _check_agent_rate_limit("agent-a")

        # Second call near the end of the window — first call is still counted
        with patch("backend.app.agents.runner.time.monotonic", return_value=_AGENT_RATE_WINDOW_SECONDS - 1):
            _check_agent_rate_limit("agent-a")

        # Third call past the window — the t=0 call is expired, only 1 in window
        with patch("backend.app.agents.runner.time.monotonic", return_value=_AGENT_RATE_WINDOW_SECONDS + 1):
            assert _check_agent_rate_limit("agent-a") is True


# ---------------------------------------------------------------------------
# shutdown_agents (sync)
# ---------------------------------------------------------------------------


class TestShutdownAgents:
    """Tests for the synchronous shutdown_agents."""

    def test_cancels_running_tasks(self) -> None:
        """All tasks are cancelled."""

        async def _slow():
            await asyncio.sleep(100)

        loop = asyncio.new_event_loop()
        try:
            tasks = [loop.create_task(_slow(), name=f"agent-{i}") for i in range(3)]
            shutdown_agents(tasks)
            for task in tasks:
                assert task.cancelled() or task.done()
        finally:
            loop.close()

    def test_tolerates_already_done_tasks(self) -> None:
        """Already-completed tasks are skipped without error."""
        loop = asyncio.new_event_loop()
        try:

            async def _noop():
                pass

            done_task = loop.create_task(_noop())
            loop.run_until_complete(done_task)
            assert done_task.done()

            tasks = [done_task]
            shutdown_agents(tasks)  # Should not raise
        finally:
            loop.close()

    def test_tolerates_empty_list(self) -> None:
        """Calling with an empty list is a no-op."""
        shutdown_agents([])


# ---------------------------------------------------------------------------
# shutdown_agents_async
# ---------------------------------------------------------------------------


class TestShutdownAgentsAsync:
    """Tests for the async shutdown_agents_async."""

    @pytest.mark.asyncio
    async def test_cancels_and_awaits_tasks(self) -> None:
        """Tasks are cancelled and the coroutine waits for them to finish."""

        async def _long_run():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass  # Swallow so the task finishes cleanly

        tasks = [asyncio.create_task(_long_run(), name=f"agent-{i}") for i in range(3)]
        await shutdown_agents_async(tasks)

        for task in tasks:
            assert task.done()

    @pytest.mark.asyncio
    async def test_tolerates_empty_list(self) -> None:
        """Calling with an empty list returns without error."""
        await shutdown_agents_async([])

    @pytest.mark.asyncio
    async def test_logs_non_cancelled_errors(self) -> None:
        """A task that raises a non-CancelledError is logged, not raised."""

        async def _failing():
            raise RuntimeError("boom")

        task = asyncio.create_task(_failing(), name="agent-failing")
        # The task raises immediately; gather(return_exceptions=True) catches it
        await shutdown_agents_async([task])
        assert task.done()

    @pytest.mark.asyncio
    async def test_cancelled_error_is_not_logged_as_warning(self) -> None:
        """CancelledError is the expected exit path — not a warning."""

        async def _slow():
            await asyncio.sleep(100)

        task = asyncio.create_task(_slow(), name="agent-slow")
        await shutdown_agents_async([task])
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_mixed_done_and_running(self) -> None:
        """A mix of already-done and still-running tasks is handled."""

        async def _instant():
            pass

        async def _slow():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass

        done_task = asyncio.create_task(_instant(), name="done")
        running_task = asyncio.create_task(_slow(), name="running")

        # Let the instant task complete
        await asyncio.sleep(0)

        await shutdown_agents_async([done_task, running_task])
        assert done_task.done()
        assert running_task.done()


# ---------------------------------------------------------------------------
# launch_agents (without credentials — happy-path smoke test)
# ---------------------------------------------------------------------------


class TestLaunchAgentsWithoutCredentials:
    """Tests for launch_agents when no credentials are configured."""

    @pytest.mark.asyncio
    async def test_returns_empty_tasks_when_credentials_missing(self) -> None:
        """With no env vars set, all agents fail to build; no tasks are created."""
        from backend.app.agents.runner import launch_agents

        # Ensure no agent credentials are in the environment.
        env_backup = {}
        agent_env_keys = [
            "COORDINATOR_AGENT_ID", "COORDINATOR_API_KEY",
            "CONFLICT_DETECTOR_AGENT_ID", "CONFLICT_DETECTOR_API_KEY",
            "WEATHER_ANALYST_AGENT_ID", "WEATHER_ANALYST_API_KEY",
            "SAFETY_REVIEWER_AGENT_ID", "SAFETY_REVIEWER_API_KEY",
            "GROUND_OPS_AGENT_ID", "GROUND_OPS_API_KEY",
            "EMERGENCY_RESPONSE_AGENT_ID", "EMERGENCY_RESPONSE_API_KEY",
        ]
        for key in agent_env_keys:
            env_backup[key] = os.environ.pop(key, None)

        try:
            tasks, errors = await launch_agents()
            assert tasks == []
            assert len(errors) == 6  # All 6 fail with missing credentials
        finally:
            # Restore environment
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val


import os
