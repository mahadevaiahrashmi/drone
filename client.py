# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Drone Delivery Environment Client."""

from typing import Dict, List

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

try:
    from .models import DroneAction, DroneObservation, HouseInfo
except ImportError:
    from models import DroneAction, DroneObservation, HouseInfo


class DroneEnv(
    EnvClient[DroneAction, DroneObservation, State]
):
    """
    Client for the Drone Delivery Environment.

    Example:
        >>> with DroneEnv(base_url="http://localhost:8000") as client:
        ...     result = client.reset()
        ...     result = client.step(DroneAction(action_type="pick_up"))
        ...     result = client.step(DroneAction(action_type="fly_to", x=3, y=4))
        ...     result = client.step(DroneAction(action_type="deliver"))

    Example with Docker:
        >>> client = DroneEnv.from_docker_image("drone-env:latest")
        >>> try:
        ...     result = client.reset()
        ...     result = client.step(DroneAction(action_type="pick_up"))
        ... finally:
        ...     client.close()
    """

    def _step_payload(self, action: DroneAction) -> Dict:
        """Convert DroneAction to JSON payload for step message."""
        payload = {"action_type": action.action_type}
        if action.x is not None:
            payload["x"] = action.x
        if action.y is not None:
            payload["y"] = action.y
        return payload

    def _parse_result(self, payload: Dict) -> StepResult[DroneObservation]:
        """Parse server response into StepResult[DroneObservation]."""
        obs_data = payload.get("observation", {})

        houses = []
        for h in obs_data.get("houses", []):
            houses.append(HouseInfo(
                name=h.get("name", ""),
                x=h.get("x", 0),
                y=h.get("y", 0),
                delivered=h.get("delivered", False),
            ))

        observation = DroneObservation(
            drone_x=obs_data.get("drone_x", 0),
            drone_y=obs_data.get("drone_y", 0),
            packages_carried=obs_data.get("packages_carried", 0),
            packages_delivered=obs_data.get("packages_delivered", 0),
            total_packages=obs_data.get("total_packages", 0),
            houses=houses,
            warehouse_x=obs_data.get("warehouse_x", 0),
            warehouse_y=obs_data.get("warehouse_y", 0),
            distance_traveled=obs_data.get("distance_traveled", 0.0),
            steps_taken=obs_data.get("steps_taken", 0),
            max_steps=obs_data.get("max_steps"),
            error=obs_data.get("error"),
            score=obs_data.get("score", 0.0),
            task_name=obs_data.get("task_name", ""),
            done=payload.get("done", False),
            reward=payload.get("reward", 0.0),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward", 0.0),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        """Parse server response into State object."""
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
