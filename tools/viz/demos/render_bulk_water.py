"""Render the Sputnik bulk-water MD next to the measured liquid structure.

Comparison story (same honesty contract as ``render_glass_of_water.py``):

* **experiment** — liquid water's O-O radial distribution function has its
  first peak at **2.80 Å** (the hydrogen-bond distance; X-ray/neutron
  diffraction, e.g. Skinner 2013 / Soper 2013), with coordination ~4.3.
  Drawn as the amber reference marker; never fed into the simulation.

* **TRECH simulated** — ``h2o_bulk_water.js`` evolves 48 flexible SPC-like
  molecules in a periodic box (minimum image + DSF Coulomb, classical MD in
  the deterministic hook layer; Geant4 is the per-tick clock). The left panel
  replays the emitted ``md_snapshot`` positions verbatim; the right panel
  shows the engine's own O-O g(r) histogram accumulating after equilibration,
  in green.

The point of the video is watching the green curve *grow a first peak at the
experimental hydrogen-bond distance* from nothing but the force field — and
stating the honest residual (the small model over-counts coordination ~5 vs
~4.3 measured) on the end card instead of tuning it away.

Run::

    cd tools/viz
    source .venv/bin/activate
    python demos/render_bulk_water.py            # default run dir + output

Inputs:  ``build/dev/out_h2o_bulk/trech_hook_emits.jsonl`` (scenario,
md_snapshot, bulk_summary emits).
Output: ``tools/viz/demos/h2o_bulk_water_gr.mp4`` (override with ``--out``).
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402

import pyvista as pv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_h2o_bulk"
DEFAULT_OUT = Path(__file__).resolve().parent / "h2o_bulk_water_gr.mp4"

# Experimental liquid-water O-O structure (diffraction; comparison only —
# these numbers never feed the simulation).
EXP_FIRST_PEAK_A = 2.80
EXP_SECOND_PEAK_A = 4.5  # tetrahedral second shell
EXP_COORDINATION = 4.3

# Palette consistent with the glass-of-water comparison demo:
# amber = "what measured physics says", green = "what TRECH actually did".
EXP_COLOR = "#ffb347"
TRECH_COLOR = "#7fdc7f"
BG_COLOR = "#16181d"
FG_COLOR = "#e8e8e8"
O_COLOR = "#d65a4a"
H_COLOR = "#dfe7ee"
BOND_COLOR = "#8fa3b5"


# ----------------------------------------------------------------- emit input


def load_emits(run_dir: Path):
    """Return (scenario, snapshots, summary) from trech_hook_emits.jsonl."""
    emits_path = run_dir / "trech_hook_emits.jsonl"
    if not emits_path.exists():
        raise SystemExit(f"error: {emits_path} not found; run h2o_bulk_water.js first")
    scenario: Optional[Dict] = None
    summary: Optional[Dict] = None
    snapshots: List[Dict] = []
    with emits_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            tag = rec.get("tag")
            payload = rec.get("payload") or {}
            if tag == "scenario" and scenario is None:
                scenario = payload
            elif tag == "md_snapshot":
                snapshots.append(payload)
            elif tag == "bulk_summary":
                summary = payload
    if scenario is None or not snapshots:
        raise SystemExit(
            "error: no scenario/md_snapshot emits found — the scenario must be "
            "re-run with the snapshot-emitting h2o_bulk_water.js")
    snapshots.sort(key=lambda p: p.get("tick", 0))
    return scenario, snapshots, summary


def normalize_gr(hist: List[float], frames: int, n_o: int, box_a: float,
                 rmax_a: float) -> np.ndarray:
    """Same normalisation as analyzeRdf() in the scenario JS."""
    bins = len(hist)
    g = np.zeros(bins)
    if frames <= 0:
        return g
    dr = rmax_a / bins
    rho = n_o / box_a ** 3
    for b in range(bins):
        rlo, rhi = b * dr, (b + 1) * dr
        shell = (4.0 / 3.0) * math.pi * (rhi ** 3 - rlo ** 3)
        ideal = frames * n_o * shell * rho
        g[b] = hist[b] / ideal if ideal > 0 else 0.0
    return g


def first_peak(g: np.ndarray, rmax_a: float) -> tuple:
    """First-peak (r, g) in the 2.4–3.2 Å window, like the scenario."""
    bins = len(g)
    dr = rmax_a / bins
    peak_r, peak_g = 0.0, 0.0
    for b in range(bins):
        r = (b + 0.5) * dr
        if 2.4 <= r <= 3.2 and g[b] > peak_g:
            peak_r, peak_g = r, g[b]
    return peak_r, peak_g


# ----------------------------------------------------------------- 3D panel


class BoxRenderer:
    """Off-screen PyVista view of the periodic cell, updated per snapshot."""

    def __init__(self, box_a: float, n_mol: int, size_px: int = 760):
        self.box_a = box_a
        self.n_mol = n_mol
        self.plotter = pv.Plotter(off_screen=True,
                                  window_size=(size_px, size_px))
        self.plotter.set_background(BG_COLOR)

        n_atoms = 3 * n_mol
        pts = np.zeros((n_atoms, 3))
        o_idx = np.arange(0, n_atoms, 3)
        h_idx = np.setdiff1d(np.arange(n_atoms), o_idx)
        self._o_idx, self._h_idx = o_idx, h_idx

        self.o_cloud = pv.PolyData(pts[o_idx].copy())
        self.h_cloud = pv.PolyData(pts[h_idx].copy())

        # O-H bonds: 2 per molecule, indices into the full [O,H,H] layout.
        lines = []
        for m in range(n_mol):
            o, h1, h2 = 3 * m, 3 * m + 1, 3 * m + 2
            lines.extend([2, o, h1, 2, o, h2])
        self.bond_poly = pv.PolyData(pts.copy(), lines=np.asarray(lines))

        self.plotter.add_mesh(self.bond_poly, color=BOND_COLOR,
                              line_width=2, opacity=0.85)
        self.plotter.add_mesh(self.o_cloud, color=O_COLOR,
                              point_size=17, render_points_as_spheres=True)
        self.plotter.add_mesh(self.h_cloud, color=H_COLOR,
                              point_size=9, render_points_as_spheres=True)

        cube = pv.Cube(center=(box_a / 2,) * 3,
                       x_length=box_a, y_length=box_a, z_length=box_a)
        self.plotter.add_mesh(cube.extract_all_edges(), color="#5c6470",
                              line_width=1.5, opacity=0.9)

        self.plotter.camera_position = "iso"
        self.plotter.camera.zoom(1.25)

    def frame(self, xyz: List[List[float]], azimuth_deg: float) -> np.ndarray:
        pts = np.asarray(xyz, dtype=float)
        self.o_cloud.points = pts[self._o_idx]
        self.h_cloud.points = pts[self._h_idx]
        self.bond_poly.points = pts
        if azimuth_deg:
            self.plotter.camera.Azimuth(azimuth_deg)  # incremental slow orbit
        # An explicit render is required: with a reused off-screen Plotter,
        # screenshot() alone returns the cached first frame (points/camera
        # updates never appear).
        self.plotter.render()
        return self.plotter.screenshot(return_img=True)

    def close(self):
        self.plotter.close()


# ----------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN_DIR,
                    help="run output dir containing trech_hook_emits.jsonl")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--frames-dir", type=Path, default=None)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--hold-seconds", type=float, default=3.0,
                    help="end-card hold on the final comparison")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--keep-frames", action="store_true")
    args = ap.parse_args()

    scenario, snapshots, summary = load_emits(args.run)
    box_a = float(scenario["box_A"])
    n_mol = int(scenario["molecules"])
    rmax_a = float(scenario.get("rdf_rmax_A") or box_a / 2)
    dt_fs = float(scenario.get("dt_fs") or 0.2)
    total_ticks = int(scenario.get("ticks") or snapshots[-1]["tick"])
    equil_frac = float(scenario.get("equil_fraction") or 0.4)
    print(f"loaded {len(snapshots)} md_snapshot emits from {args.run}")
    print(f"  N={n_mol} molecules, box={box_a:.2f} A, dt={dt_fs} fs, "
          f"ticks={total_ticks}")

    frames_dir = args.frames_dir or args.out.parent / (args.out.stem + "_frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    box3d = BoxRenderer(box_a, n_mol)
    bins = len(snapshots[-1]["rdf"]["hist"])
    r_axis = (np.arange(bins) + 0.5) * (rmax_a / bins)

    g_final = normalize_gr(snapshots[-1]["rdf"]["hist"],
                           int(snapshots[-1]["rdf"]["frames"]), n_mol,
                           box_a, rmax_a)
    ymax = max(3.5, float(g_final.max()) + 0.6)

    dpi = 100
    figsize = (args.width / dpi, args.height / dpi)

    n_anim = len(snapshots)
    n_hold = int(round(args.hold_seconds * args.fps))
    n_frames = n_anim + n_hold
    print(f"rendering {n_frames} frames @ {args.fps} fps "
          f"({n_frames / args.fps:.1f}s)")

    for i in range(n_frames):
        snap = snapshots[min(i, n_anim - 1)]
        end_card = i >= n_anim
        tick = int(snap["tick"])
        frames = int(snap["rdf"]["frames"])
        g = normalize_gr(snap["rdf"]["hist"], frames, n_mol, box_a, rmax_a)
        # slow orbit during the animation; freeze on the end card
        azim = 0.25 if not end_card else 0.0
        img = box3d.frame(snap["xyz"], azim)

        fig = plt.figure(figsize=figsize, dpi=dpi, facecolor=BG_COLOR)
        gs = GridSpec(1, 2, width_ratios=[1.05, 1.0], figure=fig,
                      left=0.015, right=0.97, top=0.86, bottom=0.10,
                      wspace=0.14)

        ax_img = fig.add_subplot(gs[0, 0])
        ax_img.imshow(img)
        ax_img.set_axis_off()

        ax_gr = fig.add_subplot(gs[0, 1], facecolor=BG_COLOR)
        for spine in ax_gr.spines.values():
            spine.set_color("#555c66")
        ax_gr.tick_params(colors=FG_COLOR, labelsize=9)
        ax_gr.set_xlim(0.0, rmax_a)
        ax_gr.set_ylim(0.0, ymax)
        ax_gr.set_xlabel("r  [Å]", color=FG_COLOR, fontsize=10)
        ax_gr.set_ylabel("g(r)  O–O", color=FG_COLOR, fontsize=10)
        ax_gr.axhline(1.0, color="#555c66", lw=0.8, ls=":")
        ax_gr.axvline(EXP_FIRST_PEAK_A, color=EXP_COLOR, lw=1.6, ls="--")
        ax_gr.text(EXP_FIRST_PEAK_A + 0.08, ymax - 0.25,
                   f"experiment: first peak {EXP_FIRST_PEAK_A:.2f} Å\n"
                   "(hydrogen-bond distance)",
                   color=EXP_COLOR, fontsize=9, va="top")
        if rmax_a > EXP_SECOND_PEAK_A + 0.5:
            ax_gr.axvline(EXP_SECOND_PEAK_A, color=EXP_COLOR, lw=1.1,
                          ls="--", alpha=0.6)
            ax_gr.text(EXP_SECOND_PEAK_A + 0.08, ymax - 0.95,
                       f"2nd shell {EXP_SECOND_PEAK_A:.1f} Å\n(tetrahedral)",
                       color=EXP_COLOR, fontsize=8, va="top", alpha=0.8)

        if frames > 0:
            ax_gr.plot(r_axis, g, color=TRECH_COLOR, lw=2.0,
                       label="TRECH MD (engine g(r))")
            pk_r, pk_g = first_peak(g, rmax_a)
            if pk_g > 0:
                ax_gr.plot([pk_r], [pk_g], "o", color=TRECH_COLOR, ms=6)
                ax_gr.annotate(f"{pk_r:.2f} Å", (pk_r, pk_g),
                               textcoords="offset points", xytext=(8, 6),
                               color=TRECH_COLOR, fontsize=10)
            leg = ax_gr.legend(loc="upper right", fontsize=9,
                               facecolor=BG_COLOR, edgecolor="#555c66")
            for t in leg.get_texts():
                t.set_color(FG_COLOR)
        else:
            ax_gr.text(0.5, 0.5,
                       "equilibrating…\n(g(r) accumulation starts at "
                       f"{int(equil_frac * 100)}% of the run)",
                       transform=ax_gr.transAxes, ha="center", va="center",
                       color="#9aa3ad", fontsize=11)

        fig.suptitle(
            "TRECH bulk H$_2$O — periodic-box classical MD (hook layer, "
            "Geant4 ticks) vs measured liquid structure",
            color=FG_COLOR, fontsize=12, y=0.965)
        hud = (f"t = {tick * dt_fs:7.1f} fs    tick {tick}/{total_ticks}    "
               f"T = {snap['temperature_K']:5.1f} K    "
               f"N = {n_mol} molecules    box = {box_a:.1f} Å")
        fig.text(0.02, 0.025, hud, color="#9aa3ad", fontsize=9,
                 family="monospace")

        if end_card and summary:
            val = summary.get("validation") or {}
            ok = bool(val.get("bulk_water_stable"))
            lines = [
                f"first peak: TRECH {summary['gr_first_peak_A']:.3f} Å  vs  "
                f"experiment {EXP_FIRST_PEAK_A:.2f} Å",
            ]
            if summary.get("gr_second_peak_A"):
                lines.append(
                    f"2nd shell:  TRECH {summary['gr_second_peak_A']:.2f} Å   vs  "
                    f"experiment ≈{EXP_SECOND_PEAK_A:.1f} Å")
            coord34 = summary.get("coordination_number_to_3p4A")
            min_h = summary.get("gr_first_min_height")
            if coord34:
                lines.append(
                    f"coordination: {summary['coordination_number']:.1f} "
                    f"(to {summary.get('gr_first_min_A', 0):.1f} Å min) / "
                    f"{coord34:.1f} (to 3.4 Å)  vs  ≈{EXP_COORDINATION} measured")
                if min_h:
                    lines.append(
                        f"inter-shell min g(r) {min_h:.2f}  (exp ≈0.75; SPC/E "
                        "charges deepen it — reported, not tuned)")
            else:
                lines.append(
                    f"coordination: TRECH {summary['coordination_number']:.1f}  "
                    f"vs  ≈{EXP_COORDINATION} measured")
            lines.append(
                f"mean T = {summary['mean_temperature_K']:.0f} K    "
                f"bulk_water_stable = {ok}")
            fig.text(0.27, 0.115, "\n".join(lines), ha="center", va="bottom",
                     color=FG_COLOR, fontsize=9.5, family="monospace",
                     bbox=dict(facecolor="#23272e", edgecolor=EXP_COLOR,
                               boxstyle="round,pad=0.6", alpha=0.92))

        fig.savefig(frames_dir / f"frame_{i:04d}.png", facecolor=BG_COLOR)
        plt.close(fig)
        if (i + 1) % 50 == 0 or i + 1 == n_frames:
            print(f"  frame {i + 1}/{n_frames}")

    box3d.close()

    print(f"encoding {args.out}")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(args.fps),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(args.out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        return res.returncode
    if not args.keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
