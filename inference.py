"""
Inference Script for Drone Delivery Environment
================================================

Drives an LLM agent through the drone delivery environment.
The agent must pick up packages at the warehouse and deliver them
to houses via the shortest route.

Required env vars:
    API_BASE_URL   The API endpoint for the LLM.
    MODEL_NAME     The model identifier to use for inference.
    HF_TOKEN       Your Hugging Face / API key.
    IMAGE_NAME     Docker image name (if using from_docker_image).

STDOUT FORMAT:
    [START] task=<task_name> env=<benchmark> model=<model_name>
    [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>
"""

import asyncio
import json
import os
import textwrap
from typing import List, Optional

from openai import OpenAI

from drone import DroneAction, DroneEnv

IMAGE_NAME = os.getenv("IMAGE_NAME")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
TASK_NAME = os.getenv("DRONE_TASK", "easy")
BENCHMARK = os.getenv("DRONE_BENCHMARK", "drone")
MAX_STEPS = 20
TEMPERATURE = 0.3
MAX_TOKENS = 200

SYSTEM_PROMPT = textwrap.dedent(
    """
    You are controlling a delivery drone on a 2D grid.
    Your goal: pick up all packages at the warehouse and deliver them to every house via the shortest route.

    Actions (respond with valid JSON):
    - {"action_type": "pick_up"}           — pick up all packages (must be at warehouse)
    - {"action_type": "fly_to", "x": N, "y": N} — fly to coordinates
    - {"action_type": "deliver"}           — deliver to nearest house within radius 1

    Strategy:
    1. First, pick_up at the warehouse to grab all packages
    2. Plan the shortest route visiting all houses
    3. Fly to each house and deliver

    Respond with ONLY a JSON object for your next action. No explanation.
    """
).strip()


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


def format_observation(obs) -> str:
    """Format observation into a readable prompt for the LLM."""
    houses_str = "\n".join(
        f"  - House {h.name} at ({h.x}, {h.y}) {'[DELIVERED]' if h.delivered else '[PENDING]'}"
        for h in obs.houses
    )
    parts = [
        f"Drone position: ({obs.drone_x}, {obs.drone_y})",
        f"Warehouse: ({obs.warehouse_x}, {obs.warehouse_y})",
        f"Packages carried: {obs.packages_carried}",
        f"Delivered: {obs.packages_delivered}/{obs.total_packages}",
        f"Distance traveled: {obs.distance_traveled}",
        f"Steps: {obs.steps_taken}",
        f"Houses:\n{houses_str}",
    ]
    if obs.max_steps is not None:
        parts.append(f"Max steps allowed: {obs.max_steps}")
    if obs.error:
        parts.append(f"ERROR: {obs.error}")
    return "\n".join(parts)


def parse_action(text: str) -> DroneAction:
    """Parse LLM response into a DroneAction."""
    text = text.strip()
    # Try to extract JSON from response
    if "{" in text:
        start = text.index("{")
        end = text.rindex("}") + 1
        text = text[start:end]
    try:
        data = json.loads(text)
        return DroneAction(
            action_type=data.get("action_type", "fly_to"),
            x=data.get("x"),
            y=data.get("y"),
        )
    except (json.JSONDecodeError, KeyError):
        # Fallback: try to interpret as a simple command
        return DroneAction(action_type="fly_to", x=0, y=0)


def get_model_action(client: OpenAI, obs_text: str) -> str:
    """Get next action from the LLM."""
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": obs_text},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return '{"action_type": "fly_to", "x": 0, "y": 0}'


async def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    env = await DroneEnv.from_docker_image(IMAGE_NAME)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=TASK_NAME, env=BENCHMARK, model=MODEL_NAME)

    try:
        result = await env.reset()
        obs = result.observation

        for step in range(1, MAX_STEPS + 1):
            if result.done:
                break

            obs_text = format_observation(obs)
            raw_action = get_model_action(client, obs_text)
            action = parse_action(raw_action)

            result = await env.step(action)
            obs = result.observation

            reward = result.reward or 0.0
            done = result.done
            error = obs.error

            rewards.append(reward)
            steps_taken = step
            score = obs.score

            action_str = raw_action.replace("\n", " ")[:80]
            log_step(step=step, action=action_str, reward=reward, done=done, error=error)

            if done:
                success = score >= 0.5
                break

    finally:
        try:
            await env.close()
        except Exception as e:
            print(f"[DEBUG] env.close() error: {e}", flush=True)
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


if __name__ == "__main__":
    asyncio.run(main())
