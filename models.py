# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for the Drone Delivery Environment.

The drone picks up packages at a warehouse and delivers them to houses
on a 2D integer coordinate grid. Actions: fly_to(x,y), pick_up(), deliver().
"""

from typing import Dict, List, Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class HouseInfo(Observation):
    """Information about a delivery target house."""

    name: str = Field(description="House identifier (e.g. 'A', 'B')")
    x: int = Field(description="X coordinate")
    y: int = Field(description="Y coordinate")
    delivered: bool = Field(default=False, description="Whether package has been delivered")


class DroneAction(Action):
    """Action for the Drone Delivery environment.

    Three action types:
    - fly_to: fly to coordinates (x, y required)
    - pick_up: pick up all packages at warehouse (must be at warehouse)
    - deliver: deliver package to nearest house within radius (must be near a house)
    """

    action_type: str = Field(
        ..., description="One of: 'fly_to', 'pick_up', 'deliver'"
    )
    x: Optional[int] = Field(default=None, description="Target X coordinate (for fly_to)")
    y: Optional[int] = Field(default=None, description="Target Y coordinate (for fly_to)")


class DroneObservation(Observation):
    """Observation from the Drone Delivery environment."""

    drone_x: int = Field(default=0, description="Drone X position")
    drone_y: int = Field(default=0, description="Drone Y position")
    packages_carried: int = Field(default=0, description="Packages currently carried")
    packages_delivered: int = Field(default=0, description="Packages delivered so far")
    total_packages: int = Field(default=0, description="Total packages to deliver")
    houses: List[HouseInfo] = Field(default_factory=list, description="Delivery target houses")
    warehouse_x: int = Field(default=0, description="Warehouse X position")
    warehouse_y: int = Field(default=0, description="Warehouse Y position")
    distance_traveled: float = Field(default=0.0, description="Total Euclidean distance traveled")
    steps_taken: int = Field(default=0, description="Number of actions taken")
    max_steps: Optional[int] = Field(default=None, description="Step limit (hard mode only)")
    error: Optional[str] = Field(default=None, description="Error message if last action was invalid")
    score: float = Field(default=0.0, description="Current grader score (0.0-1.0)")
    task_name: str = Field(default="", description="Current task name")
