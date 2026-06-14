"""Audit service — persistent SQLite event log for ATC Guardian.

Provides an async wrapper around a SQLite database that stores every
agent decision, reasoning step, and communication event for regulatory
compliance and front-end audit timeline display.
"""

import json
import logging
from pathlib import Path

import aiosqlite
from pydantic import BaseModel

logger = logging.getLogger(__name__)

AUDIT_DEFAULT_PAGE_SIZE = 100

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT,
    target_agent TEXT,
    scenario_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_CREATE_INDEX_TIMESTAMP = (
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);"
)
_CREATE_INDEX_AGENT = (
    "CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_events(agent_name);"
)
_CREATE_INDEX_TYPE = (
    "CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type);"
)


class AuditEvent(BaseModel):
    """Pydantic model for a single audit event."""

    id: int
    timestamp: str
    agent_name: str
    event_type: str
    content: str
    metadata_json: str | None
    target_agent: str | None
    scenario_id: str | None


class AuditService:
    """Async SQLite-backed audit log service.

    Every method is non-blocking and safe to call from an async context.
    The database file and its parent directory are created automatically
    on the first call to :meth:`initialize`.
    """

    def __init__(self, db_path: str = "data/audit.db") -> None:
        """Initialize with path to SQLite database file.

        Args:
            db_path: Filesystem path for the SQLite database.
        """
        self._db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and table if they don't exist.

        Must be called once during application startup before any
        other method is invoked.

        Raises:
            RuntimeError: If the database connection cannot be established.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(
            _CREATE_TABLE_SQL + _CREATE_INDEX_TIMESTAMP + _CREATE_INDEX_AGENT + _CREATE_INDEX_TYPE
        )
        await self._db.commit()
        logger.info("Audit database initialised at %s", self._db_path)

    async def log_event(
        self,
        agent_name: str,
        event_type: str,
        content: str,
        metadata: dict | None = None,
        target_agent: str | None = None,
        scenario_id: str | None = None,
    ) -> int:
        """Insert a single audit event.

        Args:
            agent_name: Name of the agent that produced the event.
            event_type: Category of the event (e.g. "thought", "task",
                "tool_call", "tool_result", "message", "error",
                "conflict_alert", "weather_advisory", "emergency_declaration").
            content: Human-readable text describing the event.
            metadata: Optional dictionary serialised as a JSON blob.
            target_agent: Name of the intended recipient, if directed.
            scenario_id: Active scenario identifier at the time of the event.

        Returns:
            The auto-incremented row ID of the inserted event.

        Raises:
            RuntimeError: If the service has not been initialised.
        """
        self._ensure_initialized()
        assert self._db is not None  # for type checker

        metadata_json = json.dumps(metadata) if metadata is not None else None
        import datetime as _dt

        timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()

        cursor = await self._db.execute(
            """
            INSERT INTO audit_events (timestamp, agent_name, event_type, content, metadata_json, target_agent, scenario_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, agent_name, event_type, content, metadata_json, target_agent, scenario_id),
        )
        await self._db.commit()
        row_id = cursor.lastrowid
        assert row_id is not None
        logger.debug("Audit event logged (id=%s) by %s [%s]", row_id, agent_name, event_type)
        return row_id

    async def get_events(
        self,
        limit: int = AUDIT_DEFAULT_PAGE_SIZE,
        offset: int = 0,
        agent_name: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
    ) -> list[AuditEvent]:
        """Query audit events with optional filters.

        Args:
            limit: Maximum number of events to return.
            offset: Number of events to skip for pagination.
            agent_name: If provided, only return events from this agent.
            event_type: If provided, only return events of this type.
            since: If provided, only return events with timestamps on or
                after this ISO 8601 string.

        Returns:
            A list of AuditEvent records matching the filters, ordered
            by timestamp descending.

        Raises:
            RuntimeError: If the service has not been initialised.
        """
        self._ensure_initialized()
        assert self._db is not None

        conditions: list[str] = []
        params: list[str | int] = []

        if agent_name is not None:
            conditions.append("agent_name = ?")
            params.append(agent_name)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(since)

        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT id, timestamp, agent_name, event_type, content, metadata_json, target_agent, scenario_id
            FROM audit_events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """  # noqa: S608 — dynamic WHERE built from whitelisted column names only
        params.extend([limit, offset])

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return [
            AuditEvent(
                id=row[0],
                timestamp=row[1],
                agent_name=row[2],
                event_type=row[3],
                content=row[4],
                metadata_json=row[5],
                target_agent=row[6],
                scenario_id=row[7],
            )
            for row in rows
        ]

    async def get_event_by_id(self, event_id: int) -> AuditEvent | None:
        """Get a single audit event by its primary key.

        Args:
            event_id: The row ID of the event to retrieve.

        Returns:
            The matching AuditEvent, or None if no event with that ID exists.

        Raises:
            RuntimeError: If the service has not been initialised.
        """
        self._ensure_initialized()
        assert self._db is not None

        async with self._db.execute(
            """
            SELECT id, timestamp, agent_name, event_type, content, metadata_json, target_agent, scenario_id
            FROM audit_events
            WHERE id = ?
            """,
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        return AuditEvent(
            id=row[0],
            timestamp=row[1],
            agent_name=row[2],
            event_type=row[3],
            content=row[4],
            metadata_json=row[5],
            target_agent=row[6],
            scenario_id=row[7],
        )

    async def get_events_by_scenario(
        self, scenario_id: str, limit: int = AUDIT_DEFAULT_PAGE_SIZE
    ) -> list[AuditEvent]:
        """Get all events for a specific scenario.

        Args:
            scenario_id: The scenario identifier to filter on.
            limit: Maximum number of events to return.

        Returns:
            A list of AuditEvent records for the given scenario, ordered
            by timestamp ascending.

        Raises:
            RuntimeError: If the service has not been initialised.
        """
        self._ensure_initialized()
        assert self._db is not None

        async with self._db.execute(
            """
            SELECT id, timestamp, agent_name, event_type, content, metadata_json, target_agent, scenario_id
            FROM audit_events
            WHERE scenario_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (scenario_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            AuditEvent(
                id=row[0],
                timestamp=row[1],
                agent_name=row[2],
                event_type=row[3],
                content=row[4],
                metadata_json=row[5],
                target_agent=row[6],
                scenario_id=row[7],
            )
            for row in rows
        ]

    async def close(self) -> None:
        """Close the database connection.

        Should be called during application shutdown.
        """
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.info("Audit database connection closed")

    def _ensure_initialized(self) -> None:
        """Raise if initialize() has not been called yet.

        Raises:
            RuntimeError: If the database connection is not active.
        """
        if self._db is None:
            raise RuntimeError(
                "AuditService has not been initialised. Call initialize() first."
            )
