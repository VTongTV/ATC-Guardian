# ATC Guardian

**A cross-framework, multi-agent decision-support system for Air Traffic Control — built for the Band of Agents Hackathon (Track 3: Regulated & High-Stakes Workflows).**

Six specialised AI agents collaborate through [Band](https://band.ai) to help human air traffic controllers detect conflicts, analyse weather, and coordinate emergencies. The guiding principle is **AI-assisted, human-decided**: agents detect, review, and recommend — the controller holds the only authority to execute.

> Built with **Band** as the collaboration layer, across **LangGraph**, **Pydantic AI**, and **CrewAI**.

---

## Why this project

Air traffic control is a regulated, high-stakes domain where review, traceability, escalation, and careful decision-making matter. ATC Guardian demonstrates what becomes possible when agents from **three different frameworks** can discover each other, coordinate work, cross-examine each other's outputs, and escalate to a human — all through Band.

Every agent action is logged for regulatory compliance, and every recommended action passes through an **independent adversarial Safety Reviewer** before reaching a **human-on-the-loop** approval gate.

---

## The agent team

Six agents collaborate through a single Band room. Each uses the framework best suited to its role:

| Agent | Framework | Role |
|---|---|---|
| **Coordinator** | LangGraph | Routes detected conditions and surfaces reviewed decisions to the controller |
| **Conflict Detector** | Pydantic AI | Computes closest-point-of-approach (CPA) and issues conflict advisories |
| **Weather Analyst** | CrewAI | Analyses SIGMETs and recommends deviation routes |
| **Safety Reviewer** | Pydantic AI | Independently cross-examines every advisory against ICAO minima (APPROVE / REJECT / MODIFY) |
| **Ground Ops** | LangGraph | Provides airport information (runways, ATIS, NOTAMs) |
| **Emergency Response** | LangGraph | Classifies emergency phase and coordinates the 7700 response |

### The collaboration loop

```
detect → @mention specialist → advisory → @safety-reviewer (verdict)
       → @coordinator → pending decision → CONTROLLER approves/rejects
```

For an emergency (squawk 7700), the loop expands:

```
system → @emergency-response → recruits @ground-ops → runway info
       → @safety-reviewer → @coordinator → CONTROLLER
```

The Emergency Response agent also holds **veto power**: while an emergency is active, lower-priority conflict and weather dispatches are deferred per ATC priority rules.

---

## Key features

- **Cross-framework collaboration through Band** — LangGraph + Pydantic AI + CrewAI agents in one room, visible in the UI's agent-team graph.
- **Adversarial review loop** — a dedicated Safety Reviewer challenges every advisory before it reaches the controller.
- **Human-on-the-loop** — agents recommend, the controller approves. Nothing executes without a human click.
- **What-if counterfactual** — propose a maneuver and preview the predicted CPA outcome *before* acting.
- **Emergency veto** — active emergencies override lower-priority advisories.
- **Regulator-ready audit export** — one-click JSON incident report with the full agent reasoning trail and controller decisions.
- **Structured Band events** — `thought` / `tool_call` / `tool_result` events flow into the audit timeline so reasoning is traceable.

---

## Architecture

```
┌─────────────┐    WebSocket     ┌──────────────────────────────────────────┐
│  React +    │ ◄──────────────► │  FastAPI backend                         │
│  Leaflet    │                  │  ┌─────────────────┐  ┌───────────────┐  │
│  radar UI   │                  │  │ SimulationLoop  │->│ Detector      │  │
└─────────────┘                  │  │ (CPA/SIGMET/    │  │ (conflict/emg)│  │
                                 │  │  7700 detection)│  └───────────────┘  │
                                 │  └────────┬────────┘                     │
                                 │           ▼                              │
                                 │  ┌─────────────────┐  ┌───────────────┐  │
                                 │  │ BandPoster      │->│ BandClient    │  │
                                 │  │ (event-driven   │  │ (sim | live)  │  │
                                 │  │  @mention)      │  └───────┬───────┘  │
                                 │  └────────┬────────┘          │          │
                                 │           ▼                   │          │
                                 │  ┌─────────────────┐          │          │
                                 │  │ AdvisoryIngester│◄─────────┘          │
                                 │  │ -> audit log    │                     │
                                 │  └─────────────────┘                     │
                                 └──────────────────────────────────────────┘
                                                    │
                                                    ▼ (BAND_MODE=live)
                                          ┌──────────────────┐
                                          │  Band room        │
                                          │  6 remote agents  │
                                          └──────────────────┘
```

**Offline-first by design.** The backend talks to a `BandClient` abstraction. In `BAND_MODE=sim` (default), an in-process message bus runs the full detect → @mention → advisory loop with **zero credentials** — the radar, agent chat, decisions, and audit timeline all populate. Flip `BAND_MODE=live` once the Band room and agents are provisioned and the identical code talks to real Band.

---

## Quick start (offline demo — no API keys needed)

> For the full, step-by-step walkthrough (offline + live Band), see **[SETUP.md](SETUP.md)**.

```bash
# 1. Backend (Python 3.12+)
uv venv && uv sync
uv run python -m uvicorn backend.app.main:app --port 8000

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

Open the UI, switch scenarios (SCN-A conflict, SCN-B weather, SCN-C emergency), and watch the collaboration cascade populate the agent chat, the safety-reviewer verdicts appear, and controller decisions queue up for approval.

## Going live with Band

> This is the short version. For every step with expected output and a
> troubleshooting table, see **[SETUP.md → Track B](SETUP.md#track-b--live-band-room-6-real-agents)**.

```bash
# 1. Create a Band account (promo code BANDHACK26 for 1 month Pro)
# 2. Create 6 remote agents at app.band.ai/agents, copy each ID + API key
# 3. Create a chat room and add all 6 agents
# 4. Fill in .env (from .env.example):
cp .env.example .env
#    Set BAND_MODE=live, BAND_API_KEY, BAND_ROOM_ID, and the 6 *_AGENT_ID/*_API_KEY
#    Set LLM_PROVIDER=aimlapi and the AI/ML API key(s)

# 5. Start everything:
uv run python scripts/start_all.py  # backend + 6 agents + frontend
```

---

## Partner technology

ATC Guardian targets the **Best Use of AI/ML API** ($1,000) prize with principled, per-agent model choices: **one AI/ML API key gives access to frontier models from multiple labs, and each agent uses the model best matched to its task** rather than forcing a single model everywhere (see `GET /collaboration/partner-routing`).

| Agent | Model | Why |
|---|---|---|
| Conflict Detector | `deepseek/deepseek-v4-pro` | Deep reasoning + reliable JSON for CPA advisories |
| Weather Analyst | `deepseek/deepseek-v4-pro` | Best analytical model for SIGMET interpretation |
| Safety Reviewer | `zhipu/glm-5.1` | Deterministic APPROVE/REJECT/MODIFY at temp 0 |
| Emergency Response | `zhipu/glm-5.1` | Deterministic 7700 phase classification |
| Coordinator | `moonshot/kimi-k2-6` | Long-context instruction-following for @mention dispatch |
| Ground Ops | `deepseek/deepseek-v4-flash` | Fast, cheap tool-calls for runway/ATIS/NOTAM lookups |

*Per-agent models confirmed on AI/ML API (verified 2026-06).*

---

## API reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/data/simulated` | GET | Current radar snapshot |
| `/data/scenario/{id}` | POST | Switch scenario (SCN-A/B/C) |
| `/ws/radar` | WS | Real-time radar push |
| `/audit/events` | GET | Agent event log (timeline) |
| `/audit/export` | GET | Regulator-ready incident report (JSON) |
| `/decisions/pending` | GET | Pending controller decisions |
| `/decisions/{id}/resolve` | POST | Controller APPROVE/REJECT/MODIFY |
| `/whatif/maneuver` | POST | Counterfactual CPA evaluation |
| `/collaboration/graph` | GET | Agent team graph + live @mention edges |
| `/collaboration/partner-routing` | GET | Per-agent partner model rationale |
| `/weather/{metar,taf,airsigmet,pirep}` | GET | AWC weather proxy |

---

## Testing

```bash
uv run pytest tests/ -q   # 171 tests, all green
```

Tests cover the CPA math, conflict/emergency/weather detection, the full Band collaboration loop (offline), the safety-reviewer verdict logic, human-on-the-loop decisions, the what-if counterfactual, audit export, partner routing, and all routers.

---

## Project structure

```
agents/              # 6 Band agents (each own venv + framework)
  coordinator/       # LangGraph
  conflict_detector/ # Pydantic AI
  weather_analyst/   # CrewAI
  safety_reviewer/   # Pydantic AI (adversarial)
  ground_ops/        # LangGraph
  emergency_response/# LangGraph
backend/app/         # FastAPI: routers, services, config
data/                # Scenario definitions + simulation engine
ml/                  # CPA, trajectory, what-if (pure math)
shared/              # Models, constants, BandClient, agent roster
frontend/src/        # React + Leaflet radar UI
tests/               # 171 tests
```

---

## License

MIT
