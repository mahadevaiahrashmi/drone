# Building Your Own OpenEnv Environment — A Tutorial

A step-by-step guide for engineering students to build an OpenEnv environment from scratch, using this drone delivery project as a worked example.

## Who is this for?

You're a CS/engineering student who knows Python and basic HTTP. You want to build an environment where an AI agent (like an LLM) performs a task, and you need to score how well it did.

## What is OpenEnv?

OpenEnv is a framework by Meta that standardizes how AI agents talk to environments over HTTP. Think of it as a common language:

- The **environment** is a program that simulates a world. It has state (where things are), rules (what actions change the state), and a scoring function (how well did the agent do).
- The **agent** is the AI (often an LLM) that decides what to do.
- OpenEnv handles the plumbing: HTTP server, WebSocket sessions, schemas, Docker packaging.

You focus on *your simulation*. OpenEnv handles *everything else*.

## The Mental Model: Reset → Step → Step → ... → Done

Every OpenEnv environment follows the same loop:

```
reset()   → initial observation          (agent sees the starting state)
step(a1)  → observation, reward, done    (agent takes action, world responds)
step(a2)  → observation, reward, done
...
step(aN)  → done=True                    (episode over, final score computed)
```

You define three things:
1. **Action** — what the agent can do (data class)
2. **Observation** — what the agent sees (data class)
3. **Environment** — the simulation logic + grader (Python class)

## Project Layout

A minimal OpenEnv environment has this structure:

```
my_env/
├── __init__.py           # Exports: MyEnv, MyAction, MyObservation
├── models.py             # Action + Observation dataclasses (Pydantic)
├── client.py             # Thin client for agents to connect
├── openenv.yaml          # Environment manifest
├── pyproject.toml        # Python dependencies
├── Dockerfile            # Container build
└── server/
    ├── __init__.py
    ├── my_environment.py # THE SIMULATION + GRADER (the important file)
    └── app.py            # FastAPI wiring (usually boilerplate)
```

In this drone project, all of this lives under `drone/`. The file you'll spend 90% of your time on is `server/drone_environment.py`.

## Step-by-Step: Build Your Own

### Step 1 — Decide your mental model

Before writing code, answer these questions **on paper**:

1. **What is the world?** Grid? Graph of locations? Text-based? For drone: 2D integer coordinate space with fixed warehouse and houses.
2. **What are the actions?** Keep them as high-level as possible. LLMs hate fiddly low-level actions. Drone uses `fly_to(x, y)`, `pick_up()`, `deliver()` — three semantic verbs.
3. **What does the agent see each turn?** Drone sends position, packages carried, list of houses with delivered status, distance traveled, current score.
4. **What defines "done"?** Drone: all packages delivered.
5. **What is the grader formula?** Must be deterministic (same inputs → same output). Drone: `(optimal_distance / actual_distance) × (delivered / total)`, clamped strictly inside `(0, 1)`.

Write these down in a `DECISIONS.md` file so future-you remembers why.

### Step 2 — Define Action and Observation (`models.py`)

Start simple. Use Pydantic via OpenEnv's base classes:

```python
from openenv.core.env_server.types import Action, Observation
from pydantic import Field

class DroneAction(Action):
    action_type: str = Field(..., description="fly_to, pick_up, or deliver")
    x: int | None = Field(default=None)
    y: int | None = Field(default=None)

class DroneObservation(Observation):
    drone_x: int = Field(default=0)
    drone_y: int = Field(default=0)
    packages_carried: int = Field(default=0)
    score: float = Field(default=0.0)
    error: str | None = Field(default=None)
    # ... everything the agent needs to see
```

**Key rules:**
- Every field needs a type and a default (or a Field marker).
- The `error` field is critical: when an action fails, set this instead of raising an exception. Agents can read it and recover.
- Don't return raw Python objects the agent can't serialize.

### Step 3 — Write the Environment (`server/drone_environment.py`)

This is where the logic lives. Your class inherits from `Environment`:

```python
from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State
from uuid import uuid4

class DroneEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True  # let multiple clients run in parallel

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)
        # ... your internal state (positions, inventory, etc.)

    def reset(self, task: str = "easy") -> DroneObservation:
        """Called once at episode start. Reset all state."""
        # set up the world
        return self._make_observation()

    def step(self, action: DroneAction) -> DroneObservation:
        """Called once per agent action."""
        self._state.step_count += 1
        # dispatch on action_type
        if action.action_type == "fly_to":
            self._handle_fly_to(action.x, action.y)
        elif action.action_type == "pick_up":
            self._handle_pick_up()
        elif action.action_type == "deliver":
            self._handle_deliver()
        else:
            self._error = f"Unknown action: {action.action_type}"
        return self._make_observation()

    @property
    def state(self) -> State:
        return self._state
```

**Design patterns that saved us pain:**

1. **One dispatch method, one handler per action.** `_handle_fly_to`, `_handle_pick_up`, `_handle_deliver`. Easy to unit test each.
2. **Errors go into the observation, not exceptions.** If `pick_up` fails because the drone isn't at the warehouse, set `self._error = "..."`. The agent sees it and retries.
3. **Centralize the observation builder.** Have `_make_observation()` that reads your internal state and returns a fresh `DroneObservation`. Call it at the end of every method. Never build observations inline.
4. **Centralize the grader.** Write `_compute_score()` as a pure function (no `self`). Easier to test, easier to reason about.

### Step 4 — Write the Grader

Your grader is the most important code in the environment. **Grader accuracy is non-negotiable.** Follow these rules:

1. **Deterministic.** Same inputs → same output. No randomness. No time-of-day. No external APIs.
2. **In range.** If the submission system requires scores in `(0, 1)` strictly, clamp:
   ```python
   SCORE_EPS = 0.001
   return min(max(score, SCORE_EPS), 1.0 - SCORE_EPS)
   ```
3. **Reward the right thing.** The drone grader rewards *route efficiency*. Look at the formula and ask "can an agent game this?" We caught one: the initial formula let agents score 1.0 by stopping after one delivery (short actual distance = inflated base score). We fixed it by clamping `base_score ≤ 1.0` BEFORE multiplying by `delivery_ratio`.
4. **Unit test edge cases.** Zero delivery, perfect route, partial delivery, exceeding time limit. Write tests BEFORE you trust the grader.

Here's the drone grader after fixes:

```python
def _compute_score(optimal_distance, actual_distance, packages_delivered,
                   total_packages, steps_taken, max_steps):
    if total_packages == 0 or actual_distance <= 0 or packages_delivered == 0:
        return SCORE_EPS
    delivery_ratio = packages_delivered / total_packages
    base_score = min(optimal_distance / actual_distance, 1.0)  # prevent gaming
    score = base_score * delivery_ratio
    if max_steps is not None and steps_taken > max_steps:
        score *= 0.5  # time penalty
    return min(max(score, SCORE_EPS), 1.0 - SCORE_EPS)  # strict (0, 1)
```

### Step 5 — Define Tasks (difficulty tiers)

Your environment should have multiple tasks at different difficulty levels. Drone uses a dict:

```python
TASKS = {
    "easy":   {"warehouse": (0,0), "houses": [("A",3,4), ("B",6,0)], "max_steps": None},
    "medium": {"warehouse": (0,0), "houses": [("A",2,4), ("B",5,1), ("C",8,5)], "max_steps": None},
    "hard":   {"warehouse": (0,0), "houses": [("A",3,6),("B",7,2),("C",10,8),("D",4,1)], "max_steps": 15},
}
```

`reset(task="medium")` looks up the config and initializes state. Keep maps **fixed** per task — randomness hurts reproducibility and makes grader debugging a nightmare.

### Step 6 — Boilerplate (`app.py`, `client.py`)

These are mostly copy-paste. The two traps we hit:

1. **Pass a factory, not an instance.** `create_app(DroneEnvironment, ...)` takes a class or factory function. If you pass an instance it will crash with `TypeError`. If you want HTTP state to persist across requests (you do), use a singleton factory:
   ```python
   _singleton = DroneEnvironment()
   def _factory(): return _singleton
   app = create_app(_factory, DroneAction, DroneObservation, env_name="my_env")
   ```

2. **The validator does a literal string match for `main()`.** In `server/app.py`:
   ```python
   if __name__ == "__main__":
       main()   # this exact string must appear
   ```
   Don't use `main(port=args.port)` — it won't match. Use argparse inside `main()` if you need args.

3. **Catch `ImportError` in fallback imports, not just `ModuleNotFoundError`.** Relative imports beyond top-level raise `ImportError`.

### Step 7 — Write End-to-End Tests

Don't just trust your grader — prove it. Write a test script that:

1. Runs the **optimal path** → score near the upper bound (e.g., 0.999).
2. Runs a **suboptimal path** → score in between (e.g., ~0.9).
3. Runs a **partial completion** → score reflects fraction completed.
4. Runs **error paths** (deliver without pickup, invalid actions, out-of-range coordinates) → error field set, state unchanged.
5. Checks **score is always strictly in the required range**.

The drone project has 71 such tests in `test_e2e.py`. Every time you change the grader, run them.

### Step 8 — Validate and Ship

```bash
openenv validate          # static checks (file structure, entry points, deps)
openenv build             # builds the Docker image
openenv validate --url http://localhost:8000   # runtime check against running server
openenv push              # deploys to Hugging Face Spaces
```

Common static validation failures you'll hit:
- Missing `main()` literal in `server/app.py`
- Missing `openenv-core` in dependencies
- Server entry point not referencing `main` in `pyproject.toml`
- `openenv.yaml` missing or malformed

## Adapting to a Different Use Case

Say you want to build a **warehouse picking environment** where a robot moves through aisles, picks products from shelves, and places them in a crate. Apply the template:

| Drone | Warehouse Picker |
|-------|------------------|
| 2D integer grid | 2D grid with aisle topology |
| `fly_to(x,y)` | `move_to(aisle, slot)` |
| `pick_up()` (all packages) | `pick(product_id)` (one at a time) |
| `deliver()` (nearest house) | `place_in_crate()` |
| Optimal = shortest route through houses | Optimal = shortest route through product locations |
| Score = route efficiency × delivery ratio | Score = route efficiency × correct picks × no damage |

**What stays the same:** the files, the structure, the validator requirements, the test-first discipline, the grader-must-be-deterministic rule.

**What changes:** the models, the tasks dict, the action handlers, the grader formula.

Other ideas that map cleanly onto this template:
- **Taxi pickup/dropoff** — passengers instead of packages.
- **Network packet routing** — graph of nodes, score = latency minimization.
- **Code refactoring** — AST nodes, score = tests still pass + fewer lines.
- **Cooking recipe** — ingredients + steps, score = recipe correctness + efficiency.

## Debugging Cheat Sheet

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Container starts, crashes | Check `docker logs` for Python traceback | Usually an import error in app.py |
| `/step` returns stale state | Passing class instead of singleton factory | Use factory pattern |
| Validator says main not callable | String `main()` not literal in app.py | Simplify the `if __name__` block |
| Score always 0 or 1 | Grader clamped to closed interval | Clamp to `[EPS, 1-EPS]` |
| Agent can game grader for free points | Formula has a loophole | Clamp sub-scores before multiplying |
| Relative import errors in Docker | Except clause too narrow | Catch `(ModuleNotFoundError, ImportError)` |

## What to Read Next

- `drone/server/drone_environment.py` — study the full implementation
- `drone/test_e2e.py` — study the test patterns
- `drone/DECISIONS.md` — see what design decisions got made and why
- `drone/ADR-001-grading-formula.md` — see the grader evolution with challenges and responses
- OpenEnv docs: https://github.com/meta-pytorch/OpenEnv

## The One Rule

**Your grader is the contract.** Every other piece of code can have bugs and you can fix them later. A broken grader corrupts every agent benchmark that ever runs against your environment. Test it first, test it hardest, and never change it without running all your tests again.
