"""Band poster — drives the agent collaboration loop from the simulation.

Watches each radar snapshot and, when a new conflict / emergency /
weather condition appears, posts a structured @mention into the Band
room (via :class:`BandClient`) so the relevant agent is triggered. In
``BAND_MODE=sim`` this routes to the local simulated handlers; in
``BAND_MODE=live`` it posts to the real Band room.

The poster is de-duplicated: each condition (identified by its advisory
id or callsign+kind) is only dispatched once per active lifetime, so
agents are not spammed on every 4-second tick. This is the event-driven
LLM invocation pattern mandated by AGENTS.md Rule 7.5.

Rate limiting
~~~~~~~~~~~~~
Each agent is allowed a maximum of 3 dispatched messages per rolling
60-second window. This prevents excessive LLM API consumption while
still allowing agents to handle multiple concurrent events. When an
agent hits the limit, the dispatch is logged but silently dropped —
the agent is already busy processing earlier messages.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from shared.band_client import BandClient, BandOutboundMessage
from shared.models import RadarSnapshot

logger = logging.getLogger(__name__)

#: Maximum messages dispatched to a single agent per rolling window.
AGENT_RATE_LIMIT: int = 3

#: Duration of the rolling rate-limit window in seconds.
AGENT_RATE_WINDOW_SECONDS: float = 60.0


class BandPoster:
    """Posts @mentions into Band when new radar conditions appear.

    Attributes:
        _client: The BandClient transport (sim or live).
        _dispatched: Set of condition keys already dispatched, used to
            avoid re-triggering agents for an ongoing condition.
        _agent_timestamps: Per-agent list of dispatch timestamps used
            to enforce the rolling rate limit.
    """

    def __init__(self, client: BandClient) -> None:
        """Initialise the poster with a Band client.

        Args:
            client: The BandClient used to post messages.
        """
        self._client = client
        self._dispatched: set[str] = set()
        self._agent_timestamps: dict[str, list[float]] = defaultdict(list)

    async def process_snapshot(self, snapshot: RadarSnapshot) -> None:
        """Inspect a snapshot and dispatch any new conditions to agents.

        Applies ATC priority rules: when an active emergency is present,
        lower-priority conflict and weather dispatches are vetoed
        (deferred) — the Emergency Response agent holds the floor. This
        mirrors how a real ATC priority stack works and is the 'agent
        veto power' differentiator.

        Args:
            snapshot: The latest radar snapshot.
        """
        emergency_active = bool(snapshot.emergencies)
        # Emerencies always fire first and get top priority.
        await self._post_emergencies(snapshot)

        if emergency_active:
            await self._post_vetoed_lower_priority(snapshot)
        else:
            await self._post_conflicts(snapshot)
            await self._post_weather(snapshot)

    async def _post_vetoed_lower_priority(self, snapshot: RadarSnapshot) -> None:
        """Defer conflict/weather advisories while an emergency is active.

        Each deferred condition is recorded once so it does not re-veto
        on every tick, and a structured Band event is emitted so the
        audit timeline shows the Emergency Response agent exercising its
        veto authority.

        Args:
            snapshot: The latest radar snapshot with an active emergency.
        """
        deferred = [*snapshot.conflicts, *snapshot.weather_advisories]
        for advisory in deferred:
            advisory_id = getattr(advisory, "advisory_id", None)
            if advisory_id is None:
                continue
            key = f"vetoed:{advisory_id}"
            if key in self._dispatched:
                continue
            self._dispatched.add(key)
            kind = (
                "conflict"
                if advisory.__class__.__name__ == "ConflictAdvisory"
                else "weather"
            )
            message = BandOutboundMessage(
                sender="emergency-response",
                content=(
                    f"VETO: deferring {kind} advisory {advisory_id} — "
                    "active emergency has priority per ATC rules."
                ),
                mentions=[],
                metadata={
                    "kind": "veto",
                    "vetoed_kind": kind,
                    "vetoed_advisory_id": advisory_id,
                    "reason": "active emergency has priority",
                },
                correlation_id=advisory_id,
            )
            await self._safe_post(message, "emergency-response (veto)")

    def reset(self) -> None:
        """Clear the dispatched-key cache and rate-limit timestamps."""
        self._dispatched.clear()
        self._agent_timestamps.clear()

    # ------------------------------------------------------------------
    # Per-condition dispatch
    # ------------------------------------------------------------------

    async def _post_conflicts(self, snapshot: RadarSnapshot) -> None:
        """Dispatch new conflict advisories to the conflict detector.

        Args:
            snapshot: The latest radar snapshot.
        """
        for advisory in snapshot.conflicts:
            key = f"conflict:{advisory.advisory_id}"
            if key in self._dispatched:
                continue
            self._dispatched.add(key)

            cpa = advisory.cpa
            message = BandOutboundMessage(
                sender="system-ingest",
                content=(
                    f"@conflict-detector Conflict detected "
                    f"{cpa.aircraft_a_callsign}/{cpa.aircraft_b_callsign} "
                    f"CPA {cpa.min_distance_nm} nm in {cpa.time_to_cpa_seconds}s "
                    f"(severity {advisory.severity.value})."
                ),
                mentions=["conflict-detector"],
                metadata={
                    "kind": "conflict",
                    "summary": (
                        f"Conflict {cpa.aircraft_a_callsign}/{cpa.aircraft_b_callsign} "
                        f"CPA {cpa.min_distance_nm} nm"
                    ),
                    "cpa": {
                        "aircraft_a_callsign": cpa.aircraft_a_callsign,
                        "aircraft_b_callsign": cpa.aircraft_b_callsign,
                        "min_distance_nm": cpa.min_distance_nm,
                        "time_to_cpa_seconds": cpa.time_to_cpa_seconds,
                        "is_conflict": cpa.is_conflict,
                    },
                },
                correlation_id=advisory.advisory_id,
            )
            await self._safe_post(message, "conflict-detector")

    async def _post_emergencies(self, snapshot: RadarSnapshot) -> None:
        """Dispatch new emergency declarations to emergency response.

        Args:
            snapshot: The latest radar snapshot.
        """
        for emrg in snapshot.emergencies:
            key = f"emergency:{emrg.emergency_id}"
            if key in self._dispatched:
                continue
            self._dispatched.add(key)

            message = BandOutboundMessage(
                sender="system-ingest",
                content=(
                    f"@emergency-response EMERGENCY {emrg.callsign} squawking "
                    f"{emrg.squawk_code} (phase {emrg.phase.value})."
                ),
                mentions=["emergency-response"],
                metadata={
                    "kind": "emergency",
                    "summary": f"Emergency {emrg.callsign} squawk {emrg.squawk_code}",
                    "callsign": emrg.callsign,
                    "squawk_code": emrg.squawk_code,
                    "phase": emrg.phase.value,
                },
                correlation_id=emrg.emergency_id,
            )
            await self._safe_post(message, "emergency-response")

    async def _post_weather(self, snapshot: RadarSnapshot) -> None:
        """Dispatch new weather advisories to the weather analyst.

        Args:
            snapshot: The latest radar snapshot.
        """
        for advisory in snapshot.weather_advisories:
            key = f"weather:{advisory.advisory_id}"
            if key in self._dispatched:
                continue
            self._dispatched.add(key)

            affected = ", ".join(advisory.affected_callsigns)
            message = BandOutboundMessage(
                sender="system-ingest",
                content=(
                    f"@weather-analyst SIGMET {advisory.sigmet.sigmet_id} "
                    f"({advisory.sigmet.phenomenon}) affects {affected}."
                ),
                mentions=["weather-analyst"],
                metadata={
                    "kind": "weather",
                    "summary": (
                        f"SIGMET {advisory.sigmet.sigmet_id} affects {affected}"
                    ),
                    "sigmet_id": advisory.sigmet.sigmet_id,
                    "affected_callsigns": advisory.affected_callsigns,
                },
                correlation_id=advisory.advisory_id,
            )
            await self._safe_post(message, "weather-analyst")

    def _check_rate_limit(self, agent: str) -> bool:
        """Check whether an agent is within its per-minute message limit.

        Maintains a rolling window of dispatch timestamps per agent.
        Timestamps older than ``AGENT_RATE_WINDOW_SECONDS`` are pruned
        on each call. If the agent has fewer than
        ``AGENT_RATE_LIMIT`` dispatches in the current window the
        check passes (returns ``True``); otherwise it fails (returns
        ``False``).

        Args:
            agent: The agent identity being dispatched.

        Returns:
            ``True`` if the dispatch is allowed, ``False`` if it should
            be dropped.
        """
        now = time.monotonic()
        timestamps = self._agent_timestamps[agent]
        # Prune timestamps outside the rolling window.
        cutoff = now - AGENT_RATE_WINDOW_SECONDS
        self._agent_timestamps[agent] = [t for t in timestamps if t > cutoff]
        timestamps = self._agent_timestamps[agent]

        if len(timestamps) >= AGENT_RATE_LIMIT:
            logger.warning(
                "Rate limit hit for @%s: %d/%d in last %.0fs — dropping dispatch",
                agent,
                len(timestamps),
                AGENT_RATE_LIMIT,
                AGENT_RATE_WINDOW_SECONDS,
            )
            return False

        # Record this dispatch.
        timestamps.append(now)
        return True

    async def _safe_post(self, message: BandOutboundMessage, agent: str) -> None:
        """Post a message, enforcing per-agent rate limiting.

        If the agent has already been dispatched 3 or more messages in
        the last 60 seconds, this dispatch is silently dropped with a
        warning log. Otherwise it is posted normally.

        A failed post must not crash the simulation loop.  If the room
        limit is reached, :meth:`LiveBandClient.post_message` will
        auto-prune and retry, so the caller does not need to handle
        limit_reached specially.

        Args:
            message: The outbound message.
            agent: The agent being dispatched (for logging and rate limiting).
        """
        if not self._check_rate_limit(agent):
            return

        try:
            await self._client.post_message(message)
            logger.info("Dispatched @%s for %s", agent, message.correlation_id)
        except Exception:
            logger.exception(
                "Failed to post @%s message (correlation_id=%s)",
                agent,
                message.correlation_id,
            )
