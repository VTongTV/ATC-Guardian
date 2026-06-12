# ATC Guardian — Build Plan

> **Status**: DRAFT v4 — Review Loops 1-3 complete, all fixes applied
> **Track**: 3 (Regulated & High-Stakes Workflows)
> **Budget**: $0 (100% free infrastructure)
> **Timeline**: 7 days (Jun 12–19, 2026)

---

## 1. Project Overview

**ATC Guardian** is a multi-agent decision support system for Air Traffic Control. Five specialized AI agents collaborate through Band to assist human controllers with conflict detection, weather analysis, ground operations, and emergency response.

**Core Principle**: AI-assisted, human-decided. The controller always has final authority. Every agent action is logged for full traceability.

**Novelty Angles** (for Originality judging):
1. **Cross-framework coordination in safety-critical domain** — 3 different frameworks (LangGraph, CrewAI, Pydantic AI) collaborating in a domain where failure = lives. Emergency Response uses LangGraph with AI/ML API's OpenAI-compatible endpoint, demonstrating cross-provider routing through the same adapter.
2. **Adversarial review loop** — Agents challenge each other's recommendations before they reach the human controller
3. **Structured audit trail for regulatory compliance** — Every agent decision, reasoning step, and handoff logged as structured events for post-incident review
4. **Human-on-the-loop, not human-in-the-loop** — Controller monitors a team of agents that are already collaborating autonomously

---

## 2. Tech Stack (Locked)

| Layer | Technology | Why |
|---|---|---|
| **Frontend** | React + TypeScript + shadcn/ui | Professional, UI-complete for regulated feel |
| **State** | Zustand (single store, `subscribeWithSelector`) | Global, minimal re-renders |
| **Radar** | HTML5 Canvas (rAF + ref pattern) + CSS conic-gradient sweep | Performance, authentic ATC look |
| **Backend** | FastAPI (Python) | Routes data, proxies external APIs, WebSocket hub |
| **Agents** | 5 separate Python processes, each in own venv | Dependency isolation, realistic deployment |
| **Band** | `band-sdk[langgraph]`, `band-sdk[openai]`, `band-sdk[crewai]`, `band-sdk[pydantic-ai]` (separate installs per agent venv) | 4 adapters, 5 agents, no venv conflicts |
| **LLM — AI/ML API** | Primary for Conflict Detector + Emergency Response | **Partner prize eligibility** — $10 hackathon credit |
| **LLM — Featherless** | Primary for Weather Analyst + Ground Ops | **Partner prize eligibility** — $25 hackathon credit |
| **LLM — OpenRouter** | Development & testing (50 free/day) | Zero cost during dev |
| **LLM — NVIDIA NIM** | Development & testing (40 RPM free) | Zero cost during dev |
| **Aircraft Data** | OpenSky Network (`opensky-api` package, OAuth2) | Real-time ADS-B, free account |
| **Weather Data** | AWC Data API (proxied through FastAPI — no CORS) | METAR, TAF, SIGMET, PIREP |
| **ML** | numpy, scikit-learn (local) | Trajectory prediction, CPA |
| **Audit DB** | SQLite (local) | Persistent log beyond Band's 24h retention |
| **Hosting** | Vercel (frontend) + Render (backend) | Free tiers |

---

## 3. Data Flow Architecture (CRITICAL — reviewed and verified across 3 loops)

```
┌──────────────────────────────────────────────────────────────────┐
│                        DATA FLOW                                  │
│                                                                    │
│  [OpenSky / Mock Generator]                                       │
│         │                                                          │
│         ▼                                                          │
│  ┌─────────────────┐                                              │
│  │   FastAPI Backend │──── POST /agent/chats/{id}/messages ────┐  │
│  │   (Data Ingestion) │    (with @mentions to relevant agents)  │  │
│  └─────────┬─────────┘                                    │    │
│            │                                                ▼    │
│            │                                      ┌─────────────┐│
│            │                                      │ Band Room    ││
│            │                                      │ "ATC Guard"  ││
│            │                                      └──────┬──────┘│
│            │                                             │        │
│            │                          @mention routing    │        │
│            │                                             ▼        │
│            │                              ┌────────────────────┐  │
│            │                              │ 5 Agent Processes  │  │
│            │                              │ (each with own     │  │
│            │                              │  Band WebSocket)    │  │
│            │                              └────────┬───────────┘  │
│            │                                       │               │
│            │              Agent responses via       │               │
│            │              Band room messages        │               │
│            │                                       ▼               │
│            │                              ┌────────────────────┐  │
│            │                              │ FastAPI Backend     │  │
│            │◄─── REST polling every 2-5s ─│ (REST poller, NOT   │  │
│            │    GET /agent/chats/{id}/     │  WebSocket sub)     │  │
│            │    messages?status=all       │                     │  │
│            │    (captures ALL messages +   │                     │  │
│            │     events — text, thought,   │                     │  │
│            │     task, tool_call, etc.)    │                     │  │
│            │                              └────────────────────┘  │
│            │                                                       │
│            ▼                                                       │
│  ┌─────────────────┐     WebSocket (1 Hz)                        │
│  │   React Frontend │◄──────────────────────────────────────────│
│  │   (Canvas + UI)  │                                              │
│  └─────────────────┘                                              │
└──────────────────────────────────────────────────────────────────┘
```

**Key points**:
1. FastAPI acts as data ingester AND Band room poller
2. FastAPI has its own Band agent credentials (@system-ingest) for posting data and polling messages
3. **FastAPI does NOT subscribe via WebSocket** — Band's WebSocket only delivers @mentioned text messages to agents. Instead, FastAPI uses **REST polling** (`GET /agent/chats/{id}/messages?status=all`) every 2-5 seconds to capture ALL messages AND events (text, thought, task, tool_call, tool_result, error)
4. Agents receive data via Band @mentions, process, and respond in the room
5. FastAPI polls the room, stores events in SQLite, and pushes to React at 1 Hz
6. React never calls external APIs directly (CORS constraints on AWC, rate limits on OpenSky)

**Why REST polling instead of WebSocket subscription**:
- Band's Agent WebSocket only delivers text messages where the agent is @mentioned — it would miss agent-to-agent messages and all events (thought, task, tool_call, tool_result)
- REST polling via `GET /agent/chats/{id}/messages` returns everything in the room
- 2-5 second polling latency is acceptable for a demo
- Eliminates WebSocket subscription complexity in FastAPI entirely

---

## 4. Event Architecture (CRITICAL — reviewed and verified)

### Rule: `thenvoi_send_event` is for STANDARD event types ONLY
The SDK only allows 5 message types: `tool_call`, `tool_result`, `thought`, `error`, `task`.
Custom event types like `conflict.alert` are NOT supported.

### Solution: Use `thenvoi_send_message` for custom structured data

Agents communicate in two ways:

**1. Structured advisories (agent-to-agent / agent-to-human):**
```python
# Use thenvoi_send_message with JSON content
await tools.thenvoi_send_message(
    content='{"type":"conflict.alert","severity":"HIGH","aircraft":["UAL123","DAL456"],"cpa_minutes":4,"resolution":{"action":"HEADING_LEFT","value":15}}',
    mentions=["@coordinator", "@weather-analyst"]  # route to specific agents
)
```

**2. Reasoning steps (for audit trail):**
```python
# Use thenvoi_send_event for standard types
await tools.thenvoi_send_event(
    content="Analyzing converging trajectories for UAL123/DAL456 at FL340",
    message_type="thought"
)
await tools.thenvoi_send_event(
    content="CPA calculation: 2.1nm lateral, 0ft vertical, 4min to CPA",
    message_type="task",
    metadata={"severity": "HIGH", "aircraft": ["UAL123", "DAL456"]}
)
```

### Event flow for audit trail
Every agent decision emits:
1. `thought` event — what the agent is reasoning about
2. `task` event — what action it's taking (with structured `metadata`)
3. `thenvoi_send_message` — the actual advisory to other agents/humans

The frontend displays this as a chronological event timeline (traceability).

---

## 5. Canonical Data Model (Unit conversions verified)

```python
class AircraftState(BaseModel):
    icao24: str
    callsign: str
    latitude: float          # decimal degrees
    longitude: float         # decimal degrees
    altitude_ft: float       # feet MSL (converted from OpenSky meters: × 3.28084)
    heading_deg: float       # 0-360 (from OpenSky true_track, already degrees)
    speed_kts: float        # knots ground speed (converted from OpenSky m/s: × 1.94384)
    vertical_rate_fpm: float # feet per minute (converted from OpenSky m/s: × 196.85)
    squawk: str | None      # e.g., "7700", "7600", "7500"
    on_ground: bool
    flight_phase: str       # CLIMB, CRUISE, DESCENT, HOLD, APPROACH, TAXI
    timestamp: datetime

class WeatherReport(BaseModel):
    icao_id: str            # e.g., "KJFK"
    station_lat: float
    station_lon: float
    wind_dir: int           # degrees
    wind_speed_kt: int      # knots (AWC already in knots)
    visibility_sm: str      # statute miles (AWC already in SM)
    flight_category: str    # VFR, MVFR, IFR, LIFR
    clouds: list[CloudLayer]
    temperature_c: float
    altimeter_hpa: float
    raw_metar: str
    timestamp: datetime

class ConflictAdvisory(BaseModel):
    conflict_id: str
    aircraft: list[str]
    conflict_type: str      # SEPARATION_LOSS, HEAD_ON, CROSSING, LEVEL_BURST
    severity: str           # LOW, MEDIUM, HIGH, CRITICAL
    time_to_cpa_seconds: int
    min_separation_nm: float
    recommended_resolution: Resolution
    confidence: float

class Resolution(BaseModel):
    action: str             # HEADING_CHANGE, ALTITUDE_CHANGE, SPEED_CHANGE, DIVERT
    target_aircraft: str
    parameter: int          # degrees, feet, or knots depending on action
```

---

## 6. Agent Architecture (Updated with peer-to-peer + review loop)

### Agent Communication Map (peer-to-peer, not just hub-and-spoke)

```
@coordinator ──────→ @conflict-detector    (dispatch)
@coordinator ──────→ @weather-analyst      (dispatch)
@coordinator ──────→ @ground-ops            (dispatch)
@coordinator ──────→ @emergency-response   (7700 trigger)
@coordinator ──────→ @user                  (escalation)

@conflict-detector ─→ @weather-analyst      (PEER: "What's the weather at the conflict point?")
@weather-analyst ───→ @conflict-detector    (PEER: "SIGMET issued — assess impact on trajectories")
@emergency-response → @ground-ops           (PEER: "Prepare priority runway for 7700")
@conflict-detector ─→ @coordinator          (review: proposed resolution)
@coordinator ───────→ @conflict-detector     (REVIEW: "Validate resolution against current weather")
@ground-ops ────────→ @emergency-response   (PEER: "Runway 28L ready for emergency")
```

### Review Loop (Track 3: "review" theme)
Before escalating to the human controller, the Coordinator **challenges** agent recommendations:
1. Conflict Detector proposes resolution
2. Coordinator asks: "@conflict-detector Has @weather-analyst confirmed the alternate route is clear of weather?"
3. Conflict Detector consults Weather Analyst directly
4. Weather Analyst confirms or flags issue
5. Only then does Coordinator escalate to @user with a validated recommendation

### Agent 1: Coordinator (LangGraph)
- **Framework**: LangGraph (simple ReAct pattern — NO custom state machine)
- **LLM**: OpenRouter/NIM (dev) → AI/ML API (demo)
- **Role**: Orchestrator, router, reviewer
- **Band Tools**: `thenvoi_send_message`, `thenvoi_add_participant`, `thenvoi_get_participants`
- **Implementation**: Use simple `LangGraphAdapter(llm=..., checkpointer=InMemorySaver())`. Orchestration logic encoded in system prompt, not a state machine. Band's message model is stateless between turns — each incoming @mention triggers a fresh LLM call with conversation context.
- **Key Behavior**: Before escalating to @user, challenges agent recommendations by asking other agents to validate. Creates a review step.
- **Escalation**: severity >= HIGH or any emergency code
- **Audit**: Logs every delegation decision as `thought` event with rationale

### Agent 2: Conflict Detector (Pydantic AI)
- **Framework**: Pydantic AI
- **LLM**: **AI/ML API** (primary — partner prize eligibility) → OpenRouter/NIM (dev)
- **Role**: ML-based trajectory prediction, conflict detection, structured advisory output
- **Band Tools**: `thenvoi_send_message` (structured advisories via `additional_tools`), `thenvoi_send_event` (reasoning steps)
- **ML**: Linear extrapolation + CPA calculation (numpy) — runs locally, no API cost
- **Structured Output**: Uses `additional_tools` parameter to define a `submit_conflict_advisory` tool with `ConflictAdvisory` Pydantic model as input schema. The LLM calls this tool to submit validated structured advisories. (PydanticAIAdapter does not expose `result_type`, so structured output is achieved via tool-use.)
- **Severity**: LOW (>10 min), MEDIUM (5-10 min), HIGH (<5 min), CRITICAL (imminent)
- **Peer Communication**: Directly @mentions @weather-analyst for conditions at conflict point
- **Decision Protocol**: Must output structured `ConflictAdvisory` with confidence score, time-to-CPA, and recommended resolution
- **Bug Mitigation**: PydanticAI has a known `content: null` bug with complex tool usage on OpenAI models. Add error handling with retry. If persistent, switch to LangGraph adapter.

### Agent 3: Weather Analyst (CrewAI)
- **Framework**: CrewAI
- **LLM**: **Featherless AI** (primary — partner prize eligibility) → OpenRouter/NIM (dev)
- **Role**: Fetch and analyze aviation weather, assess operational impact
- **Band Tools**: `thenvoi_send_message` (weather alerts), `thenvoi_send_event` (reasoning)
- **Data Source**: AWC Data API (proxied through FastAPI backend — no CORS)
- **Peer Communication**: Proactively @mentions @conflict-detector when SIGMET affects active trajectories
- **Decision Protocol**: Must classify weather using standard SIGMET categories before recommending reroutes

### Agent 4: Ground Operations (LangGraph)
- **Framework**: LangGraph
- **LLM**: **Featherless AI** (primary — partner prize eligibility) → NVIDIA NIM (dev)
- **Role**: Monitor runway/taxiway status, detect incursions, sequence ground movement
- **Band Tools**: `thenvoi_send_message`, `thenvoi_send_event`
- **Peer Communication**: Responds directly to @emergency-response for runway preparation
- **Decision Protocol**: Must verify runway is clear before confirming availability

### Agent 5: Emergency Response (LangGraph + AI/ML API)
- **Framework**: LangGraph (via `band-sdk[langgraph]`) with `ChatOpenAI(base_url="https://api.aimlapi.com/v1")`
- **LLM**: **AI/ML API** (primary — Claude/GPT via OpenAI-compatible endpoint — partner prize eligibility)
- **Role**: Dynamic recruitment for 7700/7600/7500, human-in-the-loop escalation
- **Band Tools**: `thenvoi_send_message`, `thenvoi_send_event`, `thenvoi_add_participant`
- **Trigger**: Recruited by Coordinator when 7700/7600/7500 detected
- **Peer Communication**: Directly @mentions @ground-ops to prepare priority runway
- **Decision Protocol**: Must follow ICAO emergency classification checklist before acting. Communicates with calm, structured authority.
- **Note**: Uses LangGraph adapter (same as Coordinator) but with AI/ML API as LLM provider (`base_url` override). This demonstrates cross-provider routing through the same adapter — a different kind of cross-framework story. 3 unique adapters: LangGraph, CrewAI, Pydantic AI.

---

## 7. Band Room Design (Updated)

**Room**: `ATC Guardian Operations`

**Participants**: @coordinator, @conflict-detector, @weather-analyst, @ground-ops, @emergency-response, @system-ingest (FastAPI data agent), @user (human controller)

**Band Features Actively Used** (for "Application of Technology" judging):
1. **@mention routing** — Agents only see messages directed at them
2. **Dynamic participant management** — Emergency Response recruited on-demand via `thenvoi_add_participant`
3. **Parallel @mentions** — Coordinator sends `"@conflict-detector @weather-analyst Assess SIGMET impact"` for parallel work
4. **Event types** — All 5 standard types used: `thought`, `task`, `error`, `tool_call`, `tool_result`
5. **Delivery tracking** — System knows when agents have processed requests
6. **Contact auto-approval** — All agents under same account (siblings), no approval needed
7. **Structured messages** — JSON payloads in `thenvoi_send_message` for machine-readable advisories

---

## 8. LLM Routing Strategy (Updated for Partner Prize Eligibility)

| Agent | Primary LLM | Dev/Testing LLM | Partner Prize |
|---|---|---|---|
| Conflict Detector | **AI/ML API** (GPT-5.2 / Claude) | OpenRouter / NVIDIA NIM | ✅ AI/ML API |
| Weather Analyst | **Featherless AI** (Mistral/Qwen) | OpenRouter / NVIDIA NIM | ✅ Featherless |
| Ground Ops | **Featherless AI** (Llama/Mistral) | NVIDIA NIM | ✅ Featherless |
| Emergency Response | **AI/ML API** (Claude Sonnet/Opus) | OpenRouter | ✅ AI/ML API |
| Coordinator | OpenRouter / NVIDIA NIM | OpenRouter / NVIDIA NIM | — |

**Event-driven LLM invocation** (critical for budget):
- Agents only call LLMs when triggered by a condition (NOT on every data update)
- Rule-based pre-filters: CPA < 5nm → Conflict Detector wakes, squawk 7700 → Emergency Response wakes, SIGMET polygon overlaps flight path → Weather Analyst wakes
- Estimated LLM calls per 5-min demo: 10-15 total (well within free tiers)

---

## 9. Data Architecture (Updated)

### Simulated Mode (Primary for Demo)
- Procedural generator creates 20+ aircraft
- Realistic flight profiles: CLIMB, CRUISE, DESCENT, HOLD, APPROACH, TAXI
- All data uses canonical `AircraftState` model with correct units

### Live Mode (Showcase Feature)
- **OpenSky Network**: Use `opensky-api` package (official, OAuth2 support)
  - Free account: 4,000 credits/day
  - JFK bounding box (0.08 sq°): 1 credit per call
  - Poll every 30-60 seconds, interpolate between fetches
  - Register at opensky-network.org, create API client, download `credentials.json`
- **AWC Data API**: All calls proxied through FastAPI backend (no CORS)
  - 100 req/min rate limit
  - Endpoints: `/api/data/metar`, `/api/data/taf`, `/api/data/airsigmet`, `/api/data/pirep`
  - Example: `GET https://aviationweather.gov/api/data/metar?ids=KJFK&format=json`

### 3 Pre-Defined Scenarios (Realistic)

**Scenario A: "Converging Courses" (t=120s)**
- 20 aircraft in sector, standard cruise profiles
- UAL123 (B738, FL340, 450 kts, ORD→JFK) and DAL456 (A321, FL340, 460 kts, ATL→JFK) — already among the 20 — are on converging courses that bring them within CPA at t=120s
- Conflict Detector: computes CPA < 5nm, severity HIGH
- Peer: Conflict Detector @mentions Weather Analyst → "Clear skies, no constraints"
- Coordinator reviews: "Validated. Weather clear. Escalating to controller."
- To Human: "Recommend UAL123 turn left 15° or descend to FL330"

**Scenario B: "Thunderstorm Line" (t=180s)**
- 15 aircraft approaching from east
- SIGMET injected for severe thunderstorm covering east approach corridor
  - Polygon: [40.8,-73.5], [41.0,-73.2], [40.9,-72.8], [40.6,-73.0]
  - Movement: 270° at 25 kts
  - Altitude: surface to FL450
  - Valid: 2 hours
- Weather Analyst: fetches METAR (KJFK: 23016G32KT, 2SM TSRA, BKN015, OVC025CB), flags RUNWAY_CLOSED
- Peer: Weather Analyst proactively @mentions Conflict Detector → "Assess trajectory impact"
- Conflict Detector: finds alternate route has traffic conflict
- To Human: "Divert arrivals to Runway 28L. Sequence: AAL101 first, UAL202 second."

**Scenario C: "Mayday at 35,000" (t=300s)**
- Normal sector, no alerts
- UAL999 (B777, FL350, 480 kts) squawks 7700
- 60-second grace period (pilot assesses situation)
- Realistic descent: 1,500-2,000 fpm from FL350 to target FL150 (~10-12 min)
- Speed reduces to 220 kts (single-engine approach speed)
- Emergency Response recruited dynamically via `thenvoi_add_participant`
- Peer: Emergency Response directly @mentions Ground Ops → "Prepare runway 4L, crash/fire standby"
- Peer: Emergency Response @mentions Weather Analyst → "Weather confirmed clear for emergency approach"
- To Human: "Emergency declared. UAL999 priority. Cleared descend to FL100. Runway 4L prepared. Weather clear."

---

## 10. Frontend Architecture (Reviewed and Verified)

### Radar-Phile View (Canvas + CSS)
- **Canvas rendering**: `useRef` + `requestAnimationFrame` + Zustand `subscribe()` to a ref (zero React re-renders for position updates)
- **Sweep line**: CSS `conic-gradient` div overlay on top of canvas (NOT drawn in canvas — 15 min to implement vs hours)
- **Range rings**: Drawn in canvas (simple `arc()` calls)
- **Aircraft blips**: Drawn in canvas with color coding
- **Hover/click**: Canvas hit-testing (O(n) with n<30, sub-microsecond). Cache pixel positions in ref.
- **Tooltip overlay**: Custom absolutely-positioned `<div>` with shadcn CSS classes (NOT Radix Tooltip over Canvas — won't work)
- **No AircraftBlip.tsx component** — Canvas draws everything, no React component per aircraft

### Zustand Store
- Single store with `subscribeWithSelector` middleware
- Separate concerns via selectors: `aircraft` (high-freq), `alerts` (low-freq), `agents` (low-freq)
- `setAircraftBatch()` for batch WebSocket updates (replaces entire Map, avoids N state updates)

### WebSocket Architecture
- FastAPI pushes updates to React at **1 Hz max** (throttled, not every data update)
- `asyncio.Queue(maxsize=1)` drops old messages if consumer is slow
- Frontend reconnects automatically on disconnect (Render free tier cold starts)
- `wss://` from Vercel to Render — no CORS issues (WebSocket ignores CORS)

### Cut Order (if time runs short)
1. Live mode toggle (ship simulated only)
2. Agent chat log (simple list instead of rich ScrollArea)
3. Heading vectors on blips (just render dots)
4. Hover tooltip (click-only)
5. Range ring labels (just circles)

---

## 11. Audit & Traceability (Track 3 Requirement)

### Persistent Audit Log (beyond Band's 24h retention)
- FastAPI stores every agent message and event in local SQLite
- Schema: `timestamp, agent_name, event_type, content, metadata_json`
- Frontend displays this as a chronological event timeline
- This is the "traceability" judges want for Track 3

### Structured Decision Records
Every agent decision follows this protocol:
1. Agent receives trigger → emits `thought` event (what it's reasoning about)
2. Agent processes data → emits `task` event with structured `metadata` (what action, what data)
3. Agent communicates result → sends `thenvoi_send_message` with structured advisory
4. Coordinator reviews → challenges recommendation with other agents
5. Only validated recommendations reach the human controller

---

## 12. Day-by-Day Plan (Updated)

| Day | Target | Definition of Done |
|---|---|---|
| **Day 1** | Data + Backend | FastAPI serving `/data/simulated` with 20 aircraft in canonical format. OpenSky client working. AWC proxy working. SQLite audit log writing. **6 Band agents registered. All agent_ids and api_keys in .env. Room created with all agents as participants.** |
| **Day 2** | 3 Core Agents | Coordinator + Conflict Detector + Weather Analyst in Band room. @mention routing works. Peer-to-peer @mentions work. Event-driven LLM invocation only. |
| **Day 3** | Frontend v1 | React + shadcn + Canvas radar (rAF + ref pattern) + CSS sweep + Zustand + WebSocket |
| **Day 4** | Integration | End-to-end: mock data → Band room → agents → events → FastAPI subscriber → WebSocket → frontend. Review loop visible. |
| **Day 5** | Remaining 2 agents | Ground Ops + Emergency Response. 7700 trigger with dynamic recruitment works. Peer-to-peer: Emergency→Ground, Weather→Conflict. |
| **Day 6** | Polish + 3 scenarios | All 3 pre-defined scenarios run reliably. Radar-phile polished. 7700 blinks white. Audit timeline visible. |
| **Day 7** | Submission | Video (3-5 min), slides, README, Vercel + Render deployed. |

---

## 13. Risk Register (Updated)

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | OpenSky blocks cloud IP | Cannot show live mode | Simulated mode is default; live mode is bonus |
| 2 | Band SDK issues | Agents don't communicate | Fallback to direct REST API calls |
| 3 | LLM rate limits | Agents stop responding | Event-driven invocation (10-15 calls/demo). NVIDIA NIM as dev fallback. AI/ML API + Featherless credits for demo. |
| 4 | React Canvas performance | Radar view choppy | rAF + ref pattern (zero React re-renders). Limit to 20-30 blips. 1 Hz update rate. |
| 5 | 5 agents too many for 7 days | Incomplete submission | Day 4 checkpoint: if 3 agents not working, submit with 3. |
| 6 | CrewAI + PydanticAI venv conflict | Install fails | Each agent has its own venv. Separate `uv add` per agent directory. |
| 7 | AWC CORS blocks frontend | Weather data not loading | All external API calls go through FastAPI backend. Frontend never calls AWC directly. |
| 8 | Band 24h retention loses history | No audit trail | SQLite persistent log from day 1. Frontend reads from SQLite, not Band history. |
| 9 | Partner credits exhausted mid-demo | Agents can't call LLMs | Switch to OpenRouter/NIM free tiers. Use event-driven invocation to minimize calls. |
| 10 | Render free tier cold start | WebSocket drops | Frontend auto-reconnects. Pre-warm before demo. |

---

## 14. Demo Script (3-5 min video)

**0:00-0:30 — The Problem**
> "Air traffic controllers handle 400-500 hours of overtime annually. 60-80% report catching themselves dozing off during midnight shifts. In 2023, a FedEx plane came within 170 feet of a Southwest flight in Austin — the controller was working three positions at once. ATC Guardian doesn't replace controllers — it gives them a team of AI specialists watching every angle."

**0:30-1:30 — Scenario A: Converging Courses**
- Radar-phile view shows 20 aircraft
- Conflict Detector identifies converging pair
- Peer-to-peer: Conflict Detector asks Weather Analyst for conditions
- Coordinator reviews and validates
- Alert presented to controller with full reasoning trace

**1:30-2:30 — Scenario C: Emergency (7700)**
- UAL999 squawks 7700
- Emergency Response dynamically recruited
- Peer-to-peer: Emergency tells Ground Ops to prepare runway
- Full audit timeline visible
- Controller sees structured recommendation

**2:30-3:00 — Architecture & Band**
- Band room screenshot showing all agents
- Event timeline (traceability)
- Agent-to-agent @mentions (collaboration)
- Cross-framework: LangGraph + CrewAI + Pydantic AI + Anthropic

**3:00-3:30 — Close**
> "ATC Guardian: Multi-agent decision support where review, traceability, and human authority are built in — not bolted on."

---

## 15. Business Value Data Points

- **FAA data**: ATC listed as cause/contributing factor in 135+ accidents/incidents (2010-2025, NTSB reports)
- **Fatigue**: 60-80% of controllers report near-dozing (FAA CAMI research)
- **Overtime**: 400-500 hours overtime annually (NTSB investigation reports)
- **Near-miss**: 3,400+ situations where "workload" was primary human factor (ASRS reports)
- **Staffing**: 600+ reports listing "staffing" as problem
- **Cognitive swing**: Traffic volume from 12.5 aircraft/hour (1 AM) to 198 (11 AM) — 16x workload swing in a single shift

---

---

## Appendix A: Environment Variables

```env
# === Band Platform ===
BAND_AGENT_ID_COORDINATOR=
BAND_API_KEY_COORDINATOR=
BAND_AGENT_ID_CONFLICT_DETECTOR=
BAND_API_KEY_CONFLICT_DETECTOR=
BAND_AGENT_ID_WEATHER_ANALYST=
BAND_API_KEY_WEATHER_ANALYST=
BAND_AGENT_ID_GROUND_OPS=
BAND_API_KEY_GROUND_OPS=
BAND_AGENT_ID_EMERGENCY_RESPONSE=
BAND_API_KEY_EMERGENCY_RESPONSE=
BAND_AGENT_ID_SYSTEM_INGEST=
BAND_API_KEY_SYSTEM_INGEST=
BAND_ROOM_ID=

# === LLM Providers ===
OPENROUTER_API_KEY=               # Dev/testing (50 free/day)
NVIDIA_NIM_API_KEY=               # Dev/testing (40 RPM free)
AIML_API_KEY=                     # Primary for Conflict Detector + Emergency Response
FEATHERLESS_API_KEY=              # Primary for Weather Analyst + Ground Ops

# === Data Sources ===
OPENSKY_CLIENT_ID=                # Free account at opensky-network.org
OPENSKY_CLIENT_SECRET=            # OAuth2 credentials

# === Frontend ===
VITE_WS_URL=ws://localhost:8000/ws

# === LLM Provider Switch (for Coordinator) ===
LLM_PROVIDER=openrouter           # openrouter | nvidia_nim | aiml
```

---

## Appendix B: Venv Management

Each agent has its own directory with its own `pyproject.toml`:

```
agents/coordinator/pyproject.toml       → band-sdk[langgraph]
agents/conflict_detector/pyproject.toml → band-sdk[pydantic-ai]
agents/weather_analyst/pyproject.toml   → band-sdk[crewai]
agents/ground_ops/pyproject.toml        → band-sdk[langgraph]
agents/emergency_response/pyproject.toml → band-sdk[openai]
```

**Setup script** (`scripts/setup.sh`):
```bash
for agent in coordinator conflict_detector weather_analyst ground_ops emergency_response; do
  cd agents/$agent && uv venv && uv sync && cd ../..
done
cd backend && uv venv && uv sync && cd ..
cd frontend && npm install && cd ..
```

**Start script** (`scripts/start-all.sh`):
```bash
# Terminal 1: Backend
cd backend && uv run python -m app.main &

# Terminal 2-6: Agents
for agent in coordinator conflict_detector weather_analyst ground_ops emergency_response; do
  cd agents/$agent && uv run python agent.py &
  cd ../..
done

# Terminal 7: Frontend
cd frontend && npm run dev &
```

---

## Appendix C: LLM Provider Configuration

### CrewAI + Featherless AI
```python
from crewai import LLM
llm = LLM(
    model="openai/meta-llama/Meta-Llama-3-8B-Instruct",
    base_url="https://api.featherless.ai/v1",
    api_key=os.getenv("FEATHERLESS_API_KEY"),
)
```

### LangGraph + OpenRouter/NIM
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    model="meta-llama/llama-3.3-70b-instruct:free",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)
```

### Pydantic AI + AI/ML API
```python
from pydantic_ai import Agent
agent = Agent(
    model="gpt-4o",  # via AI/ML API
    model_settings={"base_url": "https://api.aimlapi.com/v1"},
    api_key=os.getenv("AIML_API_KEY"),
)
```

### OpenAI Adapter + AI/ML API (Emergency Response)
```python
from openai import OpenAI
client = OpenAI(
    api_key=os.getenv("AIML_API_KEY"),
    base_url="https://api.aimlapi.com/v1",
)
```

### Coordinator LLM Switching
Set `LLM_PROVIDER` env var to `openrouter`, `nvidia_nim`, or `aiml` to switch between providers without code changes.

---

## Appendix D: Demo Recording

**Tool**: [OBS Studio](https://obsproject.com/) (free, open-source)
**Setup**: Record browser window (1920×1080) with the ATC Guardian dashboard
**Export**: MP4, H.264, 5-10 Mbps
**Alternative**: Loom (free tier, 25 min limit) for quicker iteration
**Script**: Follow Section 14 demo script verbatim

---

## 16. Review Log

| Loop | Date | Issues Found | Issues Verified | Fixes Applied |
|---|---|---|---|---|
| 1 | Pre-hackathon | 22 issues across 4 domains | 17 verified real, 5 confirmed OK | All 17 fixes applied in v2 |
| 2 | Pre-hackathon | 14 issues (1 CRITICAL, 3 HIGH) | 1 CRITICAL (AI/ML API ≠ Anthropic adapter), 3 HIGH | All 4 fixes applied in v3 |
| 3 | Pre-hackathon | 10 issues (2 CRITICAL, 3 HIGH) | 2 CRITICAL (no Python OpenAI adapter, WebSocket delivery broken), 3 HIGH (no structured output, state machine overkill, no prompts) | All 5 fixes applied in v4 |

---

## Appendix: Key Verified Facts

| Fact | Source | Verified |
|---|---|---|
| `thenvoi_send_event` only supports 5 message types | SDK Reference, OpenAPI spec | ✅ |
| Band free tier: 24h data retention | Pricing page | ✅ |
| Humans see all messages in room | Chat Rooms docs, API Introduction | ✅ |
| Agent auto-receives @mentioned messages | SDK Overview, WebSocket channels | ✅ |
| Sibling agents can add each other without contacts | Chat Rooms docs, Core Concepts | ✅ |
| OpenSky: 4,000 credits/day free account | OpenSky REST API docs | ✅ |
| OpenSky: 1 credit per JFK-bbox call | OpenSky REST API docs | ✅ |
| AWC: no CORS | AWC Data API docs | ✅ |
| AWC: 100 req/min | AWC Data API docs | ✅ |
| OpenRouter: 50 free req/day | OpenRouter pricing, Zendesk | ✅ |
| NVIDIA NIM: ~40 RPM, free dev tier | NVIDIA forums, docs | ✅ |
| NVIDIA NIM: OpenAI-compatible | NVIDIA docs | ✅ |
| `opensky-api` supports OAuth2 TokenManager | GitHub README, Python docs | ✅ |
| Unit conversions: m→ft ×3.28, m/s→kt ×1.94 | Physics constants | ✅ |
