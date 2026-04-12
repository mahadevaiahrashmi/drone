# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
FastAPI application for the Drone Delivery Environment.

Endpoints:
    - POST /reset: Reset the environment (accepts optional task parameter)
    - POST /step: Execute an action (fly_to, pick_up, deliver)
    - GET /state: Get current environment state
    - GET /schema: Get action/observation schemas
    - WS /ws: WebSocket endpoint for persistent sessions

Usage:
    uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
"""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with '\n    uv sync\n'"
    ) from e

try:
    from ..models import DroneAction, DroneObservation
    from .drone_environment import DroneEnvironment
except (ModuleNotFoundError, ImportError):
    from models import DroneAction, DroneObservation
    from server.drone_environment import DroneEnvironment


# Create the app with web interface and README integration
# Use a singleton factory so HTTP requests share the same environment instance.
# The library requires a callable (class or factory), not an instance.
_drone_env_singleton = DroneEnvironment()


def _drone_env_factory() -> DroneEnvironment:
    return _drone_env_singleton


app = create_app(
    _drone_env_factory,
    DroneAction,
    DroneObservation,
    env_name="drone",
    max_concurrent_envs=1,
)


def main(host: str = "0.0.0.0", port: int = 8000):
    """
    Entry point for direct execution.

    Usage:
        uv run --project . server
        uv run --project . server --port 8001
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
