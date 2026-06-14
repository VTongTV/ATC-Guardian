"""Unit tests for the simulated Safety Reviewer agent verdict logic.

Verifies the adversarial review handler applies ICAO separation minima
correctly and returns structured APPROVE / REJECT / MODIFY verdicts
that route to the coordinator. No network, no LLM.
"""

import asyncio

from backend.app.services.sim_agents import safety_reviewer_handler
from shared.band_client import BandOutboundMessage


def _run(coro):
    """Run a coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _advisory(kind: str, cpa_dist: float | None = None, summary: str = "advisory") -> BandOutboundMessage:
    """Build a BandOutboundMessage simulating a specialist's submission."""
    metadata: dict = {"kind": kind, "summary": summary}
    if cpa_dist is not None:
        metadata["cpa"] = {"min_distance_nm": cpa_dist}
    return BandOutboundMessage(
        sender="conflict-detector",
        content=f"@safety-reviewer please review {summary}",
        mentions=["safety-reviewer"],
        metadata=metadata,
        correlation_id="ADV-TEST",
    )


class TestSafetyReviewerVerdicts:
    """Tests for the safety_reviewer_handler verdict classification."""

    def test_critical_conflict_is_approved(self) -> None:
        """A conflict with CPA under 3nm is APPROVED (immediate action)."""
        replies = _run(safety_reviewer_handler(_advisory("conflict_advisory", 2.5)))
        assert len(replies) == 1
        assert replies[0].metadata["verdict"] == "APPROVE"
        assert "3.0 nm" in replies[0].metadata["reasoning"]
        assert "coordinator" in replies[0].mentions

    def test_warning_conflict_is_approved(self) -> None:
        """A conflict with CPA between 3-5nm is APPROVED."""
        replies = _run(safety_reviewer_handler(_advisory("conflict_advisory", 4.2)))
        assert replies[0].metadata["verdict"] == "APPROVE"
        assert "5.0 nm" in replies[0].metadata["reasoning"]

    def test_marginal_conflict_is_modified(self) -> None:
        """A conflict with CPA at 5nm+ (alert band) is MODIFIED."""
        replies = _run(safety_reviewer_handler(_advisory("conflict_advisory", 5.5)))
        assert replies[0].metadata["verdict"] == "MODIFY"
        assert replies[0].metadata["modification"]

    def test_weather_advisory_is_approved(self) -> None:
        """Non-conflict advisories default to APPROVE."""
        replies = _run(safety_reviewer_handler(_advisory("weather_advisory", summary="SIGMET")))
        assert replies[0].metadata["verdict"] == "APPROVE"

    def test_verdict_content_starts_with_verdict_marker(self) -> None:
        """The reply content begins with 'VERDICT:' for parseability."""
        replies = _run(safety_reviewer_handler(_advisory("conflict_advisory", 2.0)))
        assert replies[0].content.startswith("VERDICT:")

    def test_verdict_carries_correlation_id(self) -> None:
        """The correlation_id is preserved from the advisory."""
        advisory = _advisory("conflict_advisory", 2.0)
        replies = _run(safety_reviewer_handler(advisory))
        assert replies[0].correlation_id == advisory.correlation_id

    def test_verdict_metadata_includes_role_and_kind(self) -> None:
        """Verdict metadata identifies the reviewer and the event kind."""
        replies = _run(safety_reviewer_handler(_advisory("conflict_advisory", 2.0)))
        assert replies[0].metadata["role"] == "safety-reviewer"
        assert replies[0].metadata["kind"] == "safety_verdict"
