# Drone Environment — Design Decisions

## D1: World Model
- **Decision:** Continuous 2D space with integer coordinates
- **Options:** (A) Step-by-step grid walker, (B) Named location hopper, (C) Coordinate flyer
- **Chosen:** C — most realistic, tests spatial reasoning
- **Reason:** User preference for realism. LLM agents must reason about coordinates.

## D2: Coordinate Space
- **Decision:** Integer coordinates (e.g., 0–20 range)
- **Options:** Integer grid vs. floating point
- **Chosen:** Integer
- **Reason:** Easier for LLMs to reason about, cleaner grading, no floating point tolerance issues.

## D3: Actions
- **Decision:** `fly_to(x, y)`, `pick_up()`, `deliver()`
- **Reason:** High-level semantic actions. `fly_to` takes integer coordinates. `pick_up` and `deliver` are contextual (must be at warehouse / within radius of house).

## D4: Delivery Mechanic
- **Decision:** `deliver()` auto-delivers to the nearest house within radius
- **Options:** (A) `deliver()` auto-detect house, (B) `deliver(house_name)` explicit target
- **Chosen:** A
- **Reason:** Simpler interface. If drone is within radius of a house, intent is unambiguous. Reduces LLM parsing errors.

## D5: Pick Up Mechanic
- **Decision:** `pick_up()` at warehouse grabs ALL packages at once
- **Options:** (A) Grab all at once, (B) One at a time, (C) Pick specific packages
- **Chosen:** A
- **Reason:** Capacity is unlimited. No reason to force multiple pick-up actions — it adds tedium without testing planning skill. The challenge is routing, not inventory management.

## D6: Delivery Radius
- **Decision:** Drone must be within 1 unit of a house to deliver
- **Options:** Exact coordinate match vs. radius tolerance
- **Chosen:** Radius of 1 unit
- **Reason:** User preference. Avoids frustrating off-by-one failures. Grading focuses on route quality, not pixel-perfect navigation.

## D7: Task Difficulty Scaling
- **Decision:** Easy=2 deliveries, Medium=3, Hard=4 + time limit
- **Reason:** User specified. Possible routes scale factorially (2, 6, 24). Hard adds time pressure.

## D8: Grading Formula
- **Decision:** Score = optimal_distance / actual_distance (clamped 0.0–1.0)
- **Penalties:** Undelivered packages reduce score proportionally. Hard mode: time limit exceeded = additional penalty.
- **Reason:** Deterministic, rewards efficiency, partial credit for suboptimal-but-complete routes.

## D9: Map Layout
- **Decision:** Warehouse at center-ish, houses spread around. Fixed per task (not random).
- **Reason:** Fixed layouts make grading deterministic and reproducible. Optimal route is precomputed.
