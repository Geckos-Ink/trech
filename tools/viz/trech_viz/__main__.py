"""CLI entrypoint for the TRECH viewer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .playback import load_material_frames, select_physical_window
from .animate import (
    render_material_animation,
    render_trajectory_animation,
    derived_index_line,
    edep_hud_line,
    score_hud_lines,
    select_events,
)
from .renderer import render
from .scene import load_scene
from .trajectories import load_trajectories


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trech-viz",
        description=(
            "Render a TRECH viz scene with sampled trajectories or material-frame playback."
        ),
    )
    parser.add_argument(
        "--scene", default=None,
        help="Path to trech_viz_scene.json (required for the interactive view; optional for "
             "--gif, which then draws only emitted state)",
    )
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
                        help="Render off-screen to an animated GIF: material_frame playback "
                             "with --emits, otherwise Geant4 trajectories with --trajectories")
    parser.add_argument("--stream", default=None,
                        help="material_frame stream to replay when a run emits several "
                             "(default: the first one emitted)")
    parser.add_argument("--reframe", action="store_true",
                        help="material GIF: re-frame the camera on every frame's own extent")
    parser.add_argument("--scores", default=None,
                        help="trech_scores.jsonl whose engine-reported checks join the GIF HUD")
    parser.add_argument("--title", default=None, help="GIF HUD title line")
    parser.add_argument("--clock", choices=["activity", "linear"], default="activity",
                        help="trajectory GIF playback clock: Geant4 step-time quantiles "
                             "(default) or uniform Geant4 time; the HUD shows true time either way")
    parser.add_argument("--colors", type=int, default=None,
                        help="GIF palette size (file size only; default 64)")
    parser.add_argument("--elevation", type=float, default=None,
                        help="GIF camera elevation (rendering choice)")
    parser.add_argument("--color-by", choices=["history", "species", "energy"], default="history",
                        help="trajectory GIF colouring: interaction history (a photon is bright "
                             "until its first recorded interaction, default), particle species, "
                             "or recorded kinetic energy")
    parser.add_argument("--trail", type=float, default=0.12,
                        help="trajectory GIF: recorded points dim with playback age (e-folding "
                             "as a fraction of the clip; 0 keeps full trails)")
    parser.add_argument("--bundle", action="store_true",
                        help="trajectory GIF: merge optical photons with the same wavelength band "
                             "and recorded boundary history into width-weighted mean paths")
    parser.add_argument("--glyphs", action="store_true",
                        help="trajectory GIF: draw composition glyphs (molecules/ions of each "
                             "Geant4 material; representation, not to scale)")
    parser.add_argument("--nuclides", action="store_true",
                        help="trajectory GIF: draw ions as labelled nuclei and label recorded "
                             "nuclide-changing reactions/decays")
    parser.add_argument("--split", action="store_true",
                        help="trajectory GIF: show --compare-trajectories in its own pane")
    parser.add_argument("--charts", default=None,
                        help="trajectory GIF side charts from the recorded tracks: comma list of "
                             "attenuation, bragg, optical, sampling, nuclear, deposit, refraction")
    parser.add_argument("--chart-width", type=int, default=0,
                        help="side chart panel width in pixels (default ~34%% of --width)")
    parser.add_argument("--caption", default=None,
                        help="'|'-separated explanatory lines drawn lower-left")
    parser.add_argument("--display-events", type=int, default=None,
                        help="trajectory GIF: draw only the first N recorded events in 3D "
                             "(charts still use every recorded event)")
    parser.add_argument("--frame", choices=["tracks", "scene"], default="tracks",
                        help="trajectory GIF camera framing: recorded tracks (default) or the "
                             "apparatus volumes (escaping rays leave the frame)")
    parser.add_argument("--tissues", default=None,
                        help="tissues chart: 'MATERIAL_A,MATERIAL_B' probed materials of the two runs")
    parser.add_argument("--incidence-deg", type=float, default=0.0,
                        help="refraction chart: beam incidence angle for the Snell reference")
    parser.add_argument("--events-with", default=None,
                        help="trajectory GIF: show only whole events containing this particle "
                             "(stated in the HUD; tracks are never edited)")
    parser.add_argument("--compare-trajectories", default=None,
                        help="trajectory GIF: overlay a second run's recorded trajectories")
    parser.add_argument("--compare-scene", default=None,
                        help="scene manifest of the --compare-trajectories run (for --derived-n)")
    parser.add_argument("--labels", default=None,
                        help="'this run|comparison run' legend labels for --compare-trajectories")
    parser.add_argument("--compare-scores", default=None,
                        help="trech_scores.jsonl of the --compare-trajectories run (for --edep)")
    parser.add_argument("--edep", default=None,
                        help="volume-name prefix whose Geant4-scored edep joins the HUD")
    parser.add_argument("--derived-n", default=None,
                        help="comma-separated materials whose engine-derived n joins the HUD")
    parser.add_argument("--context-events", type=int, default=0,
                        help="with --events-with, also show the first N ordinary events")
    parser.add_argument("--screenshot", default=None,
                        help="Render off-screen and write PNG instead of opening a window")
    parser.add_argument("--background", choices=["dark", "light"], default="dark")
    parser.add_argument("--width", type=int, default=480, help="GIF/screenshot width")
    parser.add_argument("--height", type=int, default=640, help="GIF/screenshot height")
    parser.add_argument("--seconds", type=float, default=4.0, help="GIF duration")
    parser.add_argument("--fps", type=int, default=10, help="GIF frames per second")
    parser.add_argument("--orbit", type=float, default=16.0,
                        help="GIF camera orbit in degrees (rendering choice)")
    parser.add_argument("--physical-start", type=float, default=None,
                        help="physical seconds at which a retained-clock GIF excerpt starts")
    parser.add_argument("--physical-duration", type=float, default=None,
                        help="physical seconds included in the GIF excerpt")
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


def _track_charts(args, trajectories, compare, scene, compare_scene, names, labels):
    """Side charts computed from the recorded tracks (all recorded events, not just drawn)."""
    if not args.charts:
        return []
    from . import track_charts as tc
    from .tracks_view import Track

    tracks = [Track(traj) for traj in trajectories if traj.points]
    other = [Track(traj) for traj in compare if traj.points]
    scores = tc.last_scores(args.scores)
    charts = []
    for name in [n.strip() for n in args.charts.split(",") if n.strip()]:
        if name == "attenuation":
            charts += tc.attenuation_charts(tracks, scores)
        elif name == "bragg":
            charts += tc.bragg_charts(tracks, scores)
        elif name == "optical":
            charts += tc.optical_charts(tracks, scene=scene)
        elif name == "sampling":
            charts += tc.optical_charts(tracks, sampling=True)
        elif name == "nuclear":
            charts += tc.nuclear_charts(tracks)
        elif name == "deposit":
            charts += tc.deposit_charts(tracks, scores)
        elif name == "tissues":
            tissues = [t.strip() for t in (args.tissues or "").split(",") if t.strip()]
            charts += tc.tissue_compare_charts(
                [scores, tc.last_scores(args.compare_scores)], list(labels), tissues,
                args.edep or "receiver_coil")
        elif name == "refraction" and other:
            def index_of(sc):
                if sc is None or not names:
                    return None
                entry = sc.derived_by_name().get(names[0].lower())
                return entry.mean_refractive_index if entry is not None and entry.available else None
            charts += tc.refraction_compare_chart([tracks, other], list(labels),
                                                  [index_of(scene), index_of(compare_scene)],
                                                  args.incidence_deg)
        else:
            raise SystemExit(f"unknown or inapplicable chart: {name}")
    return charts


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    scene = None
    if args.scene:
        scene_path = Path(args.scene).expanduser().resolve()
        if not scene_path.exists():
            parser.error(f"scene file not found: {scene_path}")
            return 2
        scene = load_scene(scene_path)
    elif not args.gif:
        parser.error("--scene is required for the interactive view and screenshots")
        return 2
    if args.gif:
        if args.colors:
            from . import animate
            animate.GIF_COLORS = max(16, min(256, int(args.colors)))
        gif = str(Path(args.gif).expanduser().resolve())
        still = str(Path(args.screenshot).expanduser().resolve()) if args.screenshot else None
        extra = {} if args.elevation is None else {"elevation": args.elevation}
        if not args.emits:
            if not args.trajectories:
                parser.error("--gif requires --emits (material_frame) or --trajectories")
            traj_path = Path(args.trajectories).expanduser().resolve()
            if not traj_path.exists():
                parser.error(f"trajectories file not found: {traj_path}")
            trajectories = load_trajectories(traj_path)
            trajectories, selection = select_events(
                trajectories, args.events_with, args.context_events
            )
            if args.trajectory_limit:
                trajectories = trajectories[: args.trajectory_limit]
            if not trajectories:
                parser.error(f"no recorded trajectories selected from: {traj_path}")
            compare, labels = [], ("", "")
            if args.compare_trajectories:
                compare_path = Path(args.compare_trajectories).expanduser().resolve()
                if not compare_path.exists():
                    parser.error(f"comparison trajectories not found: {compare_path}")
                compare = load_trajectories(compare_path)
                if args.trajectory_limit:
                    compare = compare[: args.trajectory_limit]
            if args.labels:
                first, _, second = args.labels.partition("|")
                labels = (first.strip(), second.strip())
            compare_scene = (load_scene(Path(args.compare_scene).expanduser().resolve())
                             if args.compare_scene else scene)
            names = ([name.strip() for name in args.derived_n.split(",") if name.strip()]
                     if args.derived_n else [])
            hud_a = [selection] if selection else []
            hud_b: list = []
            if names:
                hud_a.append(derived_index_line(scene, names, "" if args.split else labels[0]))
                if compare:
                    hud_b.append(derived_index_line(compare_scene, names,
                                                    "" if args.split else labels[1]))
            if args.edep and args.scores:
                hud_a.append(edep_hud_line(args.scores, args.edep,
                                           "" if args.split else labels[0]))
            if args.edep and args.compare_scores:
                hud_b.append(edep_hud_line(args.compare_scores, args.edep,
                                           "" if args.split else labels[1]))
            hud_a = [line for line in hud_a if line] + (
                score_hud_lines(args.scores) if args.scores else [])
            hud_b = [line for line in hud_b if line] + (
                score_hud_lines(args.compare_scores) if args.compare_scores else [])
            from .tracks_view import load_run, render_tracks

            runs = [load_run(trajectories, label=labels[0], hud=hud_a, scene=scene,
                             display_events=args.display_events)]
            if compare:
                runs.append(load_run(compare, label=labels[1], hud=hud_b, scene=compare_scene,
                                     display_events=args.display_events, run_index=1))
            charts = _track_charts(args, trajectories, compare, scene, compare_scene, names,
                                   labels)
            render_tracks(
                runs, gif=gif, screenshot=still, background=args.background,
                title=args.title or "", window_size=(args.width, args.height), fps=args.fps,
                seconds=args.seconds, orbit_deg=args.orbit, clock=args.clock,
                color_by=args.color_by, trail=max(0.0, args.trail), bundle=args.bundle,
                glyphs=args.glyphs, nuclides=args.nuclides, split=args.split and bool(compare),
                charts=charts, chart_width=args.chart_width,
                focus=args.frame if args.frame == "scene" else None,
                caption=[line for line in (args.caption or "").split("|") if line.strip()],
                **extra,
            )
            return 0
        emits_path = Path(args.emits).expanduser().resolve()
        if not emits_path.exists():
            parser.error(f"hook-emits file not found: {emits_path}")
        frames = load_material_frames(emits_path, stream=args.stream)
        if not frames:
            parser.error(f"no valid material_frame emits found: {emits_path}")
        try:
            frames = select_physical_window(
                frames, start_s=args.physical_start, duration_s=args.physical_duration
            )
        except ValueError as exc:
            parser.error(str(exc))
        render_material_animation(
            scene, frames, gif=gif, screenshot=still,
            background=args.background, show_volumes=not args.no_volumes,
            window_size=(args.width, args.height), fps=args.fps, seconds=args.seconds,
            orbit_deg=args.orbit, title=args.title, reframe=args.reframe,
            chart_width=args.chart_width,
            caption=[line for line in (args.caption or "").split("|") if line.strip()], **extra,
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
