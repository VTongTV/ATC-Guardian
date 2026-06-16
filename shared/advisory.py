"""Advisory classification helpers shared across the backend.

Both the in-process simulated agents (``sim_agents``) and the live-mode
advisory ingester need to derive a human-readable ``kind`` label
(``conflict`` / ``weather`` / ``emergency`` / ``advisory``) from the
unstructured metadata attached to a Band message. Centralising that logic
here keeps the two paths consistent so a decision surfaced in live mode is
classified the same way as one surfaced in sim mode.
"""

from __future__ import annotations


def kind_from_metadata(meta: dict) -> str:
    """Map advisory metadata to a kind label for the decision service.

    Looks at both the structured ``kind`` field and the human-readable
    ``summary``/``callsign`` so a safety-verdict reply (whose kind is
    ``safety_verdict``) still resolves to the originating condition type.

    Args:
        meta: The message metadata. Treated as read-only.

    Returns:
        One of ``conflict`` / ``weather`` / ``emergency`` / ``advisory``.
    """
    haystack = (
        f"{meta.get('kind', '')} {meta.get('summary', '')} "
        f"{meta.get('callsign', '')}"
    ).lower()
    if "conflict" in haystack:
        return "conflict"
    if "sigmet" in haystack or "weather" in haystack:
        return "weather"
    if "emergency" in haystack or "7700" in haystack or "distress" in haystack:
        return "emergency"
    return "advisory"


def is_promotable_advisory(meta: dict) -> bool:
    """Decide whether an ingested message should become a pending decision.

    Conservative, demo-safe rule: promote only when the metadata signals a
    reviewable advisory — either an explicit reviewer ``verdict`` of
    ``APPROVE``/``MODIFY``, or a recognised ``kind`` plus a ``summary``.
    Messages already carrying a ``decision_id`` are skipped (the sim
    coordinator handler, or a prior ingest, already created the proposal).

    Args:
        meta: The message metadata. Treated as read-only.

    Returns:
        True if the ingester should call ``create_proposal`` for this message.
    """
    if not isinstance(meta, dict):
        return False
    # Already surfaced as a decision — never duplicate.
    if meta.get("decision_id"):
        return False
    verdict = str(meta.get("verdict", "")).upper()
    if verdict in {"APPROVE", "MODIFY"}:
        return True
    kind = kind_from_metadata(meta)
    return kind in {"conflict", "weather", "emergency"} and bool(meta.get("summary"))
