# ATC Guardian — Setup Guide

End-to-end setup, from `git clone` to a running demo. Two tracks:

- **Track A — Offline demo (no API keys).** Runs the full agent-collaboration
  loop in-process. Use this to evaluate the project in minutes.
- **Track B — Live Band room (6 real agents + an LLM).** The same code talks
  to a real [Band](https://band.ai) room with six framework-mixed agents.

> New here? Do **Track A** first. It validates the whole stack with zero
> credentials and zero cost; Track B then only adds the Band + LLM keys.

---

## Prerequisites (both tracks)

| Tool | Version | Why | Install |
|---|---|---|---|
| **Python** | 3.12+ | Backend + agents (`requires-python = ">=3.12"`) | [python.org](https://python.org) |
| **uv** | latest | Manages the project venv | `pip install uv` / [astral.sh/uv](https://docs.astral.sh/uv/) |
| **Node.js** | 20+ | Frontend (Vite + React) | [nodejs.org](https://nodejs.org) |
| **Git** | any | Clone the repo | [git-scm.com](https://git-scm.com) |

Verify:

```bash
python --version    # >= 3.12
uv --version
node --version      # >= 20
git --version
```

---

## Track A — Offline demo (no API keys)

`BAND_MODE=sim` runs the entire `detect → @mention → advisory → safety-review → controller`
cascade in-process. No Band account, no LLM key, no network egress. The radar,
agent chat, safety verdicts, decisions, and audit timeline all populate.

### A1. Clone & enter

```bash
git clone <your-repo-url> atc-guardian
cd atc-guardian
```

### A2. Configure environment

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

`.env.example` already ships with the offline defaults you need:

```ini
BAND_MODE=sim            # offline in-process simulation (no Band account)
LLM_PROVIDER=openrouter  # default; sim mode never calls it anyway
```

> In `sim` mode the LLM provider is never contacted, so the placeholder
> `OPENROUTER_API_KEY` value is fine. Leave everything else as-is.

### A3. Create the venv & install deps

```bash
uv venv
uv sync
```

You should see `Resolved N packages` and `Installed ... in Xs`. This creates
`.venv/` at the project root with backend + agent framework deps.

### A4. Install frontend deps

```bash
cd frontend
npm install
cd ..
```

### A5. Start backend + frontend

Two terminals, or use the bundled launcher:

**Option 1 — bundled Windows launcher** (opens two console windows):

```cmd
start.bat
```

**Option 2 — manual (any OS):**

Terminal 1 (backend):

```bash
uv run python -m uvicorn backend.app.main:app --port 8000 --reload
```

Terminal 2 (frontend):

```bash
cd frontend
npm run dev
```

### A6. Verify it works

| Check | How | Expected |
|---|---|---|
| Backend up | open `http://localhost:8000/docs` | FastAPI Swagger UI loads |
| Frontend up | open `http://localhost:5173` | Radar UI renders with aircraft |
| Radar data | `curl http://localhost:8000/data/simulated` | JSON with `aircraft[]` |
| Agent graph | `curl http://localhost:8000/collaboration/graph` | JSON with 6 agents |
| Tests green | `uv run pytest tests/ -q` | `171 passed` |

### A7. Watch the collaboration cascade

In the UI, switch scenarios (top bar) and watch:

- **SCN-A (Conflict)** — `conflict-detector` flags a CPA → `safety-reviewer`
  verdict → `coordinator` queues a pending decision.
- **SCN-B (Weather)** — `weather-analyst` detects the SIGMET overlap → deviation
  advisory → review → pending decision.
- **SCN-C (Emergency)** — squawk 7700 → `emergency-response` recruits
  `ground-ops` (veto defers lower-priority advisories) → review → controller.

Approve/reject decisions in the **Decision Panel** — nothing executes without
your click (human-on-the-loop). Click **Export Audit** for the regulator-ready
JSON incident report.

Or run the self-narrating guided demo:

```bash
uv run python scripts/demo_runner.py
```

Track A is complete. To go live with real Band agents, continue to Track B.

---

## Track B — Live Band room (6 real agents)

Switches `BAND_MODE=live`: the backend POSTs to a real Band room and six agent
processes (one per framework) connect to it. You need a Band account, an LLM
API key, and the agent framework deps (already installed in A3).

### B1. Sign up for Band

1. Create an account at **<https://band.ai>**.
2. (Hackathon) Apply promo code **`BANDHACK26`** for 1 month of Pro.

### B2. Get an LLM key (pick one provider)

ATC Guardian supports two LLM providers via `LLM_PROVIDER`:

**AI/ML API (recommended for the demo/judging)** — one key unlocks every lab:

1. Sign up at **<https://aimlapi.com>** (hackathon partner promo).
2. Copy your key from the dashboard.

Set `LLM_PROVIDER=aimlapi` and uncomment the per-agent `*_MODEL` overrides in
`.env` (see B5) — each agent then uses the frontier model best matched to its
task (the "one API, many labs, right model per job" pitch).

**OpenRouter (free fallback)** — no credit card, free models:

1. Sign up at **<https://openrouter.ai>**.
2. Create a key; it starts with `sk-or-v1-`.

Set `LLM_PROVIDER=openrouter` and paste the key. Good enough to run end-to-end.

### B3. Create the 6 Band agents

At **<https://app.band.ai/agents>**, click **New Agent → Remote Agent** and
create **six** agents, one per role. Suggested names:

| # | Agent name in Band | Handle (must match exactly) | Framework | Role |
|---|---|---|---|---|
| 1 | `Coordinator` | `coordinator` | LangGraph | Routes conditions, surfaces reviewed decisions |
| 2 | `Conflict Detector` | `conflict-detector` | Pydantic AI | CPA computation + conflict advisories |
| 3 | `Weather Analyst` | `weather-analyst` | CrewAI | SIGMET analysis + deviation routing |
| 4 | `Safety Reviewer` | `safety-reviewer` | Pydantic AI | Adversarial APPROVE/REJECT/MODIFY |
| 5 | `Ground Ops` | `ground-ops` | LangGraph | Runway / ATIS / NOTAM lookups |
| 6 | `Emergency Response` | `emergency-response` | LangGraph | 7700 phase classification |

> ⚠️ **The handles must match exactly** — the backend routes `@mention`
> targets by handle name. Copy them character-for-character.
>
> ⚠️ **The API key for each agent is shown ONCE at creation — save it
> immediately.** You cannot retrieve it later.

For each agent, copy:
- the **Agent UUID** (e.g. `12345678-…-…-…-…`),
- the **Agent API key** (e.g. `band_u_…`).

### B4. Create the Band room

1. At **<https://app.band.ai>**, create a new chat room.
2. **Add all six agents** as participants.
3. Copy the **Room ID**.

### B5. Fill in `.env`

Edit your `.env` (created in A2) and set the live values:

```ini
# --- switch to live ---
BAND_MODE=live
BAND_API_KEY=band_u_your-band-api-key-here
BAND_ROOM_ID=00000000-0000-0000-0000-000000000000   # from B4

# --- 6 agent IDs + keys (from B3) ---
COORDINATOR_AGENT_ID=...         COORDINATOR_API_KEY=...
CONFLICT_DETECTOR_AGENT_ID=...   CONFLICT_DETECTOR_API_KEY=...
WEATHER_ANALYST_AGENT_ID=...     WEATHER_ANALYST_API_KEY=...
SAFETY_REVIEWER_AGENT_ID=...     SAFETY_REVIEWER_API_KEY=...
GROUND_OPS_AGENT_ID=...          GROUND_OPS_API_KEY=...
EMERGENCY_RESPONSE_AGENT_ID=...  EMERGENCY_RESPONSE_API_KEY=...
```

Then the LLM provider block — **AI/ML API** (recommended):

```ini
LLM_PROVIDER=aimlapi
AIMLAPI_KEY=your-aimlapi-key-here

# uncomment these to pin each agent to its task-matched model:
# CONFLICT_DETECTOR_MODEL=deepseek/deepseek-v4-pro
# SAFETY_REVIEWER_MODEL=zhipu/glm-5.1
# WEATHER_ANALYST_MODEL=deepseek/deepseek-v4-pro
# COORDINATOR_MODEL=moonshot/kimi-k2-6
# EMERGENCY_RESPONSE_MODEL=zhipu/glm-5.1
# GROUND_OPS_MODEL=deepseek/deepseek-v4-flash
```

…or **OpenRouter** (free fallback):

```ini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-your-openrouter-key-here
# per-agent overrides optional; defaults to nex-agi/nex-n2-pro:free
```

### B6. Sync deps (if you skipped Track A)

If you already did Track A (A3 + A4), you can skip this — all deps are in one
venv. Otherwise:

```bash
uv venv && uv sync    # backend + agent framework deps
cd frontend && npm install && cd ..
```

### B7. Start everything

```bash
uv run python scripts/start_all.py
```

This launches, in order:
1. FastAPI backend on `http://localhost:8000`,
2. the six agent processes (from the project venv) against Band,
3. the Vite frontend on `http://localhost:5173`.

Press **Ctrl+C** once to stop all of them.

> **Windows alternative:** `start.bat` launches just backend + frontend.
> For live mode with the six agents, use `start_all.py` instead.

### B8. Verify live mode

| Check | How | Expected |
|---|---|---|
| Backend `BAND_MODE` | `GET http://localhost:8000/collaboration/graph` | 6 agents present |
| Agents connected | watch the agent console windows | each logs a successful Band connection |
| Real LLM responses | trigger SCN-A in the UI | advisories carry model-generated reasoning (not canned text) |
| Audit trail | UI timeline | `thought`/`tool_call`/`tool_result` events from the live agents |

Track B is complete — the system is now running six cross-framework agents
collaborating through a real Band room.

---

## The setup / start scripts

| Script | What it does | When |
|---|---|---|
| `scripts/setup.py` | Syncs project venv + installs frontend deps | once, or after dependency changes |
| `scripts/start_all.py` | Launches backend + 6 agents + frontend (Ctrl+C stops all) | every live run (Track B) |
| `scripts/demo_runner.py` | Auto-plays SCN-A→B→C with narration cues to the timeline | demoing |
| `scripts/smoke_test.py` | Verifies the full offline stack end-to-end (`ALL SMOKE CHECKS PASSED`) | before every submission/demo |
| `start.bat` | Windows launcher: backend + frontend in two windows | quick Track A run on Windows |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Frontend blank; console shows `ECONNREFUSED ::1:8000` | Vite proxy resolves `localhost` to IPv6 `::1` but the backend listens on IPv4 | already fixed — `vite.config.ts` proxies to `127.0.0.1:8000`. If you overrode it, restore that. |
| `uv: command not found` | uv not installed / not on PATH | `pip install uv`, or see [astral.sh/uv](https://docs.astral.sh/uv/) |
| Agent starts then exits | missing/wrong `*_AGENT_ID` / `*_API_KEY`, or agent not added to the Band room | re-check B3/B4 values in `.env`; confirm all 6 agents are room participants |
| Backend starts but advisories look canned | still in `BAND_MODE=sim` | set `BAND_MODE=live` + the Band + LLM keys, restart |
| `OPENROUTER_API_KEY` errors in sim mode | none — sim mode never calls the LLM | safe to ignore; it only matters in live mode |
| Live advisories fail / empty responses | bad LLM key, or `*_MODEL` not available on that provider | verify the key; for AI/ML API confirm each `*_MODEL` id is valid |
| `429 Too Many Requests` (OpenRouter) | free-model rate limits (20 RPM / 200 RPD per model) | use AI/ML API for the demo, or wait out the window |
| Port 8000 / 5173 already in use | another process holds the port | stop it, or change `--port` (backend) / `server.port` (`frontend/vite.config.ts`) |
| `Python version ... not compatible` | Python < 3.12 | install 3.12+ and recreate the venv (`uv venv` removes the old one) |

---

## Quick reference — env vars that matter

| Variable | Track A | Track B | Notes |
|---|---|---|---|
| `BAND_MODE` | `sim` | `live` | offline vs real Band REST |
| `BAND_API_KEY` | (ignored) | required | Band platform key |
| `BAND_ROOM_ID` | (ignored) | required | the room with all 6 agents |
| `*_AGENT_ID` / `*_API_KEY` (×6) | (ignored) | required | per-agent, from B3 |
| `LLM_PROVIDER` | `openrouter` | `aimlapi` or `openrouter` | sim never calls it |
| `OPENROUTER_API_KEY` | placeholder | required if `LLM_PROVIDER=openrouter` | |
| `AIMLAPI_KEY` | (ignored) | required if `LLM_PROVIDER=aimlapi` | one key, many labs |
| `*_MODEL` (×6, optional) | — | recommended with `aimlapi` | pins each agent to a task-matched model |

See `.env.example` for the full, commented reference.
