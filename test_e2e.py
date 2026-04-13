"""End-to-end tests for the Drone Delivery Environment.

Exercises all 3 tasks (easy/medium/hard) via direct Python calls —
no Docker, no HTTP — to verify the environment logic end to end.

Run:
    python test_e2e.py
"""

import math
import sys

from models import DroneAction
from server.drone_environment import DroneEnvironment, TASKS, _compute_optimal_distance


# --- Test helpers ---

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"


class TestReport:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []

    def check(self, name, condition, detail=""):
        if condition:
            self.passed += 1
            print(f"  {PASS} {name}")
        else:
            self.failed += 1
            self.failures.append(f"{name}: {detail}")
            print(f"  {FAIL} {name} — {detail}")

    def approx(self, name, actual, expected, tol=1e-6):
        ok = abs(actual - expected) < tol
        self.check(name, ok, f"expected ~{expected}, got {actual}")

    def summary(self):
        total = self.passed + self.failed
        print()
        print(f"=== {self.passed}/{total} passed ===")
        if self.failed:
            print("Failures:")
            for f in self.failures:
                print(f"  - {f}")
        return self.failed == 0


def run_actions(env, actions):
    """Run a list of actions and return final observation."""
    obs = None
    for a in actions:
        obs = env.step(a)
    return obs


def fly(x, y):
    return DroneAction(action_type="fly_to", x=x, y=y)


PICKUP = DroneAction(action_type="pick_up")
DELIVER = DroneAction(action_type="deliver")


# --- Tests ---

def test_easy_optimal(r: TestReport):
    print("\n[TEST] easy task — optimal route W→A→B")
    env = DroneEnvironment()
    obs = env.reset("easy")
    r.check("reset: task_name=easy", obs.task_name == "easy")
    r.check("reset: total_packages=2", obs.total_packages == 2)
    r.check("reset: drone at warehouse", (obs.drone_x, obs.drone_y) == (0, 0))
    r.check("reset: distance_traveled=0", obs.distance_traveled == 0.0)
    r.check("reset: score=SCORE_EPS (no movement)", obs.score == 0.001)
    r.check("reset: not done", obs.done is False)

    obs = env.step(PICKUP)
    r.check("pickup: carried=2", obs.packages_carried == 2)
    r.check("pickup: no error", obs.error is None)

    obs = env.step(fly(3, 4))
    r.approx("fly to A: distance=5.0", obs.distance_traveled, 5.0)
    r.check("fly to A: pos=(3,4)", (obs.drone_x, obs.drone_y) == (3, 4))

    obs = env.step(DELIVER)
    r.check("deliver A: delivered=1", obs.packages_delivered == 1)
    r.check("deliver A: carried=1", obs.packages_carried == 1)
    r.check("deliver A: house A marked", obs.houses[0].delivered is True)
    r.check("deliver A: house B not marked", obs.houses[1].delivered is False)

    obs = env.step(fly(6, 0))
    r.approx("fly to B: distance=10.0", obs.distance_traveled, 10.0)

    obs = env.step(DELIVER)
    r.check("deliver B: delivered=2", obs.packages_delivered == 2)
    r.check("deliver B: done=True", obs.done is True)
    r.approx("deliver B: score=0.999", obs.score, 0.999, tol=0.002)
    r.approx("deliver B: reward=0.999", obs.reward, 0.999, tol=0.002)
    r.check("deliver B: score strictly < 1.0", obs.score < 1.0)
    r.check("deliver B: score strictly > 0.0", obs.score > 0.0)


def test_easy_suboptimal(r: TestReport):
    print("\n[TEST] easy task — suboptimal W→B→A")
    env = DroneEnvironment()
    env.reset("easy")
    env.step(PICKUP)
    env.step(fly(6, 0))       # W→B: distance 6
    env.step(DELIVER)
    env.step(fly(3, 4))       # B→A: 5
    obs = env.step(DELIVER)   # total = 11
    r.approx("distance=11", obs.distance_traveled, 11.0)
    r.check("done", obs.done is True)
    expected = 10.0 / 11.0
    r.approx("score ≈ 10/11", obs.score, expected, tol=0.01)


def test_medium_optimal(r: TestReport):
    print("\n[TEST] medium task — brute force vs optimal")
    env = DroneEnvironment()
    obs = env.reset("medium")
    r.check("reset: total=3", obs.total_packages == 3)

    opt = _compute_optimal_distance((0, 0), TASKS["medium"]["houses"])

    env.step(PICKUP)
    env.step(fly(2, 4))
    env.step(DELIVER)
    env.step(fly(5, 1))
    env.step(DELIVER)
    env.step(fly(8, 5))
    obs = env.step(DELIVER)

    r.check("done", obs.done is True)
    r.check("delivered=3", obs.packages_delivered == 3)
    # Verify this route is in fact optimal
    r.approx("route = optimal", obs.distance_traveled, opt, tol=0.01)
    r.approx("score=0.999", obs.score, 0.999, tol=0.002)
    r.check("score strictly in (0,1)", 0.0 < obs.score < 1.0)


def test_hard_optimal(r: TestReport):
    print("\n[TEST] hard task — with time limit")
    env = DroneEnvironment()
    obs = env.reset("hard")
    r.check("reset: total=4", obs.total_packages == 4)
    r.check("reset: max_steps=15", obs.max_steps == 15)

    opt = _compute_optimal_distance((0, 0), TASKS["hard"]["houses"])

    # Find optimal permutation programmatically to play optimally
    from itertools import permutations
    houses = TASKS["hard"]["houses"]
    best_perm = None
    best_dist = float("inf")
    for perm in permutations(houses):
        d = math.dist((0, 0), (perm[0][1], perm[0][2]))
        for i in range(1, len(perm)):
            d += math.dist((perm[i-1][1], perm[i-1][2]), (perm[i][1], perm[i][2]))
        if d < best_dist:
            best_dist = d
            best_perm = perm

    env.step(PICKUP)
    for _, hx, hy in best_perm:
        env.step(fly(hx, hy))
        env.step(DELIVER)

    obs = env.step(DroneAction(action_type="fly_to", x=0, y=0))  # inert extra step
    # Actually just check after last delivery
    # Replay with correct final observation
    env2 = DroneEnvironment()
    env2.reset("hard")
    env2.step(PICKUP)
    final_obs = None
    for _, hx, hy in best_perm:
        env2.step(fly(hx, hy))
        final_obs = env2.step(DELIVER)

    r.check("delivered=4", final_obs.packages_delivered == 4)
    r.check("done=True", final_obs.done is True)
    r.approx("distance=optimal", final_obs.distance_traveled, opt, tol=0.01)
    r.approx("score=0.999", final_obs.score, 0.999, tol=0.002)
    r.check("score strictly in (0,1)", 0.0 < final_obs.score < 1.0)
    r.check(f"steps <= 15 (got {final_obs.steps_taken})", final_obs.steps_taken <= 15)


def test_hard_time_penalty(r: TestReport):
    print("\n[TEST] hard task — exceeding time limit triggers 50% penalty")
    env = DroneEnvironment()
    env.reset("hard")
    env.step(PICKUP)

    # Waste steps by flying around before delivering
    for _ in range(12):
        env.step(fly(0, 0))  # no-op flights (no distance, but steps++)

    # Now do optimal route
    from itertools import permutations
    houses = TASKS["hard"]["houses"]
    best_perm = min(
        permutations(houses),
        key=lambda p: (
            math.dist((0, 0), (p[0][1], p[0][2]))
            + sum(math.dist((p[i-1][1], p[i-1][2]), (p[i][1], p[i][2])) for i in range(1, len(p)))
        ),
    )
    final_obs = None
    for _, hx, hy in best_perm:
        env.step(fly(hx, hy))
        final_obs = env.step(DELIVER)

    r.check("done=True", final_obs.done is True)
    r.check(f"steps > 15 (got {final_obs.steps_taken})", final_obs.steps_taken > 15)
    # Raw optimality is 1.0, so score should be 0.5 after penalty
    r.approx("score = 0.5 (penalty applied)", final_obs.score, 0.5, tol=0.01)


def test_partial_delivery(r: TestReport):
    print("\n[TEST] partial delivery — only delivers 1 of 2")
    env = DroneEnvironment()
    env.reset("easy")
    env.step(PICKUP)
    env.step(fly(3, 4))
    env.step(DELIVER)
    # Stop here — only 1 delivered
    obs = env.step(DroneAction(action_type="fly_to", x=3, y=4))  # no-op

    r.check("delivered=1", obs.packages_delivered == 1)
    r.check("not done", obs.done is False)
    # score = (10/5) * (1/2) = 1.0, clamped to 1.0 — hmm wait
    # actually: optimal=10, actual=5 so ratio=2.0 clamped to 1.0
    # delivery_ratio = 0.5
    # score = 1.0 * 0.5 = 0.5
    r.approx("score reflects partial delivery", obs.score, 0.5, tol=0.01)


def test_error_cases(r: TestReport):
    print("\n[TEST] error handling")
    env = DroneEnvironment()
    env.reset("easy")

    # Deliver without packages
    obs = env.step(DELIVER)
    r.check("deliver without packages: error set", obs.error is not None)
    r.check("deliver without packages: delivered=0", obs.packages_delivered == 0)

    # Pickup at warehouse (ok)
    obs = env.step(PICKUP)
    r.check("pickup at warehouse: no error", obs.error is None)

    # Pickup again (no more packages)
    obs = env.step(PICKUP)
    r.check("pickup when all carried: error", obs.error is not None)

    # Deliver not near house
    env.step(fly(50, 50))
    obs = env.step(DELIVER)
    r.check("deliver far from house: error", obs.error is not None)
    r.check("deliver far from house: delivered=0", obs.packages_delivered == 0)

    # Unknown action — Pydantic Literal rejects at parse time
    try:
        DroneAction(action_type="teleport", x=1, y=1)
        rejected = False
    except Exception:
        rejected = True
    r.check("unknown action: rejected at parse time", rejected)

    # fly_to with missing coords
    obs = env.step(DroneAction(action_type="fly_to"))
    r.check("fly_to without x,y: error", obs.error is not None)


def test_delivery_radius(r: TestReport):
    print("\n[TEST] delivery radius — within 1 unit")
    env = DroneEnvironment()
    env.reset("easy")
    env.step(PICKUP)
    # House A at (3,4). Fly to (3,5) — 1 unit away, should deliver.
    env.step(fly(3, 5))
    obs = env.step(DELIVER)
    r.check("deliver at radius 1.0: success", obs.packages_delivered == 1)

    env.reset("easy")
    env.step(PICKUP)
    # Fly to (5,4) — 2 units from A(3,4), too far
    env.step(fly(5, 4))
    obs = env.step(DELIVER)
    r.check("deliver at radius 2.0: error", obs.error is not None)
    r.check("deliver at radius 2.0: delivered=0", obs.packages_delivered == 0)


def test_reset_mid_episode(r: TestReport):
    print("\n[TEST] reset clears state mid-episode")
    env = DroneEnvironment()
    env.reset("medium")
    env.step(PICKUP)
    env.step(fly(2, 4))
    env.step(DELIVER)

    # Reset to easy
    obs = env.reset("easy")
    r.check("reset clears distance", obs.distance_traveled == 0.0)
    r.check("reset clears delivered", obs.packages_delivered == 0)
    r.check("reset clears carried", obs.packages_carried == 0)
    r.check("reset changes task", obs.task_name == "easy")
    r.check("reset changes total", obs.total_packages == 2)


def test_invalid_task(r: TestReport):
    print("\n[TEST] invalid task name falls back to easy")
    env = DroneEnvironment()
    obs = env.reset("impossible")
    r.check("unknown task → easy fallback", obs.task_name == "easy")
    r.check("unknown task → 2 houses", obs.total_packages == 2)


def test_scores_strictly_in_open_interval(r: TestReport):
    print("\n[TEST] scores are strictly in open interval (0, 1)")
    # Scenarios that previously hit boundaries (0.0 or 1.0)
    scenarios = [
        ("easy-perfect", "easy", [PICKUP, fly(3, 4), DELIVER, fly(6, 0), DELIVER]),
        ("medium-perfect", "medium", [PICKUP, fly(2, 4), DELIVER, fly(5, 1), DELIVER, fly(8, 5), DELIVER]),
        ("hard-perfect", "hard", [PICKUP, fly(4, 1), DELIVER, fly(7, 2), DELIVER, fly(3, 6), DELIVER, fly(10, 8), DELIVER]),
        ("no-delivery", "easy", [PICKUP, fly(50, 50)]),
        ("reset-only", "easy", []),
    ]
    for name, task, actions in scenarios:
        env = DroneEnvironment()
        obs = env.reset(task)
        for a in actions:
            obs = env.step(a)
        r.check(f"{name}: 0 < score < 1 (got {obs.score})", 0.0 < obs.score < 1.0)


def test_optimal_distances_precomputed(r: TestReport):
    print("\n[TEST] optimal distances are sensible")
    easy = _compute_optimal_distance(TASKS["easy"]["warehouse"], TASKS["easy"]["houses"])
    medium = _compute_optimal_distance(TASKS["medium"]["warehouse"], TASKS["medium"]["houses"])
    hard = _compute_optimal_distance(TASKS["hard"]["warehouse"], TASKS["hard"]["houses"])

    r.approx("easy optimal = 10.0", easy, 10.0)
    r.check(f"medium optimal > 0 (got {medium:.2f})", medium > 0)
    r.check(f"hard optimal > 0 (got {hard:.2f})", hard > 0)
    r.check("hard > medium > easy difficulty", hard > medium > easy)


# --- Main ---

def main():
    r = TestReport()

    test_scores_strictly_in_open_interval(r)
    test_optimal_distances_precomputed(r)
    test_easy_optimal(r)
    test_easy_suboptimal(r)
    test_medium_optimal(r)
    test_hard_optimal(r)
    test_hard_time_penalty(r)
    test_partial_delivery(r)
    test_error_cases(r)
    test_delivery_radius(r)
    test_reset_mid_episode(r)
    test_invalid_task(r)

    ok = r.summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
