"""Tests for the partner model routing configuration.

Verifies every agent has a documented AI/ML API model assignment, the
rationale is non-trivial, and the per-agent models match the confirmed
routing decision (one AI/ML API key, right model per job).
"""

from backend.app.routers import collaboration as collab_router
from shared.partner_routing import (
    PARTNER_MODEL_ASSIGNMENTS,
    assignments_by_provider,
    env_overrides_for_active_provider,
)

#: Confirmed per-agent AI/ML API model assignments.
EXPECTED_MODELS: dict[str, str] = {
    "safety-reviewer": "zhipu/glm-5.1",
    "conflict-detector": "deepseek/deepseek-v4-pro",
    "emergency-response": "zhipu/glm-5.1",
    "coordinator": "moonshot/kimi-k2-6",
    "weather-analyst": "deepseek/deepseek-v4-pro",
    "ground-ops": "deepseek/deepseek-v4-flash",
}


def test_every_agent_has_partner_assignment() -> None:
    """All six agents have a documented AI/ML API model recommendation."""
    assigned = {a.agent_name for a in PARTNER_MODEL_ASSIGNMENTS}
    assert assigned == set(EXPECTED_MODELS)


def test_every_assignment_has_substantive_rationale() -> None:
    """Each rationale is a real paragraph, not a stub."""
    for a in PARTNER_MODEL_ASSIGNMENTS:
        assert len(a.rationale) > 60, f"{a.agent_name} rationale too short"
        assert a.model, f"{a.agent_name} missing model"
        assert a.prize_category, f"{a.agent_name} missing prize category"


def test_all_assignments_use_aimlapi() -> None:
    """Every assignment routes through AI/ML API (single partner)."""
    providers = {a.provider for a in PARTNER_MODEL_ASSIGNMENTS}
    assert providers == {"aimlapi"}


def test_assignments_match_confirmed_models() -> None:
    """Each agent is pinned to its confirmed AI/ML API model."""
    actual = {a.agent_name: a.model for a in PARTNER_MODEL_ASSIGNMENTS}
    assert actual == EXPECTED_MODELS


def test_assignments_by_provider_filters_correctly() -> None:
    """assignments_by_provider returns only matching assignments."""
    aimlapi = assignments_by_provider("aimlapi")
    assert all(a.provider == "aimlapi" for a in aimlapi)
    assert len(aimlapi) == len(PARTNER_MODEL_ASSIGNMENTS)
    # An unknown provider returns an empty list, not an error.
    assert assignments_by_provider("featherless") == []


def test_env_overrides_map_is_well_formed() -> None:
    """env_overrides_for_active_provider produces *_MODEL env keys."""
    overrides = env_overrides_for_active_provider("aimlapi")
    assert all(k.endswith("_MODEL") for k in overrides)
    assert all(isinstance(v, str) and v for v in overrides.values())
    assert overrides["CONFLICT_DETECTOR_MODEL"] == "deepseek/deepseek-v4-pro"
    assert overrides["SAFETY_REVIEWER_MODEL"] == "zhipu/glm-5.1"


def test_structured_output_agents_use_glm_5_1() -> None:
    """Highest-stakes structured-output agents route to GLM-5.1."""
    glm_agents = {
        a.agent_name
        for a in PARTNER_MODEL_ASSIGNMENTS
        if a.model == "zhipu/glm-5.1"
    }
    assert "safety-reviewer" in glm_agents
    assert "emergency-response" in glm_agents


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
        assert info["provider"] == "aimlapi"
        assert info["model"] == EXPECTED_MODELS[agent]
        assert "rationale" in info
        assert info["prize_category"] == "Best Use of AI/ML API"
