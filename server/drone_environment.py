# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Drone Delivery Environment Implementation.

A delivery drone picks up packages at a warehouse and delivers them to houses
on a 2D integer grid. Tasks test route optimization — finding the shortest
path through delivery points.

Tasks:
- easy: 2 houses, no time limit
- medium: 3 houses, no time limit
- hard: 4 houses, max_steps time limit
"""

import math
from itertools import permutations
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import DroneAction, DroneObservation, HouseInfo
except (ModuleNotFoundError, ImportError):
    from models import DroneAction, DroneObservation, HouseInfo


# --- Task Configurations ---

DELIVERY_RADIUS = 1.0  # Must be within 1 unit of house to deliver

# Score must be STRICTLY in (0, 1) — never exactly 0.0 or 1.0.
# Submission systems reject boundary scores. We clamp to [EPS, 1 - EPS].
SCORE_EPS = 0.001

TASKS: Dict[str, Dict[str, Any]] = {
    "easy": {
        "warehouse": (0, 0),
        "houses": [
            ("A", 3, 4),
            ("B", 6, 0),
        ],
        "max_steps": None,
    },
    "medium": {
        "warehouse": (0, 0),
        "houses": [
            ("A", 2, 4),
            ("B", 5, 1),
            ("C", 8, 5),
        ],
        "max_steps": None,
    },
    "hard": {
        "warehouse": (0, 0),
        "houses": [
            ("A", 3, 6),
            ("B", 7, 2),
            ("C", 10, 8),
            ("D", 4, 1),
        ],
        "max_steps": 15,
    },
}


def _euclidean(p1: Tuple[int, int], p2: Tuple[int, int]) -> float:
    """Euclidean distance between two integer coordinate points."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _compute_optimal_distance(
    warehouse: Tuple[int, int], houses: List[Tuple[str, int, int]]
) -> float:
    """Compute optimal delivery route distance by brute-forcing all permutations.

    Route: warehouse → house_perm[0] → house_perm[1] → ... → house_perm[n]
    No return to warehouse required.

    Max 4 houses = 24 permutations. See ADR-001 for rationale.
    """
    house_coords = [(h[1], h[2]) for h in houses]
    best = float("inf")
    for perm in permutations(house_coords):
        dist = _euclidean(warehouse, perm[0])
        for i in range(1, len(perm)):
            dist += _euclidean(perm[i - 1], perm[i])
        best = min(best, dist)
    return best


def _compute_score(
    optimal_distance: float,
    actual_distance: float,
    packages_delivered: int,
    total_packages: int,
    steps_taken: int,
    max_steps: Optional[int],
) -> float:
    """Compute grader score per ADR-001.

    score = (optimal_distance / actual_distance) * (delivered / total)
    Hard mode: 50% penalty if steps exceed max_steps.
    """
    if total_packages == 0:
        return SCORE_EPS
    if actual_distance <= 0:
        return SCORE_EPS
    if packages_delivered == 0:
        return SCORE_EPS

    delivery_ratio = packages_delivered / total_packages
    # Clamp base_score to <= 1.0 before multiplying so that partial delivery
    # (which uses less actual_distance) cannot inflate the score above the
    # delivery_ratio. Prevents gaming by stopping after one delivery.
    base_score = min(optimal_distance / actual_distance, 1.0)
    score = base_score * delivery_ratio

    # Hard mode time penalty
    if max_steps is not None and steps_taken > max_steps:
        score *= 0.5

    # Clamp to STRICT open interval (0, 1) per submission requirements.
    return min(max(score, SCORE_EPS), 1.0 - SCORE_EPS)


class DroneEnvironment(Environment):
    """
    Delivery drone environment.

    The drone starts at the warehouse, picks up packages, and delivers
    them to houses. Score is based on route efficiency vs. optimal.

    Actions:
        - fly_to(x, y): fly to integer coordinates
        - pick_up(): pick up all packages at warehouse
        - deliver(): deliver to nearest house within radius

    The environment supports a 'task' parameter on reset to select difficulty.
    Default task is 'easy'.
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        """Initialize the drone environment."""
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._task_name = "easy"
        self._task_config = TASKS["easy"]
        self._drone_pos: Tuple[int, int] = (0, 0)
        self._packages_carried = 0
        self._delivered: Dict[str, bool] = {}
        self._distance_traveled = 0.0
        self._optimal_distance = 0.0
        self._error: Optional[str] = None

    def reset(self, task: str = "easy") -> DroneObservation:
        """Reset the environment for a given task.

        Args:
            task: Task difficulty — 'easy', 'medium', or 'hard'

        Returns:
            DroneObservation with initial state
        """
        if task not in TASKS:
            task = "easy"

        self._task_name = task
        self._task_config = TASKS[task]
        self._state = State(episode_id=str(uuid4()), step_count=0)

        warehouse = self._task_config["warehouse"]
        self._drone_pos = warehouse
        self._packages_carried = 0
        self._delivered = {h[0]: False for h in self._task_config["houses"]}
        self._distance_traveled = 0.0
        self._error = None
        self._optimal_distance = _compute_optimal_distance(
            warehouse, self._task_config["houses"]
        )

        return self._make_observation()

    def step(self, action: DroneAction) -> DroneObservation:
        """Execute one action.

        Args:
            action: DroneAction with action_type and optional x, y

        Returns:
            DroneObservation with updated state
        """
        self._state.step_count += 1
        self._error = None

        action_type = action.action_type.lower().strip()

        if action_type == "fly_to":
            self._handle_fly_to(action.x, action.y)
        elif action_type == "pick_up":
            self._handle_pick_up()
        elif action_type == "deliver":
            self._handle_deliver()
        else:
            self._error = f"Unknown action: '{action.action_type}'. Use 'fly_to', 'pick_up', or 'deliver'."

        return self._make_observation()

    def _handle_fly_to(self, x: Optional[int], y: Optional[int]) -> None:
        """Fly the drone to target coordinates."""
        if x is None or y is None:
            self._error = "fly_to requires both x and y coordinates."
            return

        target = (x, y)
        dist = _euclidean(self._drone_pos, target)
        self._distance_traveled += dist
        self._drone_pos = target

    def _handle_pick_up(self) -> None:
        """Pick up all packages at warehouse."""
        warehouse = self._task_config["warehouse"]
        dist_to_warehouse = _euclidean(self._drone_pos, warehouse)

        if dist_to_warehouse > DELIVERY_RADIUS:
            self._error = (
                f"Not at warehouse. Drone is at {self._drone_pos}, "
                f"warehouse is at {warehouse} (distance: {dist_to_warehouse:.1f}, need <= {DELIVERY_RADIUS})."
            )
            return

        total = len(self._task_config["houses"])
        already_delivered = sum(1 for v in self._delivered.values() if v)
        remaining = total - already_delivered - self._packages_carried
        if remaining <= 0:
            self._error = "No packages to pick up."
            return

        self._packages_carried = remaining

    def _handle_deliver(self) -> None:
        """Deliver a package to the nearest undelivered house within radius."""
        if self._packages_carried <= 0:
            self._error = "No packages to deliver. Pick up packages at warehouse first."
            return

        # Find nearest undelivered house within radius
        nearest_house = None
        nearest_dist = float("inf")

        for name, hx, hy in self._task_config["houses"]:
            if self._delivered[name]:
                continue
            dist = _euclidean(self._drone_pos, (hx, hy))
            if dist <= DELIVERY_RADIUS and dist < nearest_dist:
                nearest_house = name
                nearest_dist = dist

        if nearest_house is None:
            undelivered = [
                f"{name}({hx},{hy})"
                for name, hx, hy in self._task_config["houses"]
                if not self._delivered[name]
            ]
            self._error = (
                f"No undelivered house within radius {DELIVERY_RADIUS} of {self._drone_pos}. "
                f"Undelivered houses: {', '.join(undelivered)}."
            )
            return

        self._delivered[nearest_house] = True
        self._packages_carried -= 1

    def _is_done(self) -> bool:
        """Check if all packages are delivered."""
        if not self._delivered:
            return False
        return all(self._delivered.values())

    def _make_observation(self) -> DroneObservation:
        """Build current observation."""
        houses = []
        for name, hx, hy in self._task_config["houses"]:
            houses.append(
                HouseInfo(name=name, x=hx, y=hy, delivered=self._delivered.get(name, False))
            )

        total = len(self._task_config["houses"])
        delivered_count = sum(1 for v in self._delivered.values() if v)
        done = self._is_done()

        score = _compute_score(
            optimal_distance=self._optimal_distance,
            actual_distance=self._distance_traveled,
            packages_delivered=delivered_count,
            total_packages=total,
            steps_taken=self._state.step_count,
            max_steps=self._task_config["max_steps"],
        )

        return DroneObservation(
            drone_x=self._drone_pos[0],
            drone_y=self._drone_pos[1],
            packages_carried=self._packages_carried,
            packages_delivered=delivered_count,
            total_packages=total,
            houses=houses,
            warehouse_x=self._task_config["warehouse"][0],
            warehouse_y=self._task_config["warehouse"][1],
            distance_traveled=round(self._distance_traveled, 2),
            steps_taken=self._state.step_count,
            max_steps=self._task_config["max_steps"],
            error=self._error,
            score=round(score, 4),
            task_name=self._task_name,
            done=done,
            reward=score if done else 0.0,
        )

    @property
    def state(self) -> State:
        """Get the current environment state."""
        return self._state
