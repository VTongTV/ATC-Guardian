# AGENTS.md — Development Directives for ATC Guardian

> **This document is MANDATORY.** Every line of code, every commit, every decision must comply with these directives. No exceptions.

---

## 1. Core Philosophy: Human-Consulted Development

**The human is the senior engineer. You are the junior.**

- **ASK BEFORE BUILDING.** Never assume a design decision. If the plan doesn't specify it explicitly, ask the human.
- **CONFIRM BEFORE COMPLETING.** After implementing any non-trivial change, show the human what you did before moving on.
- **ESCALATE ON AMBIGUITY.** If you're unsure about ANYTHING — a library API, a data format, a business rule — stop and ask the human. Do not guess.
- **WEB SEARCH FIRST.** Before using any library, API, or framework feature you haven't personally verified in the last 30 days, search the web for the current documentation. Never rely on cached knowledge.
- **NO PLACEHOLDER CODE.** Zero tolerance. No `TODO`, no `pass`, no `# implement later`, no mock returns pretending to be real, no `print("placeholder")`. Every function must work or not exist. If a function isn't ready, don't write it.
- **NO DEMO CODE.** No hardcoded "Hello World" routes, no fake data masquerading as real, no `return {"status": "ok"}` stubs. If it's not production-quality, it doesn't get committed.

---

## 2. Virtual Environment Rules

**Every Python execution MUST use a venv. No exceptions.**

### Rule 2.1: Always Create a Venv
```bash
# Before ANY Python work:
uv venv
# or for a specific agent:
cd agents/coordinator && uv venv && uv sync
```

### Rule 2.2: Always Activate Before Running
```bash
# Before running any Python script:
.venv\Scripts\activate  # Windows
# Then run your script
python agent.py
```

### Rule 2.3: Never Use System Python
- `python` must always resolve to the venv Python
- If `which python` or `Get-Command python` shows system Python, STOP and activate venv
- If in doubt: `uv run python script.py` — this always uses the project's venv

### Rule 2.4: Separate Venvs Per Agent
Each agent directory has its own `pyproject.toml` and its own `.venv/`:
```
agents/coordinator/.venv/          # band-sdk[langgraph]
agents/conflict_detector/.venv/    # band-sdk[pydantic-ai]
agents/weather_analyst/.venv/      # band-sdk[crewai]
agents/ground_ops/.venv/           # band-sdk[langgraph]
agents/emergency_response/.venv/   # band-sdk[langgraph]
```

### Rule 2.5: Never Install Globally
- Never `pip install` without a venv active
- Never `uv add` without a `pyproject.toml` in the current directory
- If you need a package, add it to the correct `pyproject.toml` first

---

## 3. Web Search & Verification Rules

**Search before you code. Verify before you commit.**

### Rule 3.1: Verify Library APIs Before Use
Before calling any library function that you haven't personally tested:
1. Search the official documentation
2. Read the current API signature (params, return types, exceptions)
3. Check for breaking changes in recent versions
4. If the docs are unclear, search for real usage examples

### Rule 3.2: Verify Band SDK Behavior
Band is a new platform. Before assuming any SDK behavior:
1. Check `docs.band.ai` for the current documentation
2. Verify adapter signatures against the SDK reference
3. Test in a minimal script before integrating into agent code
4. If behavior doesn't match docs, report to the human immediately

### Rule 3.3: Verify External API Contracts
Before integrating OpenSky, AWC, OpenRouter, NVIDIA NIM, AI/ML API, or Featherless:
1. Fetch the current API documentation
2. Verify the endpoint URL, request format, and response format
3. Test with a simple `curl` or `httpx` call
4. Document any discrepancies from the plan

### Rule 3.4: No Assumed Knowledge
- Don't assume LangChain's `ChatOpenAI` accepts `base_url` — verify it
- Don't assume CrewAI's `LLM` class supports Featherless — verify it
- Don't assume Band's `thenvoi_send_message` format — verify it
- Don't assume OpenSky returns meters — verify it
- When in doubt: search, read, test, then code

---

## 4. Clean Code Rules

**Every line must earn its place. Every name must reveal intent.**

### Rule 4.1: Naming
- Variables: `snake_case`, descriptive, no abbreviations (`aircraft_state`, not `ac_st`)
- Functions: `snake_case`, verb-first (`compute_cpa`, not `cpa`)
- Classes: `PascalCase`, noun (`ConflictDetector`, not `Detector`)
- Constants: `UPPER_SNAKE_CASE` (`SEPARATION_MINIMUM_NM`, not `min_sep`)
- Files: `snake_case.py` (`conflict_detector.py`, not `cd.py`)

### Rule 4.2: Functions
- One function = one responsibility
- Max 20 lines per function. If longer, extract helper functions.
- Every function has a docstring explaining what it does, parameters, and return value
- No nested conditionals deeper than 2 levels — extract named helper functions

### Rule 4.3: Type Hints
- All Python functions must have full type hints (params + return type)
- All TypeScript functions must have full type annotations
- Use Pydantic models for all data structures — no raw dicts
- Use `TypedDict` only when Pydantic is unavailable

### Rule 4.4: Error Handling
- Never catch `Exception` broadly. Catch specific exceptions.
- Never silently swallow errors. Log them at minimum.
- Every external API call must have a `try/except` with a meaningful error message
- Every external API call must have a timeout
- Fail loudly and early. Silent failures are the worst kind.

### Rule 4.5: Imports
- Standard library first, then third-party, then local — separated by blank lines
- No wildcard imports (`from typing import *`)
- No unused imports — remove immediately
- Use absolute imports within the project (`from shared.models import AircraftState`)

### Rule 4.6: No Magic Numbers
- `5` → `SEPARATION_MINIMUM_NM = 5`
- `7700` → `EMERGENCY_SQUAWK_CODE = "7700"`
- `1500` → `EMERGENCY_DESCENT_RATE_FPM = 1500`
- Define constants at module level or in a shared constants file

### Rule 4.7: No Dead Code
- No commented-out code blocks. Delete them. Git remembers.
- No unreachable code paths
- No unused variables
- No debug `print()` statements — use `logging` module

### Rule 4.8: Docstrings
Every module, class, and public function must have a docstring:
```python
def compute_cpa(aircraft_a: AircraftState, aircraft_b: AircraftState) -> CPAResult:
    """Compute closest point of approach between two aircraft.

    Args:
        aircraft_a: First aircraft state vector.
        aircraft_b: Second aircraft state vector.

    Returns:
        CPAResult with min_distance_nm, time_to_cpa_seconds, and relative_bearing.

    Raises:
        ValueError: If both aircraft are at the same position.
    """
```

---

## 5. Commit Rules

**Small commits. Frequent commits. Meaningful commits.**

### Rule 5.1: Commit On Every Minor Change
- Changed one function? Commit.
- Added one constant? Commit.
- Fixed one typo? Commit.
- Updated one prompt? Commit.
- Changed one CSS class? Commit.
- No batch commits. No "misc changes" commits.

### Rule 5.2: Commit Message Format
```
type(scope): description

[optional body explaining WHY, not WHAT]
```

Types:
- `feat`: New feature (new agent, new endpoint, new component)
- `fix`: Bug fix
- `refactor`: Code restructure without behavior change
- `docs`: Documentation only
- `style`: Formatting, whitespace, naming
- `test`: Adding or updating tests
- `chore`: Build, config, dependencies

Scopes:
- `coordinator`, `conflict-detector`, `weather-analyst`, `ground-ops`, `emergency-response`
- `backend`, `frontend`, `shared`, `ml`, `data`

Examples:
```
feat(coordinator): add @mention dispatch to conflict detector
fix(backend): handle OpenSky 429 rate limit with exponential backoff
refactor(ml): extract trajectory extrapolation into shared module
docs(PLAN): add REST polling architecture diagram
style(frontend): rename radar component to RadarView
test(conflict-detector): add CPA calculation unit tests
chore(deps): add band-sdk[langgraph] to coordinator pyproject.toml
```

### Rule 5.3: Never Commit Broken Code
- Every commit must leave the project in a working state
- If tests exist, they must pass before committing
- No `WIP` commits. Finish the change, test it, then commit
- If you can't finish, stash or branch — don't commit half-work

### Rule 5.4: Never Commit Secrets
- `.env` is in `.gitignore`. Never add API keys to code.
- `agent_config.yaml` is in `.gitignore`. Never commit Band credentials.
- If you accidentally commit a secret, tell the human IMMEDIATELY

### Rule 5.5: Commit Before Risky Changes
Before refactoring, before changing a dependency, before modifying shared models:
1. Commit the current working state
2. Make the change
3. Test the change
4. Commit the change
5. If it breaks, `git revert` to the last working state

---

## 6. Development Workflow

### Rule 6.1: Read → Search → Ask → Code
For every new task:
1. **Read** the plan (PLAN.md) and this file (AGENTS.md)
2. **Search** the web for current documentation of any library you'll use
3. **Ask** the human if anything is unclear, ambiguous, or not specified
4. **Code** only after steps 1-3 are complete

### Rule 6.2: Test After Every Change
- After writing a function, test it immediately — don't wait
- Use `uv run pytest tests/test_ml.py -k test_compute_cpa` for targeted tests
- For manual testing, use `uv run python -m app.main` from the backend directory
- If you can't test it, don't commit it

### Rule 6.3: Show Before Moving On
After completing any non-trivial change:
1. Run the relevant test or demo
2. Show the human the output
3. Ask: "Does this look correct?"
4. Wait for confirmation before proceeding

### Rule 6.4: No Parallel Implementation
Work on one thing at a time. Complete it. Test it. Commit it. Then move on.
- Don't start the frontend before the backend data layer works
- Don't start the next agent before the current one is tested
- Don't refactor while adding features

### Rule 6.5: Checkpoint With Human
After every major milestone (agent working, scenario running, etc.):
1. Demo it to the human
2. Get explicit approval
3. Then proceed to the next milestone

---

## 7. Agent Implementation Directives

### Rule 7.1: Start With Data Layer
Build order:
1. `shared/models.py` — canonical data models (AircraftState, ConflictAdvisory, etc.)
2. `data/generator.py` — mock data generator
3. `ml/trajectory.py` + `ml/conflict.py` — ML functions (pure, no LLM needed)
4. `backend/` — FastAPI server
5. Then agents, then frontend

### Rule 7.2: Test ML Without LLM
The ML layer (trajectory prediction, CPA calculation) is pure math. Test it with:
```python
def test_cpa_converging():
    a = AircraftState(callsign="UAL123", latitude=40.7, longitude=-73.8, altitude_ft=34000, heading_deg=45, speed_kts=450, ...)
    b = AircraftState(callsign="DAL456", latitude=40.71, longitude=-73.79, altitude_ft=34000, heading_deg=225, speed_kts=460, ...)
    result = compute_cpa(a, b)
    assert result.time_to_cpa_seconds > 0
    assert result.min_distance_nm < 5.0
```

### Rule 7.3: Each Agent Is Independent
- Each agent runs in its own process with its own venv
- Each agent has its own `pyproject.toml` with only the deps it needs
- Each agent reads its own Band credentials from environment variables
- Agents communicate ONLY through Band — no shared files, no Redis, no queues

### Rule 7.4: System Prompts Are Code
- System prompts are stored in `prompts.py` files, not in string literals scattered in agent code
- Prompts are version-controlled and reviewed
- Every prompt change is a commit
- Prompts must specify: role, input format, output format, decision rules, communication protocol

### Rule 7.5: Event-Driven LLM Invocation
- Agents do NOT call LLMs on every data update
- Rule-based pre-filters decide whether an LLM call is needed:
  - CPA < 5nm → Conflict Detector invokes LLM
  - SIGMET polygon overlaps flight path → Weather Analyst invokes LLM
  - Squawk 7700 → Emergency Response invokes LLM
  - No condition met → No LLM call. Log and skip.
- This is CRITICAL for staying within free tier limits

---

## 8. Human Checkpoint Schedule

| Checkpoint | When | What to Show Human |
|---|---|---|
| **CP1** | After shared models + ML | Unit test results for CPA calculation |
| **CP2** | After FastAPI data layer | `GET /data/simulated` returns 20 aircraft in browser |
| **CP3** | After first agent (Coordinator) | Coordinator responds to @mention in Band room |
| **CP4** | After 3 agents | 3 agents exchange @mentions in Band room |
| **CP5** | After frontend v1 | Radar-phile view renders aircraft blips |
| **CP6** | After full integration | End-to-end: data → agents → events → radar display |
| **CP7** | After 5 agents | All 5 agents working, 7700 triggers emergency |
| **CP8** | After 3 scenarios | All scenarios run reliably |
| **CP9** | Before submission | Full demo video, slides, deployed URL |

---

## 9. Forbidden Patterns

### NEVER:
- `# TODO` — if it's not done, don't commit it
- `pass` — if the function body is empty, the function shouldn't exist
- `print()` — use `logging.info()` or `logging.debug()`
- `except Exception` — catch specific exceptions
- `import *` — explicit imports only
- Hardcoded secrets — use environment variables
- `return {"status": "ok"}` — real endpoints return real data
- Mock data in production code paths — mock data is in `data/generator.py` only
- `time.sleep()` in async code — use `asyncio.sleep()`
- Global mutable state — use dependency injection or Zustand stores
- Copy-pasted code — extract shared functions into `shared/`
- Uncommitted changes overnight — commit before you sleep

---

## 10. File Naming Convention

| Pattern | Example | Purpose |
|---|---|---|
| `agent.py` | `agents/coordinator/agent.py` | Main agent entry point |
| `prompts.py` | `agents/coordinator/prompts.py` | System prompts |
| `models.py` | `shared/models.py` | Pydantic data models |
| `client.py` | `backend/app/services/opensky_client.py` | External API client |
| `test_*.py` | `tests/test_ml.py` | Test files |
| `*.css` | `frontend/src/styles/radar.css` | Stylesheets |
| `*.tsx` | `frontend/src/components/RadarView.tsx` | React components |
| `*.ts` | `frontend/src/stores/atcStore.ts` | TypeScript modules |

---

## 11. Environment Variable Access

All configuration through environment variables. Never hardcode:

```python
# CORRECT
import os
api_key = os.getenv("BAND_API_KEY_COORDINATOR")

# WRONG
api_key = "band_u_abc123"  # NEVER DO THIS
```

```typescript
// CORRECT
const wsUrl = import.meta.env.VITE_WS_URL;

// WRONG
const wsUrl = "ws://localhost:8000/ws";  // NEVER DO THIS
```

---

## 12. Review Checklist Before Every Commit

- [ ] Does this change work? (tested)
- [ ] Does this change follow clean code rules? (naming, types, docstrings)
- [ ] Does this change have no placeholder code? (no TODO, pass, stubs)
- [ ] Does this change have no secrets? (no API keys, passwords)
- [ ] Is the commit message descriptive? (type(scope): description)
- [ ] Is this change small enough? (one logical change per commit)
- [ ] Did I consult the human on any design decisions in this change?
- [ ] Did I verify any library APIs I'm using in this change?
