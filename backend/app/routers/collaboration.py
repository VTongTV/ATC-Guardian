"""Collaboration router — exposes the agent team graph for the UI.

Returns the static agent roster (nodes with framework metadata) plus
live @mention edges derived from the audit log, so the frontend can
render a node-graph that visualises the cross-framework collaboration
the Band of Agents rubric rewards.
"""

from __future__ import annotations

import json
import logging
from collections import Counter

from fastapi import APIRouter, HTTPException

from backend.app.services.audit_service import AuditService
from shared.agent_roster import AGENT_ROSTER

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collaboration", tags=["collaboration"])

# Injected by main.py on application startup
_audit_service: AuditService | None = None


def set_audit_service(service: AuditService) -> None:
    """Register the audit service for edge derivation.

    Args:
        service: The active AuditService instance.
    """
    global _audit_service
    _audit_service = service


def _get_service() -> AuditService:
    """Retrieve the audit service or raise 503.

    Returns:
        The active AuditService.

    Raises:
        HTTPException: 503 if not initialised.
    """
    if _audit_service is None:
        raise HTTPException(status_code=503, detail="Audit service not initialized")
    return _audit_service


@router.get("/graph")
async def collaboration_graph(limit: int = 200) -> dict:
    """Return the agent team graph (nodes + @mention edges).

    Args:
        limit: Number of recent audit events to scan for edges.

    Returns:
        Dict with ``nodes`` (agent roster with framework metadata),
        ``edges`` (sender -> mentioned target counts), and
        ``frameworks`` (per-framework agent counts for the pitch).
    """
    service = _get_service()
    events = await service.get_events(limit=limit)

    edge_counter: Counter[tuple[str, str]] = Counter()
    for evt in events:
        if not evt.metadata_json:
            continue
        try:
            metadata = json.loads(evt.metadata_json)
        except (json.JSONDecodeError, TypeError):
            continue
        mentions = metadata.get("mentions") or []
        for target in mentions:
            # Mentions may be a list of strings OR a list of dicts
            # (e.g. {"handle": "conflict-detector", "id": "..."}).
            # Normalise to a string for use as a Counter key.
            if isinstance(target, dict):
                target = target.get("handle") or target.get("name") or str(target)
            if not isinstance(target, str):
                continue
            edge_counter[(evt.agent_name, target)] += 1

    edges = [
        {"source": src, "target": tgt, "weight": count}
        for (src, tgt), count in edge_counter.most_common()
    ]

    nodes = [a.model_dump() for a in AGENT_ROSTER]
    frameworks: dict[str, int] = {}
    for agent in AGENT_ROSTER:
        frameworks[agent.framework] = frameworks.get(agent.framework, 0) + 1

    return {"nodes": nodes, "edges": edges, "frameworks": frameworks}


@router.get("/partner-routing")
async def partner_routing() -> dict:
    """Return the documented per-agent AI/ML API model assignments.

    Exposes the rationale for each agent's recommended AI/ML API model
    (one partner, right model per job) so prize judges can review the
    technology choices.

    Returns:
        Dict mapping each agent to its recommended provider, model,
        rationale, and prize category.
    """
    from shared.partner_routing import PARTNER_MODEL_ASSIGNMENTS

    return {
        agent: {
            "provider": a.provider,
            "model": a.model,
            "rationale": a.rationale,
            "prize_category": a.prize_category,
        }
        for agent, a in (
            (a.agent_name, a) for a in PARTNER_MODEL_ASSIGNMENTS
        )
    }
