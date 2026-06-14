"""Tests for the agent roster and collaboration graph endpoint.

Verifies the static roster covers all six agents, the framework
diversity summary is correct, and the /collaboration/graph endpoint
derives @mention edges from the audit log.
"""

import asyncio
import json

from fastapi.testclient import TestClient

from shared.agent_roster import (
    AGENT_BY_NAME,
    AGENT_ROSTER,
    framework_diversity_summary,
)


def _run(coro):
    """Run a coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Static roster
# ---------------------------------------------------------------------------


def test_roster_has_six_agents() -> None:
    """The roster covers all six ATC Guardian agents."""
    names = {a.name for a in AGENT_ROSTER}
    assert names == {
        "coordinator",
        "conflict-detector",
        "weather-analyst",
        "safety-reviewer",
        "ground-ops",
        "emergency-response",
    }


def test_every_agent_has_framework_metadata() -> None:
    """Each agent declares a framework and a rationale note."""
    for agent in AGENT_ROSTER:
        assert agent.framework, f"{agent.name} missing framework"
        assert agent.framework_note, f"{agent.name} missing framework_note"
        assert agent.role, f"{agent.name} missing role"
        assert agent.colour.startswith("#"), f"{agent.name} bad colour"


def test_roster_showcases_three_frameworks() -> None:
    """The cross-framework diversity (the competitive edge) is present."""
    summary = framework_diversity_summary()
    assert "LangGraph" in summary
    assert "Pydantic AI" in summary
    assert "CrewAI" in summary
    assert len(summary) >= 3


def test_agent_by_name_lookup_works() -> None:
    """AGENT_BY_NAME lets callers fetch a single descriptor."""
    coord = AGENT_BY_NAME["coordinator"]
    assert coord.framework == "LangGraph"
    reviewer = AGENT_BY_NAME["safety-reviewer"]
    assert reviewer.framework == "Pydantic AI"


# ---------------------------------------------------------------------------
# /collaboration/graph endpoint
# ---------------------------------------------------------------------------


class _FakeAudit:
    """Fake audit service returning canned events with mentions metadata."""

    def __init__(self, events: list) -> None:
        self._events = events

    async def get_events(self, **kwargs):
        return self._events


def test_collaboration_graph_returns_roster_and_edges() -> None:
    """The graph endpoint returns nodes + derived edges + framework counts."""
    from fastapi import FastAPI

    from backend.app.routers import collaboration as collab_router

    canned = [
        type(
            "Evt",
            (),
            {
                "agent_name": "conflict-detector",
                "metadata_json": json.dumps({"mentions": ["safety-reviewer"]}),
            },
        )(),
        type(
            "Evt",
            (),
            {
                "agent_name": "safety-reviewer",
                "metadata_json": json.dumps({"mentions": ["coordinator"]}),
            },
        )(),
        type(
            "Evt",
            (),
            {
                "agent_name": "conflict-detector",
                "metadata_json": json.dumps({"mentions": ["safety-reviewer"]}),
            },
        )(),
    ]

    app = FastAPI()
    collab_router.set_audit_service(_FakeAudit(canned))  # type: ignore[arg-type]
    app.include_router(collab_router.router)
    client = TestClient(app)

    response = client.get("/collaboration/graph")
    assert response.status_code == 200
    body = response.json()

    assert len(body["nodes"]) == 6
    assert "frameworks" in body
    # The conflict-detector -> safety-reviewer edge counted twice (weight 2)
    edges = {(e["source"], e["target"]): e["weight"] for e in body["edges"]}
    assert edges.get(("conflict-detector", "safety-reviewer")) == 2
    assert edges.get(("safety-reviewer", "coordinator")) == 1


def test_collaboration_graph_handles_missing_metadata() -> None:
    """Events without mentions metadata don't break the graph."""
    from fastapi import FastAPI

    from backend.app.routers import collaboration as collab_router

    canned = [
        type("Evt", (), {"agent_name": "x", "metadata_json": None})(),
    ]
    app = FastAPI()
    collab_router.set_audit_service(_FakeAudit(canned))  # type: ignore[arg-type]
    app.include_router(collab_router.router)
    client = TestClient(app)

    response = client.get("/collaboration/graph")
    assert response.status_code == 200
    assert response.json()["edges"] == []
