"""Audit router — REST endpoints for the persistent audit log.

Provides read-only access to the audit event store so the front-end
timeline and compliance dashboards can display agent activity.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.app.services.audit_service import AuditEvent, AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])

# Injected by main.py on application startup
_audit_service: AuditService | None = None


def set_audit_service(service: AuditService) -> None:
    """Register the audit service instance for this router.

    Called once during application lifespan startup.

    Args:
        service: The active AuditService instance.
    """
    global _audit_service
    _audit_service = service


def _get_service() -> AuditService:
    """Retrieve the audit service or raise 503 if not initialized.

    Returns:
        The active AuditService.

    Raises:
        HTTPException: 503 if the service is not yet initialized.
    """
    if _audit_service is None:
        raise HTTPException(status_code=503, detail="Audit service not initialized")
    return _audit_service


@router.get("/events", response_model=list[AuditEvent])
async def list_events(
    limit: int = 100,
    offset: int = 0,
    agent_name: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
) -> list[AuditEvent]:
    """List audit events with optional filters.

    Args:
        limit: Maximum number of events to return (default 100).
        offset: Number of events to skip for pagination (default 0).
        agent_name: Filter by the agent that produced the event.
        event_type: Filter by event category.
        since: Only return events at or after this ISO 8601 timestamp.

    Returns:
        A list of AuditEvent records matching the query.
    """
    service = _get_service()
    return await service.get_events(
        limit=limit,
        offset=offset,
        agent_name=agent_name,
        event_type=event_type,
        since=since,
    )


@router.get("/events/{event_id}", response_model=AuditEvent)
async def get_event(event_id: int) -> AuditEvent:
    """Get a single audit event by ID.

    Args:
        event_id: The primary key of the event.

    Returns:
        The matching AuditEvent.

    Raises:
        HTTPException: 404 if no event with that ID exists.
    """
    service = _get_service()
    event = await service.get_event_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Audit event {event_id} not found")
    return event


@router.get("/events-by-scenario/{scenario_id}", response_model=list[AuditEvent])
async def list_events_by_scenario(
    scenario_id: str, limit: int = 100
) -> list[AuditEvent]:
    """Get all audit events for a specific scenario.

    Args:
        scenario_id: The scenario identifier to filter on.
        limit: Maximum number of events to return (default 100).

    Returns:
        A list of AuditEvent records for the given scenario.
    """
    service = _get_service()
    return await service.get_events_by_scenario(scenario_id=scenario_id, limit=limit)
