"""Render the shaken glass of water as a 5 mm metaball isosurface.

Story (same honesty contract as ``render_bulk_water.py``):

* **the multi-scale claim** — ``glass_of_water_shaken.js`` never types a single
  macroscopic water property. A short rigid-SPC/E MD measures the nanoscale
  number density and hydrogen-bond coordination; ``ctx.cascade`` lifts those
  facts nano -> micro -> macro into the fluid parameters (rest density, surface
  tension, viscosity); a Position-Based-Fluid solver then sloshes the glass. The
  recovered macro rest density (~999 kg/m^3) lands on measured water (998) as a
  *check*, not an input -- shown on the cascade card.

* **the merging drops** — the water is drawn as a single **isosurface of a 5 mm
  density grid** splatted from the particle positions (the requested 5 mm
  representation precision). Neighbouring particles fuse into one cohesive
  surface; a splash that breaks off shows as its own blob and MERGES back into
  the body when it rejoins -- the requested "drops of water merge into cohesive,
  united water" effect, driven by the cascade-inferred cohesion.

Run::

    cd tools/viz && source ../../build/render-venv/bin/activate   # pyvista + ffmpeg
    python demos/render_glass_of_water_shaken.py                  # default run dir + output

Inputs:  ``build/dev/out_glass_shaken/trech_hook_emits.jsonl`` (scenario,
cascade, fluid_frame, glass_summary emits).
Output:  ``tools/viz/demos/glass_of_water_shaken.mp4`` (override with ``--out``).
"""

from __future__ import annotations

import argparse
import json
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
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_glass_shaken"
DEFAULT_OUT = Path(__file__).resolve().parent / "glass_of_water_shaken.mp4"

# Palette (consistent with the other comparison demos):
# amber = "what measured physics says", the water is a cohesive blue body.
BG_COLOR = "#0e1014"
FG_COLOR = "#e8e8e8"
EXP_COLOR = "#ffb347"
GLASS_COLOR = "#9fb9cc"
WATER_LO = "#1c5fb0"   # deep water
WATER_HI = "#8fd6ff"   # crest / splash
REF_WATER_DENSITY = 998.2   # kg/m^3, measured liquid water ~20 C (comparison only)


# ----------------------------------------------------------------- emit input


def load_emits(run_dir: Path):
    """Return (scenario, cascade, frames, summary) from trech_hook_emits.jsonl."""
    emits_path = run_dir / "trech_hook_emits.jsonl"
    if not emits_path.exists():
        raise SystemExit(
            f"error: {emits_path} not found; run glass_of_water_shaken.js first")
    scenario: Optional[Dict] = None
    cascade: Optional[Dict] = None
    summary: Optional[Dict] = None
    frames: List[Dict] = []
    with emits_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            tag, payload = rec.get("tag"), rec.get("payload") or {}
            if tag == "scenario" and scenario is None:
                scenario = payload
            elif tag == "cascade" and cascade is None:
                cascade = payload
            elif tag == "fluid_frame":
                frames.append(payload)
            elif tag == "glass_summary":
                summary = payload
    if scenario is None or not frames:
        raise SystemExit(
            "error: no scenario/fluid_frame emits found -- re-run "
            "glass_of_water_shaken.js")
    frames.sort(key=lambda p: p.get("tick", 0))
    return scenario, cascade, frames, summary


# ----------------------------------------------------------------- metaballs


def make_stencil(spacing: float, sigma: float):
    """Gaussian splat stencil normalised so a lone particle peaks at 1.0
    (truncated at 2 sigma to keep the per-particle splat cheap on the fine grid)."""
    rad = max(1, int(np.ceil(2.0 * sigma / spacing)))
    ax = np.arange(-rad, rad + 1)
    gx, gy, gz = np.meshgrid(ax, ax, ax, indexing="ij")
    r2 = (gx * gx + gy * gy + gz * gz) * spacing * spacing
    return rad, np.exp(-r2 / (2.0 * sigma * sigma)).astype(np.float32)


def density_grid(points: np.ndarray, origin: np.ndarray, spacing: float,
                 dims, rad: int, stencil: np.ndarray) -> np.ndarray:
    """Splat particle points onto a 5 mm point grid (order-F flattenable)."""
    nx, ny, nz = dims
    field = np.zeros((nx, ny, nz), dtype=np.float32)
    idx = np.round((points - origin) / spacing).astype(int)
    for p in idx:
        x, y, z = int(p[0]), int(p[1]), int(p[2])
        xa, xb = max(0, x - rad), min(nx, x + rad + 1)
        ya, yb = max(0, y - rad), min(ny, y + rad + 1)
        za, zb = max(0, z - rad), min(nz, z + rad + 1)
        if xa >= xb or ya >= yb or za >= zb:
            continue
        sxa, sya, sza = xa - (x - rad), ya - (y - rad), za - (z - rad)
        field[xa:xb, ya:yb, za:zb] += stencil[
            sxa:sxa + (xb - xa), sya:sya + (yb - ya), sza:sza + (zb - za)]
    return field


class GlassScene:
    """Off-screen PyVista view: shaking glass + merged water isosurface."""

    def __init__(self, scenario: Dict, size_px: int = 900):
        g = scenario["glass"]
        self.R = float(g["inner_radius_m"])
        self.H_wall = float(g["wall_height_m"])
        self.spacing = float(scenario.get("particle_spacing_m") or 0.006)
        # The metaball isosurface is sampled on a FINE grid (2 mm by default) for
        # higher visual precision than the ~6 mm simulation particles; the splat
        # width is tied to the sim spacing so neighbours still fuse into one body.
        self.dx = float(scenario.get("render_grid_mm") or 2.0) / 1000.0
        self.sigma = 0.85 * self.spacing
        self.iso = 0.42
        self.rad, self.stencil = make_stencil(self.dx, self.sigma)

        self.plotter = pv.Plotter(off_screen=True, window_size=(size_px, size_px))
        self.plotter.set_background(BG_COLOR)

        # a dim table plane for grounding
        table = pv.Plane(center=(0, 0, 0.0), direction=(0, 0, 1),
                         i_size=0.34, j_size=0.34)
        self.plotter.add_mesh(table, color="#1a1e26", ambient=0.4)

        # the glass: a translucent open cylinder shell + a base disk. Kept as
        # actors so they can be translated with the shake each frame.
        shell = pv.Cylinder(center=(0, 0, self.H_wall / 2), direction=(0, 0, 1),
                            radius=self.R, height=self.H_wall,
                            capping=False, resolution=48)
        base = pv.Disc(center=(0, 0, 0.001), inner=0.0, outer=self.R,
                       normal=(0, 0, 1), r_res=1, c_res=48)
        self.glass_actor = self.plotter.add_mesh(
            shell, color=GLASS_COLOR, opacity=0.16, specular=0.6,
            specular_power=30, smooth_shading=True)
        self.base_actor = self.plotter.add_mesh(base, color=GLASS_COLOR,
                                                opacity=0.28)

        # fixed 3/4 camera in the lab frame, so the glass visibly slides when
        # shaken (both glass and water translate together). Framed for the wide
        # (11 cm across, 13 cm tall) tumbler with headroom above the water.
        self.plotter.camera_position = [
            (0.30, -0.44, 0.20), (0.0, 0.0, 0.055), (0, 0, 1)]
        self.plotter.camera.zoom(1.25)

    def frame(self, xyz: np.ndarray, glass_xy) -> np.ndarray:
        # translate the glass with the shake
        for a in (self.glass_actor, self.base_actor):
            a.SetPosition(float(glass_xy[0]), float(glass_xy[1]), 0.0)

        # fine (2 mm) density grid over the current water bounding box (+ padding)
        pad = 0.012
        lo = xyz.min(axis=0) - pad
        hi = xyz.max(axis=0) + pad
        lo[2] = -0.002
        dims = np.maximum(4, np.ceil((hi - lo) / self.dx).astype(int) + 1)
        field = density_grid(xyz, lo, self.dx, tuple(dims),
                             self.rad, self.stencil)
        # clip the density field to the glass radius (about its shaken centre) so
        # the metaball surface never bulges through the wall.
        nx, ny, nz = (int(d) for d in dims)
        gx = lo[0] + np.arange(nx) * self.dx - float(glass_xy[0])
        gy = lo[1] + np.arange(ny) * self.dx - float(glass_xy[1])
        rr = (gx[:, None] ** 2 + gy[None, :] ** 2) > (self.R * 0.995) ** 2
        field[rr] = 0.0
        grid = pv.ImageData(dimensions=tuple(int(d) for d in dims),
                            spacing=(self.dx,) * 3, origin=tuple(lo))
        grid.point_data["d"] = field.flatten(order="F")
        water = grid.contour([self.iso], scalars="d")

        if water.n_points > 0:
            # colour the surface by height (deep -> crest/splash)
            z = water.points[:, 2]
            water["height"] = z
            self.plotter.add_mesh(
                water, name="water", scalars="height", cmap=WATER_CMAP,
                clim=[0.0, max(0.06, float(z.max()))], show_scalar_bar=False,
                smooth_shading=True, specular=0.5, specular_power=25,
                opacity=0.97)
        else:
            self.plotter.add_mesh(pv.PolyData(np.zeros((1, 3))), name="water",
                                  opacity=0.0)

        self.plotter.render()
        return self.plotter.screenshot(return_img=True)

    def close(self):
        self.plotter.close()


from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

WATER_CMAP = LinearSegmentedColormap.from_list("water", [WATER_LO, WATER_HI])


# ----------------------------------------------------------------- panels


def cascade_lines(cascade: Optional[Dict]) -> List[str]:
    if not cascade:
        return ["(no cascade emit)"]
    n = cascade.get("nano_measured", {})
    m = cascade.get("macro_inferred", {})
    c = cascade.get("cascade", {})
    scales = " -> ".join(c.get("scales_bridged", []))
    return [
        "MULTI-SCALE CASCADE  (no macro water property is typed)",
        "",
        f"  nano MD measured:  n = {n.get('number_density_per_A3', 0):.4f} /A^3",
        f"                     H-bond coordination = {n.get('coordination', 0):.2f}",
        f"                     g(r) 1st peak = {n.get('hbond_peak_A', 0):.2f} A"
        f"  (T {n.get('mean_temperature_K', 0):.0f} K)",
        "",
        f"  cascade bridged:   {scales}   ({c.get('stages_run', 0)} stages)",
        "",
        f"  macro inferred:    rest density = {m.get('rest_density_kg_per_m3', 0):.1f}"
        f" kg/m^3",
        f"                     surface tension = "
        f"{m.get('surface_tension_coeff', 0):.3f}  (drops merge)",
        f"                     viscosity coeff = {m.get('viscosity_coeff', 0):.3f}",
        "",
        f"  check vs measured water {REF_WATER_DENSITY:.0f} kg/m^3:  "
        f"{cascade.get('density_recovery_error_pct', 0):.2f}% error",
        f"  poured: {m.get('water_mass_g', 0):.0f} g  (~{m.get('water_mass_g', 0) / 1000:.2f} L),"
        f" {m.get('target_particles', 0)} particles @ 6 mm",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--stride", type=int, default=1,
                    help="use every Nth emitted frame")
    ap.add_argument("--hold-seconds", type=float, default=3.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--keep-frames", action="store_true")
    ap.add_argument("--gif", action="store_true", help="also write a .gif")
    ap.add_argument("--gif-width", type=int, default=840,
                    help="width (px) of the .gif (height keeps the aspect ratio)")
    args = ap.parse_args()

    scenario, cascade, frames, summary = load_emits(args.run)
    frames = frames[:: max(1, args.stride)]
    print(f"loaded {len(frames)} fluid_frame emits from {args.run}")

    frames_dir = args.out.parent / (args.out.stem + "_frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    scene = GlassScene(scenario)
    still_level = None
    if summary:
        still_level = float(summary.get("glass", {}).get("still_water_level_m") or 0)

    n_hold = int(round(args.hold_seconds * args.fps))
    n_frames = len(frames) + n_hold
    dpi = 100
    figsize = (args.width / dpi, args.height / dpi)
    casc_txt = cascade_lines(cascade)
    print(f"rendering {n_frames} frames @ {args.fps} fps")

    for i in range(n_frames):
        fr = frames[min(i, len(frames) - 1)]
        end_card = i >= len(frames)
        xyz = np.asarray(fr["xyz"], dtype=float)
        img = scene.frame(xyz, fr.get("glass_xy_m", [0, 0]))

        fig = plt.figure(figsize=figsize, dpi=dpi, facecolor=BG_COLOR)
        gs = GridSpec(1, 2, width_ratios=[1.32, 1.0], figure=fig,
                      left=0.01, right=0.985, top=0.9, bottom=0.06, wspace=0.03)

        ax_img = fig.add_subplot(gs[0, 0])
        ax_img.imshow(img)
        ax_img.set_axis_off()

        ax_txt = fig.add_subplot(gs[0, 1])
        ax_txt.set_axis_off()
        ax_txt.text(0.0, 0.98, "\n".join(casc_txt), va="top", ha="left",
                    color=FG_COLOR, fontsize=9.5, family="monospace",
                    transform=ax_txt.transAxes)

        phase_map = {"pour": "POURING", "settle": "settling", "shake": "SHAKING"}
        phase = phase_map.get(fr.get("phase", ""), fr.get("phase", ""))
        live = [
            "",
            "", "", "", "", "", "", "", "", "", "", "", "", "", "",
            f"  phase: {phase}   t = {fr.get('time_s', 0):.2f} s",
            f"  water in glass = {fr.get('active', 0)} particles",
            f"  glass offset = ({fr.get('glass_xy_m', [0, 0])[0] * 100:+.2f}, "
            f"{fr.get('glass_xy_m', [0, 0])[1] * 100:+.2f}) cm",
            f"  wave roughness = {fr.get('surf_roughness_m', 0) * 1000:.1f} mm",
            f"  crest above still = {fr.get('splash_height_m', 0) * 1000:+.1f} mm",
            f"  max speed = {fr.get('max_speed', 0):.2f} m/s",
        ]
        ax_txt.text(0.0, 0.98, "\n".join(live), va="top", ha="left",
                    color="#9fdcff", fontsize=9.5, family="monospace",
                    transform=ax_txt.transAxes)

        fig.suptitle(
            "TRECH glass of water, SHAKEN -- macro sloshing inferred from the "
            "nanoscale H$_2$O base (multi-scale cascade)",
            color=FG_COLOR, fontsize=13, y=0.965)

        if end_card and summary:
            val = summary.get("validation", {})
            ok = bool(val.get("glass_of_water_from_nano"))
            dyn = summary.get("dynamics", {})
            lines = [
                f"peak wave roughness {dyn.get('peak_wave_roughness_m', 0) * 1000:.1f} mm"
                f"   peak splash {dyn.get('peak_splash_height_m', 0) * 1000:.1f} mm"
                f" above still level",
                f"poured={val.get('water_poured_in')}  waves={val.get('waves_present')}"
                f"  splash={val.get('splash_present')}"
                f"  contained={val.get('water_contained')}  stable="
                f"{val.get('stable_no_explosion')}",
                f"every macro parameter inferred from the nano base   "
                f"glass_of_water_from_nano = {ok}",
            ]
            fig.text(0.5, 0.02, "\n".join(lines), ha="center", va="bottom",
                     color=FG_COLOR, fontsize=10, family="monospace",
                     bbox=dict(facecolor="#1b1f27", edgecolor=EXP_COLOR,
                               boxstyle="round,pad=0.5", alpha=0.95))

        fig.savefig(frames_dir / f"frame_{i:04d}.png", facecolor=BG_COLOR)
        plt.close(fig)
        if (i + 1) % 40 == 0 or i + 1 == n_frames:
            print(f"  frame {i + 1}/{n_frames}")

    scene.close()

    print(f"encoding {args.out}")
    cmd = ["ffmpeg", "-y", "-framerate", str(args.fps),
           "-i", str(frames_dir / "frame_%04d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
           str(args.out)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        return res.returncode
    print(f"wrote {args.out}")

    if args.gif:
        gif = args.out.with_suffix(".gif")
        palette = frames_dir / "palette.png"
        gw = f"scale={args.gif_width}:-1:flags=lanczos"
        subprocess.run(["ffmpeg", "-y", "-i", str(frames_dir / "frame_%04d.png"),
                        "-vf", f"fps=12,{gw},palettegen",
                        str(palette)], capture_output=True, text=True)
        subprocess.run(["ffmpeg", "-y", "-framerate", str(args.fps),
                        "-i", str(frames_dir / "frame_%04d.png"), "-i", str(palette),
                        "-lavfi", f"fps=12,{gw}[x];[x][1:v]paletteuse",
                        str(gif)], capture_output=True, text=True)
        print(f"wrote {gif}")

    if not args.keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
