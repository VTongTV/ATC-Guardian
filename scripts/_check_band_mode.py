"""One-shot helper for start.bat: report Band mode and credential sanity.

Prints exactly one line and exits. Used by ``start.bat`` to decide whether
to launch the six agent processes. Kept dependency-free (stdlib only) so it
runs even before the venv is fully populated.

Exit / output contract (the prefix is what start.bat switches on):

    ``sim``                 BAND_MODE != live — offline, no agents needed.
    ``live:ok``             BAND_MODE=live and all 6 agent IDs + keys look real.
    ``live:skip:REASON``    BAND_MODE=live but something is a placeholder/missing.

"Looks real" means the value is set and is NOT the placeholder UUID
(``00000000-0000-0000-0000-000000000000``) or the ``band_u_...-here`` key
template shipped in ``.env.example``. We do not call Band — this is a fast
local guard, not a credential check.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"
PLACEHOLDER_KEY_MARKERS = ("-here", "your-band", "band_u_your")

AGENTS = [
    "COORDINATOR",
    "CONFLICT_DETECTOR",
    "WEATHER_ANALYST",
    "SAFETY_REVIEWER",
    "GROUND_OPS",
    "EMERGENCY_RESPONSE",
]


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _looks_real_uuid(value: str) -> bool:
    return bool(value) and value != PLACEHOLDER_UUID


def _looks_real_key(value: str) -> bool:
    if not value:
        return False
    return not any(marker in value for marker in PLACEHOLDER_KEY_MARKERS)


def main() -> int:
    env = _load_env(Path(__file__).resolve().parent.parent / ".env")
    # The process environment wins over .env if set (matches pydantic-settings).
    for k in list(env) + [f"{a}_AGENT_ID" for a in AGENTS] + [f"{a}_API_KEY" for a in AGENTS]:
        env[k] = os.environ.get(k, env.get(k, ""))

    mode = (env.get("BAND_MODE") or os.environ.get("BAND_MODE") or "sim").strip().lower()
    if mode != "live":
        print("sim")
        return 0

    # Live mode — validate the 6 agent credential pairs.
    missing_ids: list[str] = []
    bad_ids: list[str] = []
    missing_keys: list[str] = []
    bad_keys: list[str] = []
    for agent in AGENTS:
        uid = env.get(f"{agent}_AGENT_ID", "")
        key = env.get(f"{agent}_API_KEY", "")
        if not uid:
            missing_ids.append(agent)
        elif not _looks_real_uuid(uid):
            bad_ids.append(agent)
        if not key:
            missing_keys.append(agent)
        elif not _looks_real_key(key):
            bad_keys.append(agent)

    problems: list[str] = []
    if missing_ids:
        problems.append("missing *_AGENT_ID: " + ",".join(missing_ids))
    if bad_ids:
        problems.append("placeholder *_AGENT_ID: " + ",".join(bad_ids))
    if missing_keys:
        problems.append("missing *_API_KEY: " + ",".join(missing_keys))
    if bad_keys:
        problems.append("placeholder *_API_KEY: " + ",".join(bad_keys))

    if problems:
        print("live:skip:" + "; ".join(problems))
        return 1

    print("live:ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
