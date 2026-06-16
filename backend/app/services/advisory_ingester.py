"""Advisory ingester — mirrors Band agent replies into the audit log.

On every simulation tick, polls :class:`BandClient` for new agent
replies (messages produced after the last watermark) and stores each one
in the audit service so the frontend's AgentChatPanel and AuditTimeline
populate with the live agent conversation.

In ``BAND_MODE=sim`` the replies come from the local simulated handlers;
in ``BAND_MODE=live`` they come from real Band agents. Either way the
audit log is the single source of truth the frontend reads.

When a decision service is wired in, the ingester also promotes
reviewer-approved advisories into pending controller decisions. This is
what populates the CONTROLLER DECISIONS panel in live mode — the sim
agents already create proposals directly, but in live mode the real Band
agents only emit messages, so the ingester performs the same promotion
from the message stream.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shared.advisory import is_promotable_advisory, kind_from_metadata
from shared.band_client import BandClient
from backend.app.services.audit_service import AuditService

if TYPE_CHECKING:
    from backend.app.services.decision_service import DecisionService

logger = logging.getLogger(__name__)


class AdvisoryIngester:
    """Polls the BandClient for new agent replies and logs them.

    Attributes:
        _client: The BandClient transport.
        _audit: The audit service to write events into.
        _decision_service: Optional decision service. When set and
            ``promote_decisions`` is True, reviewed advisories are promoted
            into pending controller decisions so the human-on-the-loop
            panel populates in live mode.
        _promote_decisions: Whether promotion is active (live mode only;
            sim mode creates proposals via the coordinator handler).
        _promoted: Set of message ids already turned into a decision, to
            guard against duplicates across polls.
        _watermark: Last-seen message id; only newer messages are ingested.
    """

    def __init__(
        self,
        client: BandClient,
        audit: AuditService,
        decision_service: "DecisionService | None" = None,
        promote_decisions: bool = False,
    ) -> None:
        """Initialise the ingester.

        Args:
            client: The BandClient used to fetch replies.
            audit: The audit service to store events in.
            decision_service: Optional decision service. When provided
                *and* ``promote_decisions`` is True, reviewer-approved
                advisories are promoted into pending controller decisions.
            promote_decisions: Whether to promote advisories into decisions.
                Only the live-mode ingester should set this — in sim mode
                the coordinator handler already creates proposals directly,
                so promoting here would duplicate them. Defaults to False.
        """
        self._client = client
        self._audit = audit
        self._decision_service = decision_service
        self._promote_decisions = promote_decisions and decision_service is not None
        self._promoted: set[str] = set()
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
            meta = msg.metadata or {}
            try:
                await self._audit.log_event(
                    agent_name=msg.sender,
                    event_type=msg.message_type,
                    content=msg.content,
                    metadata={
                        "mentions": msg.mentions,
                        **meta,
                    },
                    target_agent=msg.mentions[0] if msg.mentions else None,
                    scenario_id=scenario_id,
                )
                count += 1
            except Exception:
                logger.exception("Failed to log agent reply from %s", msg.sender)

            # Promote reviewer-approved advisories into pending controller
            # decisions so the human-on-the-loop panel populates in live
            # mode (where no sim coordinator handler runs). Skipped when no
            # decision service is wired, or for messages already carrying a
            # decision_id / already promoted. Failures never break ingestion.
            await self._maybe_promote_decision(msg, meta, scenario_id)

            # Advance the watermark to the highest synthetic counter seen.
            if msg.message_id:
                self._watermark = _max_watermark(self._watermark, msg.message_id)

        if count:
            logger.info("Ingested %d new agent reply/ies", count)
        return count

    async def _maybe_promote_decision(self, msg, meta: dict, scenario_id: str | None) -> None:
        """Promote a reviewer-approved advisory into a pending decision.

        Only fires when a decision service is wired and the message looks
        like a promotable advisory (see :func:`shared.advisory.is_promotable_advisory`).
        De-duplicates by message id so a message seen across two polls is
        only promoted once. The recommendation defaults to the message
        content's first line when no explicit recommendation is carried.

        Args:
            msg: The Band reply being ingested.
            meta: Its metadata dict.
            scenario_id: Active scenario id to tag the decision with.
        """
        if not self._promote_decisions:
            return
        if msg.message_id and msg.message_id in self._promoted:
            return
        if not is_promotable_advisory(meta):
            return
        try:
            summary = str(meta.get("summary") or msg.content).strip().splitlines()[0]
            verdict = str(meta.get("verdict", "APPROVE")).upper() or "APPROVE"
            recommendation = (
                meta.get("recommendation")
                or meta.get("modification")
                or "see advisory"
            )
            evidence = {
                k: v
                for k, v in meta.items()
                if k in {"cpa", "callsign", "sigmet_id", "phase"}
            }
            await self._decision_service.create_proposal(  # type: ignore[union-attr]
                scenario_id=scenario_id or meta.get("scenario_id") or "SCN-A",
                advisory_kind=kind_from_metadata(meta),
                summary=summary,
                agent_recommendation=str(recommendation),
                reviewer_verdict=verdict,
                evidence=evidence,
            )
            if msg.message_id:
                self._promoted.add(msg.message_id)
            logger.info("Promoted advisory from %s into a pending decision", msg.sender)
        except Exception:
            logger.exception(
                "Failed to promote advisory from %s into a decision", msg.sender
            )

    def reset(self) -> None:
        """Clear the watermark (e.g. on scenario change)."""
        self._watermark = None
        self._promoted.clear()


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
