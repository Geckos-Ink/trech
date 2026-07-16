"""CLI entrypoint for the TRECH viewer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .playback import load_material_frames
from .renderer import render, render_material_animation
from .scene import load_scene
from .trajectories import load_trajectories


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trech-viz",
        description=(
            "Render a TRECH viz scene with sampled trajectories or material-frame playback."
        ),
    )
    parser.add_argument("--scene", required=True, help="Path to trech_viz_scene.json")
    parser.add_argument(
        "--trajectories",
        default=None,
        help="Path to trech_viz_trajectories.jsonl (optional, default disabled)",
    )
    parser.add_argument(
        "--emits", default=None,
        help="Path to trech_hook_emits.jsonl (enables material_frame observer playback)",
    )
    parser.add_argument("--gif", default=None,
                        help="Render material_frame playback off-screen to an animated GIF")
    parser.add_argument("--screenshot", default=None,
                        help="Render off-screen and write PNG instead of opening a window")
    parser.add_argument("--background", choices=["dark", "light"], default="dark")
    parser.add_argument("--width", type=int, default=480, help="GIF/screenshot width")
    parser.add_argument("--height", type=int, default=640, help="GIF/screenshot height")
    parser.add_argument("--seconds", type=float, default=4.0, help="GIF duration")
    parser.add_argument("--fps", type=int, default=10, help="GIF frames per second")
    parser.add_argument("--orbit", type=float, default=16.0,
                        help="GIF camera orbit in degrees (rendering choice)")
    parser.add_argument("--no-world", action="store_true", help="Hide the world wireframe")
    parser.add_argument("--no-volumes", action="store_true", help="Hide volume meshes")
    parser.add_argument("--no-beams", action="store_true", help="Hide authored beam arrows")
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
    if args.gif:
        if not args.emits:
            parser.error("--gif requires --emits trech_hook_emits.jsonl")
        emits_path = Path(args.emits).expanduser().resolve()
        if not emits_path.exists():
            parser.error(f"hook-emits file not found: {emits_path}")
        frames = load_material_frames(emits_path)
        if not frames:
            parser.error(f"no valid material_frame emits found: {emits_path}")
        render_material_animation(
            scene, frames, gif=str(Path(args.gif).expanduser().resolve()),
            screenshot=(str(Path(args.screenshot).expanduser().resolve()) if args.screenshot else None),
            background=args.background, show_volumes=not args.no_volumes,
            window_size=(args.width, args.height), fps=args.fps, seconds=args.seconds,
            orbit_deg=args.orbit,
        )
        return 0

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
        show_world=not args.no_world,
        show_volumes=not args.no_volumes,
        show_beams=not args.no_beams,
        show_trajectories=not args.no_trajectories,
        trajectory_limit=args.trajectory_limit,
        window_size=(args.width, args.height),
        enable_time_slider=not args.no_time_slider,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
