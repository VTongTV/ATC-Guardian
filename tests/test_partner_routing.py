"""Tests for the partner model routing configuration.

Verifies every agent has a documented partner model assignment, the
rationale is non-trivial, and the prize categories match the partners.
"""

from backend.app.routers import collaboration as collab_router
from shared.partner_routing import (
    PARTNER_MODEL_ASSIGNMENTS,
    assignments_by_provider,
    env_overrides_for_active_provider,
)


def test_every_agent_has_partner_assignment() -> None:
    """All six agents have a documented partner model recommendation."""
    assigned = {a.agent_name for a in PARTNER_MODEL_ASSIGNMENTS}
    assert assigned == {
        "coordinator",
        "conflict-detector",
        "weather-analyst",
        "safety-reviewer",
        "ground-ops",
        "emergency-response",
    }


def test_every_assignment_has_substantive_rationale() -> None:
    """Each rationale is a real paragraph, not a stub."""
    for a in PARTNER_MODEL_ASSIGNMENTS:
        assert len(a.rationale) > 60, f"{a.agent_name} rationale too short"
        assert a.model, f"{a.agent_name} missing model"
        assert a.prize_category, f"{a.agent_name} missing prize category"


def test_both_partners_are_targeted() -> None:
    """Assignments cover both AI/ML API and Featherless prizes."""
    categories = {a.prize_category for a in PARTNER_MODEL_ASSIGNMENTS}
    assert any("AI/ML API" in c for c in categories)
    assert any("Featherless" in c for c in categories)


def test_assignments_by_provider_filters_correctly() -> None:
    """assignments_by_provider returns only matching assignments."""
    aimlapi = assignments_by_provider("aimlapi")
    featherless = assignments_by_provider("featherless")
    assert all(a.provider == "aimlapi" for a in aimlapi)
    assert all(a.provider == "featherless" for a in featherless)
    assert len(aimlapi) >= 1
    assert len(featherless) >= 1


def test_env_overrides_map_is_well_formed() -> None:
    """env_overrides_for_active_provider produces *_MODEL env keys."""
    overrides = env_overrides_for_active_provider("aimlapi")
    assert all(k.endswith("_MODEL") for k in overrides)
    assert all(isinstance(v, str) and v for v in overrides.values())


def test_structured_output_agents_use_aimlapi() -> None:
    """Time-critical structured-output agents route to AI/ML API gpt-4o."""
    aimlapi_agents = {a.agent_name for a in assignments_by_provider("aimlapi")}
    assert "conflict-detector" in aimlapi_agents
    assert "safety-reviewer" in aimlapi_agents
    assert "emergency-response" in aimlapi_agents
    for a in assignments_by_provider("aimlapi"):
        assert a.model == "gpt-4o"


def test_partner_routing_endpoint_returns_all_agents() -> None:
    """GET /collaboration/partner-routing exposes every assignment."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    # partner-routing doesn't need the audit service, but the router
    # module-level _get_service is only used by /graph, so we can mount
    # without it.
    app.include_router(collab_router.router)
    client = TestClient(app)

    response = client.get("/collaboration/partner-routing")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 6
    # Each entry has the required fields
    for agent, info in body.items():
        assert "provider" in info
        assert "model" in info
        assert "rationale" in info
        assert "prize_category" in info
