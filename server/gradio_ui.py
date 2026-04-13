# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Custom Gradio tab for the Drone Delivery environment.

Renders a 2D grid visualization showing the warehouse, delivery houses,
and the current drone position. Mirrors the structure of wordle's custom
gradio_ui.py: build_drone_gradio_app is passed to create_app via the
gradio_builder parameter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
from openenv.core.env_server.types import EnvironmentMetadata

try:
    from ..models import DroneAction, VALID_ACTION_TYPES
except (ModuleNotFoundError, ImportError):
    from models import DroneAction, VALID_ACTION_TYPES

VALID_TASKS = ["easy", "medium", "hard"]


CELL = 40  # pixels per grid cell
PAD = 20   # svg padding


def _snapshot(env: Any) -> Optional[Dict[str, Any]]:
    """Pull a state snapshot off a DroneEnvironment instance.

    Returns None if the env doesn't expose the expected private attributes
    (e.g. during startup before reset, or if it's a different env type).
    """
    try:
        task_name = getattr(env, "_task_name", "easy")
        task_config = getattr(env, "_task_config", None)
        if task_config is None:
            return None
        warehouse = task_config["warehouse"]
        houses = task_config["houses"]
        max_steps = task_config.get("max_steps")
        drone_pos = getattr(env, "_drone_pos", warehouse)
        delivered = dict(getattr(env, "_delivered", {}))
        carried = getattr(env, "_packages_carried", 0)
        distance = getattr(env, "_distance_traveled", 0.0)
        state = getattr(env, "_state", None)
        steps = getattr(state, "step_count", 0) if state is not None else 0
        return {
            "task_name": task_name,
            "warehouse": tuple(warehouse),
            "houses": list(houses),
            "max_steps": max_steps,
            "drone_pos": tuple(drone_pos),
            "delivered": delivered,
            "carried": carried,
            "distance": float(distance),
            "steps": int(steps),
        }
    except Exception:
        return None


def _grid_bounds(
    warehouse: Tuple[int, int], houses: List[Tuple[str, int, int]], drone: Tuple[int, int]
) -> Tuple[int, int, int, int]:
    """Compute (min_x, min_y, max_x, max_y) with a 1-cell margin."""
    xs = [warehouse[0], drone[0]] + [h[1] for h in houses]
    ys = [warehouse[1], drone[1]] + [h[2] for h in houses]
    min_x, max_x = min(xs) - 1, max(xs) + 1
    min_y, max_y = min(ys) - 1, max(ys) + 1
    # Keep at least an 8x8 viewport so the picture doesn't look cramped
    if max_x - min_x < 8:
        pad = (8 - (max_x - min_x)) // 2 + 1
        min_x -= pad
        max_x += pad
    if max_y - min_y < 8:
        pad = (8 - (max_y - min_y)) // 2 + 1
        min_y -= pad
        max_y += pad
    return min_x, min_y, max_x, max_y


def _render_svg(snap: Dict[str, Any]) -> str:
    warehouse = snap["warehouse"]
    houses = snap["houses"]
    drone = snap["drone_pos"]
    delivered = snap["delivered"]

    min_x, min_y, max_x, max_y = _grid_bounds(warehouse, houses, drone)
    cols = max_x - min_x + 1
    rows = max_y - min_y + 1
    width = cols * CELL + 2 * PAD
    height = rows * CELL + 2 * PAD

    def px(x: int, y: int) -> Tuple[int, int]:
        # Flip y so positive y is "up" visually
        cx = PAD + (x - min_x) * CELL + CELL // 2
        cy = PAD + (max_y - y) * CELL + CELL // 2
        return cx, cy

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'style="background:#0f172a; border-radius:8px; font-family:\'IBM Plex Sans\', Arial, sans-serif;">'
    )

    # Grid lines
    for c in range(cols + 1):
        x = PAD + c * CELL
        parts.append(
            f'<line x1="{x}" y1="{PAD}" x2="{x}" y2="{PAD + rows * CELL}" '
            f'stroke="#1e293b" stroke-width="1"/>'
        )
    for r in range(rows + 1):
        y = PAD + r * CELL
        parts.append(
            f'<line x1="{PAD}" y1="{y}" x2="{PAD + cols * CELL}" y2="{y}" '
            f'stroke="#1e293b" stroke-width="1"/>'
        )

    # Axis labels
    for c in range(cols):
        lx = PAD + c * CELL + CELL // 2
        parts.append(
            f'<text x="{lx}" y="{PAD + rows * CELL + 14}" text-anchor="middle" '
            f'fill="#64748b" font-size="10">{min_x + c}</text>'
        )
    for r in range(rows):
        ly = PAD + r * CELL + CELL // 2 + 4
        parts.append(
            f'<text x="{PAD - 6}" y="{ly}" text-anchor="end" '
            f'fill="#64748b" font-size="10">{max_y - r}</text>'
        )

    # Optimal route preview (warehouse -> houses in given order, dashed)
    route_pts = [warehouse] + [(h[1], h[2]) for h in houses]
    route_pixels = [px(pt[0], pt[1]) for pt in route_pts]
    poly = " ".join(f"{a},{b}" for a, b in route_pixels)
    parts.append(
        f'<polyline points="{poly}" fill="none" stroke="#334155" '
        f'stroke-width="1.5" stroke-dasharray="4 3"/>'
    )

    # Warehouse
    wx, wy = px(*warehouse)
    parts.append(
        f'<rect x="{wx - 14}" y="{wy - 14}" width="28" height="28" rx="4" '
        f'fill="#2563eb" stroke="#93c5fd" stroke-width="2"/>'
    )
    parts.append(
        f'<text x="{wx}" y="{wy + 5}" text-anchor="middle" fill="white" '
        f'font-size="16" font-weight="700">W</text>'
    )

    # Houses
    for name, hx, hy in houses:
        cx, cy = px(hx, hy)
        is_delivered = bool(delivered.get(name, False))
        fill = "#16a34a" if is_delivered else "#dc2626"
        stroke = "#86efac" if is_delivered else "#fca5a5"
        # House glyph: triangle roof + square body
        parts.append(
            f'<polygon points="{cx - 14},{cy - 2} {cx},{cy - 16} {cx + 14},{cy - 2}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )
        parts.append(
            f'<rect x="{cx - 12}" y="{cy - 2}" width="24" height="16" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{cx}" y="{cy + 11}" text-anchor="middle" fill="white" '
            f'font-size="11" font-weight="700">{name}</text>'
        )

    # Drone (always drawn on top)
    dx, dy = px(*drone)
    parts.append(
        f'<circle cx="{dx}" cy="{dy}" r="12" fill="#facc15" '
        f'stroke="#fde68a" stroke-width="3"/>'
    )
    parts.append(
        f'<text x="{dx}" y="{dy + 5}" text-anchor="middle" fill="#0f172a" '
        f'font-size="14" font-weight="800">D</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def _stats_html(snap: Dict[str, Any]) -> str:
    delivered = snap["delivered"]
    total = len(snap["houses"])
    done = sum(1 for v in delivered.values() if v)
    max_steps = snap["max_steps"]
    steps_str = f'{snap["steps"]}/{max_steps}' if max_steps else str(snap["steps"])
    return f"""
<div style="display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px 24px;
            font-family:'IBM Plex Sans', Arial, sans-serif; color:#0f172a; max-width:360px;">
  <div><strong>Task</strong></div><div>{snap['task_name']}</div>
  <div><strong>Drone</strong></div><div>({snap['drone_pos'][0]}, {snap['drone_pos'][1]})</div>
  <div><strong>Warehouse</strong></div><div>({snap['warehouse'][0]}, {snap['warehouse'][1]})</div>
  <div><strong>Carrying</strong></div><div>{snap['carried']}</div>
  <div><strong>Delivered</strong></div><div>{done} / {total}</div>
  <div><strong>Steps</strong></div><div>{steps_str}</div>
  <div><strong>Distance</strong></div><div>{snap['distance']:.2f}</div>
</div>
"""


def _empty_html() -> str:
    return """
<div style="padding:16px; font-family:'IBM Plex Sans', Arial, sans-serif; color:#475569;">
  No drone environment state yet. Hit <strong>Reset</strong> in the Playground tab
  (optionally with <code>task=easy|medium|hard</code>), then click <strong>Refresh</strong>
  here to render the grid.
</div>
"""


def _render(env: Any) -> Tuple[str, str]:
    snap = _snapshot(env)
    if snap is None:
        return _empty_html(), ""
    return _render_svg(snap), _stats_html(snap)


def build_drone_gradio_app(
    web_manager: Any,
    action_fields: List[Dict[str, Any]],
    metadata: Optional[EnvironmentMetadata],
    is_chat_env: bool,
    title: str,
    quick_start_md: str,
) -> gr.Blocks:
    """Build the Custom tab for the drone environment."""

    def _refresh() -> Tuple[str, str, str]:
        env = getattr(web_manager, "env", None)
        svg, stats = _render(env)
        return svg, stats, ""

    def _do_reset(task: str) -> Tuple[str, str, str]:
        env = getattr(web_manager, "env", None)
        if env is None:
            return _empty_html(), "", "No environment bound."
        try:
            env.reset(task=task)
            msg = f"Reset to task '{task}'."
        except Exception as e:
            msg = f"Reset failed: {e}"
        svg, stats = _render(env)
        return svg, stats, msg

    def _do_step(action_type: str, x: float, y: float) -> Tuple[str, str, str]:
        env = getattr(web_manager, "env", None)
        if env is None:
            return _empty_html(), "", "No environment bound."
        try:
            kwargs: Dict[str, Any] = {"action_type": action_type}
            if action_type == "fly_to":
                kwargs["x"] = int(x)
                kwargs["y"] = int(y)
            action = DroneAction(**kwargs)
            obs = env.step(action)
            if obs.error:
                msg = f"Step error: {obs.error}"
            else:
                msg = f"Step ok: {action_type}"
        except Exception as e:
            msg = f"Step failed (parse-time validation): {e}"
        svg, stats = _render(env)
        return svg, stats, msg

    with gr.Blocks(title=f"{title} — Drone Visualization") as blocks:
        gr.Markdown("# Drone Delivery Visualization")
        gr.Markdown(
            "A 2D grid view of the drone (**D**), warehouse (**W**), and houses. "
            "Red houses are pending; green houses are delivered. The dashed line is "
            "the house list in task order (not the optimal route). "
            "Dropdowns below constrain action_type/task so invalid inputs are "
            "structurally impossible from this UI."
        )

        with gr.Row():
            task_dd = gr.Dropdown(
                choices=VALID_TASKS, value="easy", label="Task", interactive=True
            )
            reset_btn = gr.Button("Reset", variant="secondary")
            refresh_btn = gr.Button("Refresh", variant="primary")

        with gr.Row():
            action_dd = gr.Dropdown(
                choices=list(VALID_ACTION_TYPES),
                value="pick_up",
                label="action_type",
                interactive=True,
            )
            x_in = gr.Number(value=0, label="x (fly_to only)", precision=0)
            y_in = gr.Number(value=0, label="y (fly_to only)", precision=0)
            step_btn = gr.Button("Step", variant="primary")

        status_md = gr.Markdown(value="")

        with gr.Row():
            svg_html = gr.HTML(value=_empty_html(), show_label=False)
            stats_html = gr.HTML(value="", show_label=False)

        refresh_btn.click(
            fn=_refresh, inputs=None, outputs=[svg_html, stats_html, status_md]
        )
        reset_btn.click(
            fn=_do_reset, inputs=[task_dd], outputs=[svg_html, stats_html, status_md]
        )
        step_btn.click(
            fn=_do_step,
            inputs=[action_dd, x_in, y_in],
            outputs=[svg_html, stats_html, status_md],
        )
        blocks.load(fn=_refresh, inputs=None, outputs=[svg_html, stats_html, status_md])

    return blocks
