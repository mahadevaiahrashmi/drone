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
| `error` | str? | Error from last action |
| `score` | float | Current grader score |
| `task_name` | str | Active task |

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
# Build
docker build -t drone-env:latest -f Dockerfile .

# Run server locally
uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

# Run inference
DRONE_TASK=easy python inference.py
```

## Project Structure

```
drone/
├── __init__.py           # Module exports
├── models.py             # DroneAction, DroneObservation, HouseInfo
├── client.py             # DroneEnv client (EnvClient subclass)
├── inference.py          # LLM agent inference script
├── openenv.yaml          # OpenEnv manifest
├── Dockerfile            # Container build
├── pyproject.toml        # Dependencies
├── DECISIONS.md          # Design decisions log
├── ADR-001-grading-formula.md  # Grading architecture decision
└── server/
    ├── __init__.py
    ├── drone_environment.py  # Core environment + grader
    └── app.py                # FastAPI application
```
