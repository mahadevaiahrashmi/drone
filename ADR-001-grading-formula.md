# ADR-001: Grading Formula for Delivery Tasks

## Status
Accepted

## Context
Each task needs a deterministic grader that scores agent performance 0.0–1.0. The grading must reward route efficiency (shorter = better) and penalize incomplete deliveries. This is the project's non-negotiable quality criterion.

## Decision

### Formula
```
base_score = min(optimal_distance / actual_distance, 1.0)
delivery_ratio = packages_delivered / total_packages
score = base_score * delivery_ratio
final_score = clamp(score, SCORE_EPS, 1.0 - SCORE_EPS)   # SCORE_EPS = 0.001
```

Scores are clamped to the STRICT open interval `(0, 1)` — never exactly
`0.0` or `1.0`. Submission systems reject boundary scores, so perfect
performance maps to `0.999` and worst performance maps to `0.001`.

`base_score` is capped at 1.0 BEFORE multiplying by `delivery_ratio` —
otherwise partial delivery (shorter actual distance) would inflate the
base ratio and cancel out the delivery penalty, letting an agent score
1.0 by stopping after one delivery.

### Hard mode time limit
If `steps_taken > max_steps`: score = score * 0.5 (50% penalty)

### Edge cases (with strict-interval clamp)
- Agent delivers all packages via optimal route → score = 0.999
- Agent delivers all but takes 2x optimal distance → score = 0.5
- Agent delivers 2 of 4 packages optimally → score = 0.5 (delivery_ratio)
- Agent delivers 0 packages → score = 0.001
- Agent doesn't move → actual_distance = 0 → score = 0.001

### Optimal distance computation
Brute-force all permutations of delivery order. Max 4 houses = 24 permutations. Compute: warehouse → house_perm[0] → house_perm[1] → ... → house_perm[n]. Shortest total Euclidean distance wins. Precomputed at task init.

## Alternatives Considered
1. **Step count instead of distance** — rejected because fly_to covers variable distance per step. Distance is the true cost.
2. **Additive scoring (points per delivery)** — rejected because it doesn't reward route optimization, only completion.
3. **Time-based decay** — rejected for easy/medium; added as penalty multiplier for hard only.

## Constraints (explicit)
- **House count hard cap: 4.** Brute-force permutation is O(n!). At n=4, 24 perms — trivial. If ever extended beyond 8, replace with TSP approximation.
- **No obstacles, no return to warehouse.** Optimal = straight-line Euclidean through all houses. If obstacles are added, grading formula must be revisited in a new ADR.

## Risks
- Euclidean distance between integer coords produces irrational numbers — comparison uses float math. Mitigated by computing both optimal and actual with same math; ratio is stable.
- Multiplicative score collapse on partial delivery is intentional: partial delivery means the agent misunderstood the task. Low scores are appropriate signal.

## Debate Record (2026-04-12)
- **Wei challenge 1 (assumption surfacing):** Optimal assumes no obstacles/return — breaks if constraints added. **Archie response:** Accepted as documented constraint. No obstacles is confirmed scope.
- **Wei challenge 2 (scale attack):** Brute-force breaks at higher house counts. **Archie response:** Added explicit hard cap of 4 houses. Document switch to TSP solver if extended.
- **Wei challenge 3 (cost of being wrong):** Multiplicative formula crushes partial-delivery scores. **Archie response:** Intentional — partial delivery is a fundamental agent failure, low score is correct signal.
- **Outcome:** ADR updated with explicit constraints and rationale. No formula change needed.
