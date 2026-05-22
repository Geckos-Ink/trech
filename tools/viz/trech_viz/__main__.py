"""CLI entrypoint for the TRECH viewer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .renderer import render
from .scene import load_scene
from .trajectories import load_trajectories


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trech-viz",
        description=(
            "Render a TRECH viz scene + sampled photon trajectories in a 3D window."
        ),
    )
    parser.add_argument("--scene", required=True, help="Path to trech_viz_scene.json")
    parser.add_argument(
        "--trajectories",
        default=None,
        help="Path to trech_viz_trajectories.jsonl (optional, default disabled)",
    )
    parser.add_argument("--screenshot", default=None,
                        help="Render off-screen and write PNG instead of opening a window")
    parser.add_argument("--background", choices=["dark", "light"], default="dark")
    parser.add_argument("--no-volumes", action="store_true", help="Hide volume meshes")
    parser.add_argument("--no-trajectories", action="store_true",
                        help="Hide photon polylines")
    parser.add_argument("--trajectory-limit", type=int, default=None,
                        help="Render at most N trajectories (default: all)")
    parser.add_argument("--no-time-slider", action="store_true",
                        help="Disable the interactive time slider widget")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    scene_path = Path(args.scene).expanduser().resolve()
    if not scene_path.exists():
        parser.error(f"scene file not found: {scene_path}")
        return 2

    scene = load_scene(scene_path)
    trajectories = []
    if args.trajectories and not args.no_trajectories:
        traj_path = Path(args.trajectories).expanduser().resolve()
        if traj_path.exists():
            trajectories = load_trajectories(traj_path)
        else:
            print(f"warning: trajectories file not found: {traj_path}", file=sys.stderr)

    render(
        scene,
        trajectories,
        screenshot=args.screenshot,
        background=args.background,
        show_volumes=not args.no_volumes,
        show_trajectories=not args.no_trajectories,
        trajectory_limit=args.trajectory_limit,
        enable_time_slider=not args.no_time_slider,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
