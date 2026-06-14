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
"""

from __future__ import annotations

import logging

from shared.band_client import BandClient, BandOutboundMessage
from shared.models import RadarSnapshot

logger = logging.getLogger(__name__)


class BandPoster:
    """Posts @mentions into Band when new radar conditions appear.

    Attributes:
        _client: The BandClient transport (sim or live).
        _dispatched: Set of condition keys already dispatched, used to
            avoid re-triggering agents for an ongoing condition.
    """

    def __init__(self, client: BandClient) -> None:
        """Initialise the poster with a Band client.

        Args:
            client: The BandClient used to post messages.
        """
        self._client = client
        self._dispatched: set[str] = set()

    async def process_snapshot(self, snapshot: RadarSnapshot) -> None:
        """Inspect a snapshot and dispatch any new conditions to agents.

        Args:
            snapshot: The latest radar snapshot.
        """
        await self._post_conflicts(snapshot)
        await self._post_emergencies(snapshot)
        await self._post_weather(snapshot)

    def reset(self) -> None:
        """Clear the dispatched-key cache (e.g. on scenario change)."""
        self._dispatched.clear()

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

    async def _safe_post(self, message: BandOutboundMessage, agent: str) -> None:
        """Post a message, logging and swallowing transport errors.

        A failed post must not crash the simulation loop.

        Args:
            message: The outbound message.
            agent: The agent being dispatched (for logging).
        """
        try:
            await self._client.post_message(message)
            logger.info("Dispatched @%s for %s", agent, message.correlation_id)
        except Exception:
            logger.exception(
                "Failed to post @%s message (correlation_id=%s)",
                agent,
                message.correlation_id,
            )
