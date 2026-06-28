"""Render the osmotic-dehydration hook scenario as a 3D animation.

The video is a replay of TRECH output, not a closed-form osmosis illustration:

* ``testscenario_osmotic.js`` advances a deterministic coarse-grained H2O /
  glucose bath from Geant4 event callbacks. One event is one MD tick.
* The script consumes only ``trech_hook_emits.jsonl`` sidebands
  (``osmotic_particles`` and ``final_summary``). It does not use a fixed
  osmotic law to move particles or draw an expected curve.
* The count plot is the emitted simulation history. It is suitable as training
  / validation signal for larger-scale surrogate work, while any learned
  inference path must still be gated against high-fidelity TRECH/Geant4 runs.

Run::

    trech run examples/experiments/testscenario_osmotic.js \
        --events 6000 --output build/dev/out_osmotic

    cd tools/viz
    source .venv/bin/activate
    python demos/render_osmotic.py

Output: ``tools/viz/demos/osmotic_dehydration.mp4``.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_osmotic"
DEFAULT_OUT = Path(__file__).resolve().parent / "osmotic_dehydration.mp4"

BG_COLOR = "#15171c"
FG_COLOR = "#e8edf2"
GRID_COLOR = "#4a515c"
WATER_COLOR = "#5cc8ff"
GLUCOSE_COLOR = "#f2a65a"
MEMBRANE_COLOR = "#d8d8d8"
TRECH_GREEN = "#7fdc7f"


def load_emits(run_dir: Path) -> Tuple[Dict, List[Dict], Optional[Dict]]:
    emits = run_dir / "trech_hook_emits.jsonl"
    if not emits.exists():
        raise SystemExit(f"error: {emits} not found; run testscenario_osmotic.js first")
    scenario: Optional[Dict] = None
    summary: Optional[Dict] = None
    snapshots: List[Dict] = []
    with emits.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            payload = rec.get("payload") or {}
            tag = rec.get("tag")
            if tag == "scenario" and scenario is None:
                scenario = payload
            elif tag == "osmotic_particles":
                snapshots.append(payload)
            elif tag == "final_summary":
                summary = payload
    if scenario is None:
        raise SystemExit("error: no scenario emit found")
    if not snapshots:
        raise SystemExit(
            "error: no osmotic_particles emits found; re-run the scenario with "
            "the snapshot-emitting testscenario_osmotic.js")
    snapshots.sort(key=lambda p: int(p.get("tick", 0)))
    return scenario, snapshots, summary


def pore_angles(count: int) -> List[float]:
    return [(2.0 * math.pi * i) / count for i in range(count)]


def angle_delta(a: float, b: float) -> float:
    d = a - b
    while d > math.pi:
        d -= 2.0 * math.pi
    while d < -math.pi:
        d += 2.0 * math.pi
    return d


def membrane_segments(radius: float, pores: Iterable[float],
                      half_width: float) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    thetas = np.linspace(-math.pi, math.pi, 900)
    pore_list = list(pores)
    keep = []
    for th in thetas:
        keep.append(not any(abs(angle_delta(th, p)) <= half_width for p in pore_list))
    segments: List[Tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    start = None
    for idx, ok in enumerate(keep + [False]):
        if ok and start is None:
            start = idx
        elif not ok and start is not None:
            end = idx
            th = thetas[start:end]
            if len(th) > 1:
                x = radius * np.cos(th)
                y = radius * np.sin(th)
                z = np.zeros_like(x)
                segments.append((x, y, z))
            start = None
    return segments


def particle_z(p: Dict) -> float:
    pid = int(p.get("id", 0))
    return (0.32 if p.get("i") else -0.32) + 0.08 * math.sin(pid * 1.618)


def particle_arrays(snapshot: Dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    water_in, water_out, glucose_in, glucose_out = [], [], [], []
    for p in snapshot.get("particles") or []:
        # z is a visualization depth cue only; x/y are the emitted simulation state.
        z = particle_z(p)
        row = [float(p["x"]), float(p["y"]), z]
        if p.get("k") == "h2o":
            (water_in if p.get("i") else water_out).append(row)
        else:
            (glucose_in if p.get("i") else glucose_out).append(row)
    def arr(rows: List[List[float]]) -> np.ndarray:
        return np.array(rows, dtype=float) if rows else np.zeros((0, 3), dtype=float)
    return arr(water_in), arr(water_out), arr(glucose_in), arr(glucose_out)


def water_trails(snapshots: List[Dict], snap_idx: int,
                 window: int = 6) -> List[Tuple[np.ndarray, bool]]:
    start = max(0, snap_idx - window)
    by_id: Dict[int, List[Tuple[float, float, float, bool]]] = {}
    for snap in snapshots[start:snap_idx + 1]:
        for p in snap.get("particles") or []:
            if p.get("k") != "h2o":
                continue
            pid = int(p.get("id", 0))
            by_id.setdefault(pid, []).append(
                (float(p["x"]), float(p["y"]), particle_z(p), bool(p.get("i"))))
    crossing: List[Tuple[np.ndarray, bool]] = []
    background: List[Tuple[np.ndarray, bool]] = []
    for pid, rows in by_id.items():
        if len(rows) < 2:
            continue
        crossed = any(rows[i][3] != rows[i - 1][3] for i in range(1, len(rows)))
        trail = (np.array([r[:3] for r in rows], dtype=float), crossed)
        if crossed and pid % 3 == 0 and len(crossing) < 28:
            crossing.append(trail)
        elif not crossed and pid % 19 == 0 and len(background) < 10:
            background.append(trail)
    return background + crossing


def phase_color(phase: str) -> str:
    if phase == "thermalization":
        return "#90caf9"
    if phase == "local_diffusion":
        return "#b39ddb"
    if phase == "macroscopic_flux":
        return TRECH_GREEN
    return "#ffd166"


def encode_video(frames_dir: Path, out: Path, fps: int) -> int:
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
    return res.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--frames-dir", type=Path, default=None)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--hold-seconds", type=float, default=2.5)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--keep-frames", action="store_true")
    args = ap.parse_args()

    scenario, snapshots, summary = load_emits(args.run)
    radius = float(scenario["cellRadius"])
    half = float(scenario["domainHalfSize"])
    pore_count = int(scenario["pores"])
    pore_half = float(scenario["poreHalfWidth"])
    water_radius = float(scenario.get("waterRadius") or 0.5)
    glucose_radius = float(scenario.get("glucoseRadius") or 1.75)
    total_ticks = int(scenario.get("ticks") or snapshots[-1]["tick"])

    frames_dir = args.frames_dir or args.out.parent / (args.out.stem + "_frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    counts_t = np.array([int(s["tick"]) for s in snapshots])
    inside_h2o = np.array([int(s["inside_h2o"]) for s in snapshots])
    outside_h2o = np.array([int(s["outside_h2o"]) for s in snapshots])
    flux = np.array([int(s["net_water_flux_out"]) for s in snapshots])
    membrane = membrane_segments(radius, pore_angles(pore_count), pore_half)

    n_anim = len(snapshots)
    n_hold = int(round(args.hold_seconds * args.fps))
    n_frames = n_anim + n_hold
    dpi = 100
    figsize = (args.width / dpi, args.height / dpi)
    print(f"loaded {n_anim} osmotic_particles emits from {args.run}")
    print(f"rendering {n_frames} frames @ {args.fps} fps")

    for frame_idx in range(n_frames):
        snap_idx = min(frame_idx, n_anim - 1)
        snap = snapshots[snap_idx]
        tick = int(snap["tick"])
        phase = str(snap.get("phase") or "")
        end_card = frame_idx >= n_anim

        fig = plt.figure(figsize=figsize, dpi=dpi, facecolor=BG_COLOR)
        gs = GridSpec(1, 2, width_ratios=[1.18, 1.0], figure=fig,
                      left=0.035, right=0.975, top=0.88, bottom=0.11,
                      wspace=0.16)
        ax = fig.add_subplot(gs[0, 0], projection="3d", facecolor=BG_COLOR)
        ax.set_box_aspect((1, 1, 0.28))
        ax.view_init(elev=36, azim=-55 + 0.28 * frame_idx)
        ax.set_xlim(-half, half)
        ax.set_ylim(-half, half)
        ax.set_zlim(-4.0, 4.0)
        ax.set_xlabel("x", color=FG_COLOR, labelpad=-6)
        ax.set_ylabel("y", color=FG_COLOR, labelpad=-6)
        ax.set_zticks([])
        ax.tick_params(colors="#aeb6c2", labelsize=7)
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.pane.set_facecolor((0.08, 0.09, 0.11, 1.0))
            axis.pane.set_edgecolor(GRID_COLOR)
        ax.grid(True, color=GRID_COLOR, alpha=0.35)

        for x, y, z in membrane:
            ax.plot(x, y, z, color=MEMBRANE_COLOR, lw=2.0, alpha=0.9)
        th_fill = np.linspace(0, 2.0 * math.pi, 96)
        rr = np.linspace(0, radius, 16)
        rr_grid, th_grid = np.meshgrid(rr, th_fill)
        ax.plot_surface(rr_grid * np.cos(th_grid), rr_grid * np.sin(th_grid),
                        np.zeros_like(rr_grid) - 0.03, color="#3d5668",
                        alpha=0.08, linewidth=0, shade=False)
        # Sparse vertical ticks make the pored membrane read as a shallow 3D ring.
        for th in np.linspace(0, 2.0 * math.pi, 48, endpoint=False):
            if any(abs(angle_delta(th, p)) <= pore_half for p in pore_angles(pore_count)):
                continue
            x, y = radius * math.cos(th), radius * math.sin(th)
            ax.plot([x, x], [y, y], [-0.55, 0.55],
                    color=MEMBRANE_COLOR, lw=0.8, alpha=0.55)
        for pth in pore_angles(pore_count):
            px = radius * math.cos(pth)
            py = radius * math.sin(pth)
            ax.scatter([px], [py], [0.0], s=42, c="#9be7ff",
                       alpha=0.95, edgecolors="#0e1116", linewidths=0.25)
            flux_len = min(8.0, max(0.0, float(snap["net_water_flux_out"])) * 0.08)
            if flux_len > 0.1:
                ax.quiver(px, py, 0.12, math.cos(pth), math.sin(pth), 0.0,
                          length=flux_len, normalize=True, color=TRECH_GREEN,
                          alpha=0.62, linewidth=1.0, arrow_length_ratio=0.28)

        for trail, crossed in water_trails(snapshots, snap_idx):
            ax.plot(trail[:, 0], trail[:, 1], trail[:, 2],
                    color=("#e9fbff" if crossed else WATER_COLOR),
                    lw=(1.8 if crossed else 0.7),
                    alpha=(0.90 if crossed else 0.22))

        wi, wo, gi, go = particle_arrays(snap)
        def scatter(points: np.ndarray, color: str, size: float, alpha: float,
                    label: str) -> None:
            if len(points):
                ax.scatter(points[:, 0], points[:, 1], points[:, 2],
                           s=size, c=color, alpha=alpha, depthshade=True,
                           edgecolors="#0e1116", linewidths=0.25, label=label)
        scatter(wo, WATER_COLOR, 55 * water_radius, 0.62, "H2O outside")
        scatter(wi, WATER_COLOR, 55 * water_radius, 0.95, "H2O inside")
        scatter(go, GLUCOSE_COLOR, 80 * glucose_radius, 0.50, "glucose outside")
        scatter(gi, GLUCOSE_COLOR, 80 * glucose_radius, 0.92, "glucose inside")
        leg = ax.legend(loc="upper left", fontsize=8, facecolor="#20242c",
                        edgecolor=GRID_COLOR)
        for txt in leg.get_texts():
            txt.set_color(FG_COLOR)

        ax2 = fig.add_subplot(gs[0, 1], facecolor=BG_COLOR)
        for spine in ax2.spines.values():
            spine.set_color(GRID_COLOR)
        ax2.tick_params(colors=FG_COLOR, labelsize=9)
        ax2.set_xlim(0, total_ticks)
        ax2.set_ylim(0, max(100, float(max(outside_h2o.max(), inside_h2o.max())) + 8))
        ax2.set_xlabel("TRECH event tick", color=FG_COLOR)
        ax2.set_ylabel("H2O count", color=FG_COLOR)
        ax2.plot(counts_t[:snap_idx + 1], inside_h2o[:snap_idx + 1],
                 color="#3b8bd9", lw=2.2, label="inside H2O")
        ax2.plot(counts_t[:snap_idx + 1], outside_h2o[:snap_idx + 1],
                 color=WATER_COLOR, lw=2.2, label="outside H2O")
        ax2b = ax2.twinx()
        ax2b.set_ylim(0, max(85, float(flux.max()) + 5))
        ax2b.tick_params(colors="#b6f5b6", labelsize=9)
        ax2b.set_ylabel("net water flux out", color="#b6f5b6")
        ax2b.plot(counts_t[:snap_idx + 1], flux[:snap_idx + 1],
                  color=TRECH_GREEN, lw=1.7, ls="--", label="net flux out")
        ax2.axvline(50, color="#777d88", lw=0.8, ls=":")
        ax2.axvline(500, color="#777d88", lw=0.8, ls=":")
        ax2.axvline(5000, color="#777d88", lw=0.8, ls=":")
        ax2.grid(True, color=GRID_COLOR, alpha=0.28)
        leg2 = ax2.legend(loc="upper right", fontsize=8, facecolor="#20242c",
                          edgecolor=GRID_COLOR)
        for txt in leg2.get_texts():
            txt.set_color(FG_COLOR)

        fig.suptitle(
            "TRECH osmotic dehydration replay — Geant4 event clock + deterministic hook MD",
            color=FG_COLOR, fontsize=13, y=0.965)
        phase_c = phase_color(phase)
        hud = (
            f"tick {tick:4d}/{total_ticks}   phase={phase}   "
            f"H2O in/out={snap['inside_h2o']}/{snap['outside_h2o']}   "
            f"glucose in/out={snap['inside_glucose']}/{snap['outside_glucose']}   "
            f"net flux out={snap['net_water_flux_out']}"
        )
        fig.text(0.035, 0.045, hud, color=phase_c, fontsize=9.5,
                 family="monospace")
        fig.text(
            0.035, 0.018,
            "Replay of emitted TRECH state. No fixed osmotic law drives this "
            "video; larger-scale surrogates must be trained/gated from runs like this.",
            color="#9aa3ad", fontsize=8.5)

        if end_card and summary:
            val = summary.get("validation") or {}
            late = summary.get("late_pressure_average") or {}
            ratio = (late.get("external", 0.0) / late.get("internal", 1.0)
                     if late.get("internal") else float("inf"))
            lines = [
                f"validation checks: {sum(1 for v in val.values() if v)}/{len(val)}",
                f"net water flux out: {summary.get('net_water_flux_out')}",
                f"first crossing tick: {summary.get('first_crossing_tick')}",
                f"max mean KE: {summary.get('max_observed_mean_kinetic_energy', 0):.3f} "
                f"vs target {summary.get('target_mean_kinetic_energy', 0):.3f}",
                f"late pressure external/internal: {ratio:.2f}",
            ]
            fig.text(0.50, 0.19, "\n".join(lines), ha="center", va="bottom",
                     color=FG_COLOR, fontsize=10, family="monospace",
                     bbox=dict(facecolor="#23272e", edgecolor=TRECH_GREEN,
                               boxstyle="round,pad=0.6", alpha=0.94))

        fig.savefig(frames_dir / f"frame_{frame_idx:04d}.png", facecolor=BG_COLOR)
        plt.close(fig)
        if (frame_idx + 1) % 50 == 0 or frame_idx + 1 == n_frames:
            print(f"  frame {frame_idx + 1}/{n_frames}")

    print(f"encoding {args.out}")
    rc = encode_video(frames_dir, args.out, args.fps)
    if rc == 0 and not args.keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)
    if rc == 0:
        print(f"wrote {args.out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
