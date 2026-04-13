---
title: Drone Delivery Environment
emoji: 🚁
colorFrom: gray
colorTo: blue
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
---

# Drone Delivery Environment

A delivery drone simulation where an AI agent picks up packages at a warehouse and delivers them to houses on a 2D grid. Tasks test route optimization — finding the shortest path through delivery points.

## Tasks

| Task | Houses | Time Limit | Challenge |
|------|--------|------------|-----------|
| easy | 2 | None | 2 possible routes |
| medium | 3 | None | 6 possible routes |
| hard | 4 | 15 steps | 24 possible routes + time pressure |

## Grading (0.0–1.0)

```
score = (optimal_distance / actual_distance) * (delivered / total)
```

- Perfect route → 1.0
- All delivered but 2x optimal distance → 0.5
- Half delivered optimally → 0.5
- Hard mode: 50% penalty if steps exceed limit

## Quick Start

```python
from drone import DroneAction, DroneEnv

client = DroneEnv.from_docker_image("drone-env:latest")
try:
    result = client.reset()  # defaults to "easy" task

    # Pick up all packages at warehouse
    result = client.step(DroneAction(action_type="pick_up"))

    # Fly to first house
    result = client.step(DroneAction(action_type="fly_to", x=3, y=4))

    # Deliver
    result = client.step(DroneAction(action_type="deliver"))

    # Fly to second house
    result = client.step(DroneAction(action_type="fly_to", x=6, y=0))

    # Deliver
    result = client.step(DroneAction(action_type="deliver"))

    print(f"Score: {result.observation.score}")
    print(f"Done: {result.done}")
finally:
    client.close()
```

## Actions

| Action | Fields | Description |
|--------|--------|-------------|
| `fly_to` | `x`, `y` (int) | Fly to coordinates |
| `pick_up` | — | Pick up all packages at warehouse (must be within radius 1) |
| `deliver` | — | Deliver to nearest undelivered house within radius 1 |

Invalid actions return an error message in the observation but don't crash the environment.

## Observation

| Field | Type | Description |
|-------|------|-------------|
| `drone_x`, `drone_y` | int | Current drone position |
| `packages_carried` | int | Packages currently held |
| `packages_delivered` | int | Packages delivered so far |
| `total_packages` | int | Total to deliver |
| `houses` | list | Each house: name, x, y, delivered status |
| `warehouse_x`, `warehouse_y` | int | Warehouse position |
| `distance_traveled` | float | Total Euclidean distance flown |
| `steps_taken` | int | Actions taken |
| `max_steps` | int? | Step limit (hard mode only) |
| `error` | str? | Human-readable error from last action |
| `error_details` | dict? | Structured error: `{code, message, valid, got?, suggestion?}` |
| `valid_actions` | list[str] | Action grammar on the wire: `["fly_to","pick_up","deliver"]` |
| `score` | float | Current grader score |
| `task_name` | str | Active task |

## Invalid-Input Handling (three layers)

Invalid inputs are blocked at the layer closest to the source:

| Layer | Audience | Mechanism |
|-------|----------|-----------|
| Pydantic model | Both | `action_type: Literal["fly_to","pick_up","deliver"]` — typos raise `ValidationError` at parse time (HTTP 422) |
| HTTP `/step` | LLMs, scripts | Runtime failures set `error_details = {code, message, valid, got?, suggestion?}`; **invalid actions do not consume a step** from the hard-mode budget |
| Gradio Custom tab | Humans | Dropdowns for `task` and `action_type`, number inputs for `x`/`y` — invalid values are structurally unrepresentable |

Error codes you may see: `invalid_action_type` (with `suggestion` from `difflib`), `missing_coordinates`, `not_at_warehouse`, `nothing_to_pick_up`, `no_packages_carried`, `no_house_in_range`.

## Task Maps

### Easy
```
Warehouse: (0, 0)
House A:   (3, 4)
House B:   (6, 0)
```

### Medium
```
Warehouse: (0, 0)
House A:   (2, 4)
House B:   (5, 1)
House C:   (8, 5)
```

### Hard
```
Warehouse: (0, 0)
House A:   (3, 6)
House B:   (7, 2)
House C:   (10, 8)
House D:   (4, 1)
Max steps: 15
```

## Running

```bash
# Install dependencies (first time only)
uv sync

# Run server locally (no Docker required)
uv run uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

# Run end-to-end tests (direct Python, no HTTP, no Docker)
uv run python test_e2e.py

# Run inference against a live server
DRONE_TASK=easy uv run python inference.py

# Build and run via Docker (optional)
docker build -t drone-env:latest -f Dockerfile .
docker run -p 8000:8000 drone-env:latest
```

## Visualization (Gradio Custom Tab)

With the server running and `ENABLE_WEB_INTERFACE=true`, open
`http://localhost:8000/web` and switch to the **Drone Visualization** tab.
You'll see a live 2D grid showing:

- **W** (blue) — warehouse
- **A/B/C/D** (red) — pending houses, (green) — delivered
- **D** (yellow) — the drone

The Custom tab includes its own **Reset / Step / Refresh** controls with
dropdowns for `task` and `action_type` and number inputs for `x`/`y`, so you
can drive the environment end-to-end without leaving the viz tab and without
typing an invalid value. You can still use the **Playground** tab for raw
JSON interaction if preferred.

See [TUTORIAL.md](./TUTORIAL.md) for a full walkthrough of how this
environment was built — intended as a teaching reference for anyone writing
their own OpenEnv environment.

## Project Structure

```
drone/
├── __init__.py                 # Module exports
├── models.py                   # DroneAction, DroneObservation, HouseInfo
├── client.py                   # DroneEnv client (EnvClient subclass)
├── inference.py                # LLM agent inference script
├── test_e2e.py                 # End-to-end tests (direct Python, no Docker)
├── openenv.yaml                # OpenEnv manifest
├── Dockerfile                  # Container build
├── pyproject.toml              # Dependencies
├── README.md                   # This file
├── TUTORIAL.md                 # Step-by-step build guide
├── DECISIONS.md                # Design decisions log
├── ADR-001-grading-formula.md  # Grading architecture decision
└── server/
    ├── __init__.py
    ├── drone_environment.py    # Core environment + grader
    ├── gradio_ui.py            # Custom Drone Visualization tab
    └── app.py                  # FastAPI application
```
