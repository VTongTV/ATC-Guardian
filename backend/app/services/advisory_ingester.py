"""Advisory ingester — mirrors Band agent replies into the audit log.

On every simulation tick, polls :class:`BandClient` for new agent
replies (messages produced after the last watermark) and stores each one
in the audit service so the frontend's AgentChatPanel and AuditTimeline
populate with the live agent conversation.

In ``BAND_MODE=sim`` the replies come from the local simulated handlers;
in ``BAND_MODE=live`` they come from real Band agents. Either way the
audit log is the single source of truth the frontend reads.
"""

from __future__ import annotations

import logging

from shared.band_client import BandClient
from backend.app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class AdvisoryIngester:
    """Polls the BandClient for new agent replies and logs them.

    Attributes:
        _client: The BandClient transport.
        _audit: The audit service to write events into.
        _watermark: Last-seen message id; only newer messages are ingested.
    """

    def __init__(self, client: BandClient, audit: AuditService) -> None:
        """Initialise the ingester.

        Args:
            client: The BandClient used to fetch replies.
            audit: The audit service to store events in.
        """
        self._client = client
        self._audit = audit
        self._watermark: str | None = None

    async def ingest_new(self, scenario_id: str | None = None) -> int:
        """Fetch and store any agent replies since the last watermark.

        Args:
            scenario_id: Active scenario id to tag audit events with.

        Returns:
            The number of new messages ingested.
        """
        try:
            messages = await self._client.fetch_replies(since_id=self._watermark)
        except Exception:
            logger.exception("Failed to fetch Band replies")
            return 0

        if not messages:
            return 0

        count = 0
        for msg in messages:
            try:
                await self._audit.log_event(
                    agent_name=msg.sender,
                    event_type=msg.message_type,
                    content=msg.content,
                    metadata={
                        "mentions": msg.mentions,
                        **(msg.metadata or {}),
                    },
                    target_agent=msg.mentions[0] if msg.mentions else None,
                    scenario_id=scenario_id,
                )
                count += 1
            except Exception:
                logger.exception("Failed to log agent reply from %s", msg.sender)

            # Advance the watermark to the highest synthetic counter seen.
            if msg.message_id:
                self._watermark = _max_watermark(self._watermark, msg.message_id)

        if count:
            logger.info("Ingested %d new agent reply/ies", count)
        return count

    def reset(self) -> None:
        """Clear the watermark (e.g. on scenario change)."""
        self._watermark = None


def _max_watermark(current: str | None, candidate: str) -> str:
    """Return whichever of two watermark ids represents the later message.

    Synthetic ids look like ``sim-<n>``; live ids are opaque strings.
    For synthetic ids we compare the numeric suffix. For anything else
    we just take the candidate (Band returns messages newest-first, so
    the first unseen id is the most recent).

    Args:
        current: The current watermark, if any.
        candidate: A candidate message id.

    Returns:
        The watermark to use going forward.
    """

    def _num(value: str | None) -> int:
        try:
            return int(str(value).split("-")[-1])
        except (IndexError, ValueError):
            return -1

    if current is None:
        return candidate
    return candidate if _num(candidate) > _num(current) else current
