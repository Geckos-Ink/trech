"""Render the osmotic-dehydration hook scenario as a biological-cell animation.

The video is a replay of TRECH output, not a closed-form osmosis illustration:

* ``testscenario_osmotic.js`` advances a deterministic coarse-grained bath of
  H2O / glucose / wrong-polarized ions from Geant4 event callbacks. One event
  is one MD tick. A turgor-driven spring membrane (emitted as ``membrane`` node
  radii) crenates as the cell loses water.
* The script consumes only ``trech_hook_emits.jsonl`` sidebands
  (``osmotic_particles``, ``scenario`` and ``final_summary``). It does not use a
  fixed osmotic law to move particles or draw an expected curve.
* The count / radius plots are the emitted simulation history -- suitable as
  training / validation signal for larger-scale surrogate work, while any
  learned inference path must still be gated against high-fidelity TRECH runs.

What the cell shows (all emitted by the scenario):

* H2O is the *solvent*, drawn as a blue field rather than ~100 jittering dots:
  the intracellular wash fades as water is expelled and the extracellular wash
  brightens, so the osmotic shift reads as a coherent transfer of water out of
  the cell (pore arrows mark the efflux direction);
* glucose (amber) is size-excluded and bounces off the wall;
* ions (magenta) are small enough to fit the pore but the channel rejects them
  by polarity -- the membrane *expels these "wrong polarized" molecules*;
* the lipid membrane contracts and buckles into lobes (crenation) as turgor
  falls.

Rendering notes: (1) the scenario resolves particle exclusion on the nominal
pore ring, while the emitted turgor membrane gives the crenated outline -- for
visual coherence the renderer maps the emitted bath radially onto the current
membrane outline (angles/identities are raw emitted state; only the radial
coordinate is conformed). (2) Snapshots are tens of ticks apart, so the
glucose/ion molecules are *interpolated* between snapshots (``--tween``) to
glide smoothly instead of teleporting; water is a field, not tracked dots.

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
from typing import Dict, List, Optional, Tuple

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402
from matplotlib.patches import Ellipse, Polygon  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_osmotic"
DEFAULT_OUT = Path(__file__).resolve().parent / "osmotic_dehydration.mp4"

BG_COLOR = "#080b11"
EXTRA_COLOR = "#0c1420"          # extracellular fluid wash
FG_COLOR = "#e8edf2"
GRID_COLOR = "#3a414c"
WATER_COLOR = "#5cc8ff"
GLUCOSE_COLOR = "#f2a65a"
ION_COLOR = "#ff5d8f"            # wrong-polarized
MEMBRANE_HEAD = "#ffd27f"        # phospholipid heads
MEMBRANE_TAIL = "#caa24e"
CYTOPLASM = "#16b39a"
NUCLEUS = "#7c5cc0"
ORGANELLE = "#3fae9a"
PORE_COLOR = "#bdecff"
EXPEL_COLOR = "#fff3b0"
TRECH_GREEN = "#7fdc7f"

TWO_PI = 2.0 * math.pi


def load_emits(run_dir: Path) -> Tuple[Dict, List[Dict], Optional[Dict]]:
    emits = run_dir / "trech_hook_emits.jsonl"
    if not emits.exists():
        raise SystemExit(f"error: {emits} not found; run testscenario_osmotic.js first")
    scenario: Optional[Dict] = None
    summary: Optional[Dict] = None
    snapshots: Dict[int, Dict] = {}
    with emits.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            payload = rec.get("payload") or {}
            tag = rec.get("tag")
            if tag == "scenario":
                scenario = payload          # keep the latest (the active run)
            elif tag == "osmotic_particles":
                if "membrane" in payload:    # ignore any legacy schema lines
                    snapshots[int(payload.get("tick", 0))] = payload
            elif tag == "final_summary":
                summary = payload
    if scenario is None:
        raise SystemExit("error: no scenario emit found")
    if not snapshots:
        raise SystemExit(
            "error: no osmotic_particles emits with a membrane found; re-run the "
            "current testscenario_osmotic.js (a clean --output dir; emits append)")
    ordered = [snapshots[t] for t in sorted(snapshots)]
    return scenario, ordered, summary


def pore_angles(count: int) -> np.ndarray:
    return np.array([(TWO_PI * i) / count for i in range(count)])


def membrane_radius_at(membrane: np.ndarray, thetas: np.ndarray) -> np.ndarray:
    """Periodic-linear interpolation of node radii at arbitrary angles."""
    n = len(membrane)
    node_ang = TWO_PI * np.arange(n) / n
    ext_ang = np.append(node_ang, TWO_PI)
    ext_r = np.append(membrane, membrane[0])
    return np.interp(np.mod(thetas, TWO_PI), ext_ang, ext_r)


def membrane_outline(membrane: np.ndarray, samples: int = 400
                     ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    th = np.linspace(0.0, TWO_PI, samples)
    r = membrane_radius_at(membrane, th)
    return r * np.cos(th), r * np.sin(th), th


def remap_radial(x: np.ndarray, y: np.ndarray, inside: np.ndarray,
                 membrane: np.ndarray, r0: float, half: float
                 ) -> Tuple[np.ndarray, np.ndarray]:
    """Conform emitted (x, y) onto the current membrane outline.

    Inside particles compress with the cytoplasm; outside particles hug the
    receding wall. Angle is preserved; only the radius is remapped.
    """
    if len(x) == 0:
        return x, y
    r = np.hypot(x, y)
    theta = np.arctan2(y, x)
    rm = membrane_radius_at(membrane, theta)
    out = np.empty_like(r)
    inside = inside.astype(bool)
    # inside: [0, r0] -> [0, rm]
    out[inside] = r[inside] * rm[inside] / r0
    # outside: [r0, half] -> [rm, half]
    ro = np.clip(r[~inside], r0, half)
    out[~inside] = rm[~inside] + (ro - r0) * (half - rm[~inside]) / (half - r0)
    safe = np.maximum(r, 1e-9)
    return out * x / safe, out * y / safe


def _index_by_id(snapshot: Dict) -> Dict[int, Dict]:
    return {int(p.get("id", i)): p for i, p in enumerate(snapshot.get("particles") or [])}


# Particles whose id-tracked step exceeds this (units) between two snapshots are
# treated as teleports (domain wrap / rare large diffusive jump) and snapped to
# the nearest keyframe rather than streaked across the cell.
TELEPORT_STEP = 34.0


def interp_frame(snap_a: Dict, snap_b: Dict, u: float) -> Dict:
    """Linearly interpolate two snapshots so non-water molecules glide.

    Particle ids are stable (the array index never changes), so each id is the
    same molecule across snapshots. Water is *not* tracked as dots -- it is
    rendered as a solvent field from the in/out counts -- so only glucose / ion
    positions are tweened.
    """
    mem_a = np.array(snap_a["membrane"], dtype=float)
    mem_b = np.array(snap_b["membrane"], dtype=float)
    membrane = (1.0 - u) * mem_a + u * mem_b

    idx_a = _index_by_id(snap_a)
    idx_b = _index_by_id(snap_b)
    species: Dict[str, List[List[float]]] = {"glucose": [], "ion": []}
    for pid, pa in idx_a.items():
        kind = pa.get("k")
        if kind not in species:
            continue
        pb = idx_b.get(pid, pa)
        ax_, ay_ = float(pa["x"]), float(pa["y"])
        bx_, by_ = float(pb["x"]), float(pb["y"])
        if math.hypot(bx_ - ax_, by_ - ay_) > TELEPORT_STEP:
            # snap (no streak) to whichever keyframe we are nearer
            x, y, ins = (ax_, ay_, pa) if u < 0.5 else (bx_, by_, pb)
            inside = 1.0 if ins.get("i") else 0.0
        else:
            x = (1.0 - u) * ax_ + u * bx_
            y = (1.0 - u) * ay_ + u * by_
            inside = 1.0 if (pa if u < 0.5 else pb).get("i") else 0.0
        species[kind].append([x, y, inside])

    out_species: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for k, rows in species.items():
        if rows:
            a = np.array(rows)
            out_species[k] = (a[:, 0], a[:, 1], a[:, 2])
        else:
            z = np.zeros(0)
            out_species[k] = (z, z, z)

    def lerp(key: str) -> float:
        return (1.0 - u) * float(snap_a.get(key) or 0.0) + u * float(snap_b.get(key) or 0.0)

    return {
        "membrane": membrane,
        "species": out_species,
        "inside_h2o": lerp("inside_h2o"),
        "outside_h2o": lerp("outside_h2o"),
        "flux": lerp("net_water_flux_out"),
        # discrete fields come from the leading keyframe
        "tick": int(snap_a["tick"]),
        "phase": str(snap_a.get("phase") or ""),
        "rejections": int(snap_a.get("wrong_polarized_rejections") or 0),
        "inside_h2o_i": int(snap_a["inside_h2o"]),
        "outside_h2o_i": int(snap_a["outside_h2o"]),
        "expelled": snap_a.get("expelled") or [],
        "expel_alpha": max(0.0, 1.0 - u),
    }


def phase_color(phase: str) -> str:
    return {
        "thermalization": "#90caf9",
        "local_diffusion": "#b39ddb",
        "macroscopic_flux": TRECH_GREEN,
    }.get(phase, "#ffd166")


def draw_cell(ax, frame: Dict, scenario: Dict, pores: np.ndarray,
              init_water: float) -> None:
    r0 = float(scenario["cellRadius"])
    half = float(scenario["domainHalfSize"])
    membrane = frame["membrane"]
    mean_r = float(membrane.mean())
    frac_in = max(0.0, min(1.0, frame["inside_h2o"] / max(init_water, 1.0)))
    frac_out = max(0.0, min(1.0, frame["outside_h2o"] / max(init_water, 1.0)))

    ax.set_facecolor(BG_COLOR)
    ax.set_xlim(-half * 0.86, half * 0.86)
    ax.set_ylim(-half * 0.86, half * 0.86)
    ax.set_aspect("equal")
    ax.axis("off")

    ox, oy, oth = membrane_outline(membrane)
    bilayer = 1.4
    inner = membrane - bilayer
    ix, iy, _ = membrane_outline(inner)

    # --- Water as a solvent field (no per-molecule water dots) ---
    # Extracellular water wash: brightens as expelled water accumulates outside.
    ax.add_patch(plt.Rectangle((-half, -half), 2 * half, 2 * half,
                               facecolor=EXTRA_COLOR, edgecolor="none", zorder=0))
    ax.add_patch(plt.Rectangle((-half, -half), 2 * half, 2 * half,
                               facecolor=WATER_COLOR, alpha=0.04 + 0.20 * frac_out,
                               edgecolor="none", zorder=0))
    # Cytoplasm (teal) under the intracellular water.
    ax.add_patch(Polygon(np.column_stack([ix, iy]), closed=True,
                         facecolor=CYTOPLASM, alpha=0.16, edgecolor="none",
                         zorder=1))
    # Lipid bilayer band: cut a clean interior, then fill it.
    ax.add_patch(Polygon(np.column_stack([ox, oy]), closed=True,
                         facecolor=MEMBRANE_TAIL, alpha=0.22, edgecolor="none",
                         zorder=2))
    ax.add_patch(Polygon(np.column_stack([ix, iy]), closed=True,
                         facecolor=BG_COLOR, alpha=1.0, edgecolor="none",
                         zorder=2))
    ax.add_patch(Polygon(np.column_stack([ix, iy]), closed=True,
                         facecolor=CYTOPLASM, alpha=0.16, edgecolor="none",
                         zorder=3))
    # Intracellular water: bright when full, fades as the cell dehydrates.
    ax.add_patch(Polygon(np.column_stack([ix, iy]), closed=True,
                         facecolor=WATER_COLOR, alpha=0.07 + 0.34 * frac_in,
                         edgecolor="none", zorder=3))
    ax.plot(ox, oy, color=MEMBRANE_HEAD, lw=1.7, alpha=0.95, zorder=4)
    ax.plot(ix, iy, color=MEMBRANE_HEAD, lw=1.2, alpha=0.7, zorder=4)

    # Phospholipid head dots along the outer leaflet.
    head_th = np.linspace(0, TWO_PI, 120, endpoint=False)
    hr = membrane_radius_at(membrane, head_th)
    ax.scatter(hr * np.cos(head_th), hr * np.sin(head_th), s=10,
               c=MEMBRANE_HEAD, alpha=0.55, edgecolors="none", zorder=4)

    # Nucleus + nucleolus + a couple of organelles, scaled with the cell.
    ax.add_patch(Ellipse((0, 0), 2 * 0.34 * mean_r, 2 * 0.30 * mean_r,
                         facecolor=NUCLEUS, alpha=0.32, edgecolor=NUCLEUS,
                         lw=1.0, zorder=5))
    ax.add_patch(Ellipse((0.05 * mean_r, -0.02 * mean_r),
                         2 * 0.10 * mean_r, 2 * 0.09 * mean_r,
                         facecolor=NUCLEUS, alpha=0.55, edgecolor="none", zorder=6))
    for ang, rad, w, h in [(0.9, 0.62, 0.12, 0.06), (3.7, 0.58, 0.10, 0.05),
                           (5.3, 0.6, 0.11, 0.055)]:
        cx, cy = rad * mean_r * math.cos(ang), rad * mean_r * math.sin(ang)
        ax.add_patch(Ellipse((cx, cy), 2 * w * mean_r, 2 * h * mean_r,
                             angle=math.degrees(ang), facecolor=ORGANELLE,
                             alpha=0.45, edgecolor="none", zorder=5))

    # Channel pores on the membrane outline, with outward water-efflux arrows.
    pr = membrane_radius_at(membrane, pores)
    px, py = pr * np.cos(pores), pr * np.sin(pores)
    ax.scatter(px, py, s=70, c=PORE_COLOR, alpha=0.95,
               edgecolors="#06121a", linewidths=0.5, zorder=7)
    arrow_len = min(7.5, max(0.0, frame["flux"]) * 0.09)
    if arrow_len > 0.3:
        for a, x0, y0 in zip(pores, px, py):
            ca, sa = math.cos(a), math.sin(a)
            ax.annotate("", xy=(x0 + arrow_len * ca, y0 + arrow_len * sa),
                        xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="-|>", color=WATER_COLOR,
                                        alpha=0.75, lw=1.4), zorder=7)

    # Smoothly-glided solute molecules (water is the field above).
    spec = frame["species"]

    def draw(kind: str, color: str, size_in: float, size_out: float) -> None:
        x, y, ins = spec.get(kind, (np.zeros(0),) * 3)
        if len(x) == 0:
            return
        rx, ry = remap_radial(x, y, ins, membrane, r0, half)
        m_in = ins.astype(bool)
        if m_in.any():
            ax.scatter(rx[m_in], ry[m_in], s=size_in, c=color, alpha=0.96,
                       edgecolors="#06121a", linewidths=0.3, zorder=8)
        if (~m_in).any():
            ax.scatter(rx[~m_in], ry[~m_in], s=size_out, c=color, alpha=0.62,
                       edgecolors="none", zorder=6)

    draw("glucose", GLUCOSE_COLOR, 95, 80)
    draw("ion", ION_COLOR, 46, 40)

    # Expulsion flashes: membrane strikes by wrong-polarized / oversized
    # molecules, fading across the tween so each reads as a pulse.
    ea = frame.get("expel_alpha", 1.0)
    if ea > 0.05:
        for ev in frame.get("expelled") or []:
            ex = np.array([float(ev["x"])])
            ey = np.array([float(ev["y"])])
            ei = np.array([1.0 if ev.get("i") else 0.0])
            fx, fy = remap_radial(ex, ey, ei, membrane, r0, half)
            ax.scatter(fx, fy, s=170, marker="*", c=EXPEL_COLOR, alpha=0.9 * ea,
                       edgecolors="none", zorder=9)
            ax.scatter(fx, fy, s=300 + 500 * (1 - ea), marker="o",
                       facecolors="none", edgecolors=EXPEL_COLOR,
                       linewidths=1.0, alpha=0.5 * ea, zorder=9)


def encode_video(frames_dir: Path, out: Path, fps: int) -> int:
    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
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
    ap.add_argument("--tween", type=int, default=3,
                    help="interpolated frames per snapshot pair (smooth motion)")
    ap.add_argument("--hold-seconds", type=float, default=2.8)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--gif", action="store_true", help="also write a .gif")
    ap.add_argument("--keep-frames", action="store_true")
    args = ap.parse_args()

    scenario, snapshots, summary = load_emits(args.run)
    pore_count = int(scenario["pores"])
    pores = pore_angles(pore_count)
    total_ticks = int(scenario.get("ticks") or snapshots[-1]["tick"])

    frames_dir = args.frames_dir or args.out.parent / (args.out.stem + "_frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    t = np.array([int(s["tick"]) for s in snapshots])
    inside_h2o = np.array([int(s["inside_h2o"]) for s in snapshots])
    outside_h2o = np.array([int(s["outside_h2o"]) for s in snapshots])
    flux = np.array([int(s["net_water_flux_out"]) for s in snapshots])
    mean_r = np.array([float(s.get("membrane_mean_radius") or 0.0) for s in snapshots])
    rejections = np.array([int(s.get("wrong_polarized_rejections") or 0) for s in snapshots])
    r0 = float(scenario["cellRadius"])
    init_water = float((scenario.get("ratioInside") or {}).get("h2o") or inside_h2o[0])

    n_anim = len(snapshots)
    tween = max(1, int(args.tween))
    # Each consecutive snapshot pair is subdivided into `tween` interpolated
    # frames so glucose/ions glide instead of teleporting.
    n_motion = (n_anim - 1) * tween + 1
    n_hold = int(round(args.hold_seconds * args.fps))
    n_frames = n_motion + n_hold
    dpi = 100
    figsize = (args.width / dpi, args.height / dpi)
    print(f"loaded {n_anim} membrane snapshots from {args.run}")
    print(f"rendering {n_frames} frames @ {args.fps} fps (tween x{tween})")

    for frame_idx in range(n_frames):
        if frame_idx >= n_motion:
            snap_idx = n_anim - 1
            frame = interp_frame(snapshots[snap_idx], snapshots[snap_idx], 0.0)
            end_card = True
        else:
            pair = min(frame_idx // tween, n_anim - 2)
            u = (frame_idx - pair * tween) / tween
            snap_idx = pair
            frame = interp_frame(snapshots[pair], snapshots[pair + 1], u)
            end_card = False
        tick = frame["tick"]
        phase = frame["phase"]

        fig = plt.figure(figsize=figsize, dpi=dpi, facecolor=BG_COLOR)
        gs = GridSpec(2, 2, width_ratios=[1.22, 1.0], height_ratios=[1.0, 1.0],
                      figure=fig, left=0.01, right=0.965, top=0.9, bottom=0.1,
                      wspace=0.18, hspace=0.32)
        axc = fig.add_subplot(gs[:, 0])
        draw_cell(axc, frame, scenario, pores, init_water)

        # --- population panel ---
        ax1 = fig.add_subplot(gs[0, 1], facecolor=BG_COLOR)
        for sp in ax1.spines.values():
            sp.set_color(GRID_COLOR)
        ax1.tick_params(colors=FG_COLOR, labelsize=8)
        ax1.set_xlim(0, total_ticks)
        ax1.set_ylim(0, max(100, float(max(outside_h2o.max(), inside_h2o.max())) + 8))
        ax1.set_ylabel("H2O count", color=FG_COLOR, fontsize=9)
        ax1.plot(t[:snap_idx + 1], inside_h2o[:snap_idx + 1], color="#3b8bd9",
                 lw=2.2, label="H2O inside (cytoplasm)")
        ax1.plot(t[:snap_idx + 1], outside_h2o[:snap_idx + 1], color=WATER_COLOR,
                 lw=2.2, label="H2O outside (bath)")
        ax1b = ax1.twinx()
        ax1b.set_ylim(0, max(85, float(flux.max()) + 5))
        ax1b.tick_params(colors="#b6f5b6", labelsize=8)
        ax1b.set_ylabel("net flux out", color="#b6f5b6", fontsize=9)
        ax1b.plot(t[:snap_idx + 1], flux[:snap_idx + 1], color=TRECH_GREEN,
                  lw=1.6, ls="--", label="net flux out")
        for xv in (50, 500, 5000):
            ax1.axvline(xv, color="#6b7280", lw=0.7, ls=":")
        ax1.grid(True, color=GRID_COLOR, alpha=0.25)
        leg = ax1.legend(loc="center right", fontsize=7.5, facecolor="#161b22",
                         edgecolor=GRID_COLOR)
        for txt in leg.get_texts():
            txt.set_color(FG_COLOR)

        # --- membrane / crenation panel ---
        ax2 = fig.add_subplot(gs[1, 1], facecolor=BG_COLOR)
        for sp in ax2.spines.values():
            sp.set_color(GRID_COLOR)
        ax2.tick_params(colors=FG_COLOR, labelsize=8)
        ax2.set_xlim(0, total_ticks)
        ax2.set_ylim(0, r0 * 1.08)
        ax2.set_xlabel("TRECH event tick", color=FG_COLOR, fontsize=9)
        ax2.set_ylabel("cell mean radius", color=MEMBRANE_HEAD, fontsize=9)
        ax2.axhline(r0, color="#6b7280", lw=0.7, ls=":")
        ax2.plot(t[:snap_idx + 1], mean_r[:snap_idx + 1], color=MEMBRANE_HEAD,
                 lw=2.4, label="membrane radius (crenation)")
        ax2b = ax2.twinx()
        ax2b.set_ylim(0, max(50, float(rejections.max()) + 5))
        ax2b.tick_params(colors=ION_COLOR, labelsize=8)
        ax2b.set_ylabel("wrong-pol. expelled", color=ION_COLOR, fontsize=9)
        ax2b.plot(t[:snap_idx + 1], rejections[:snap_idx + 1], color=ION_COLOR,
                  lw=1.6, label="ions/glucose rejected")
        ax2.grid(True, color=GRID_COLOR, alpha=0.25)
        leg2 = ax2.legend(loc="upper right", fontsize=7.5, facecolor="#161b22",
                          edgecolor=GRID_COLOR)
        for txt in leg2.get_texts():
            txt.set_color(FG_COLOR)

        fig.suptitle(
            "TRECH cell in a hypertonic bath — osmotic dehydration & crenation",
            color=FG_COLOR, fontsize=15, y=0.965, weight="bold")
        fig.text(0.012, 0.915,
                 "Geant4 event clock + deterministic hook MD  ·  water shown as a "
                 "solvent field; the membrane expels wrong-polarized molecules",
                 color="#9aa3ad", fontsize=8.5)

        # legend swatches for the cell
        sw = [(WATER_COLOR, "H2O — solvent (blue wash, fades as expelled)", "▬"),
              (GLUCOSE_COLOR, "glucose (size-excluded)", "●"),
              (ION_COLOR, "ion (wrong polarity, expelled)", "●"),
              (EXPEL_COLOR, "membrane rejection flash", "✦")]
        for i, (col, lab, mk) in enumerate(sw):
            yy = 0.86 - i * 0.033
            fig.text(0.022, yy, mk, color=col, fontsize=11, va="center")
            fig.text(0.044, yy, lab, color=FG_COLOR, fontsize=8.2, va="center")

        phase_c = phase_color(phase)
        hud = (f"tick {tick:4d}/{total_ticks}   phase={phase}   "
               f"H2O in/out={frame['inside_h2o_i']}/{frame['outside_h2o_i']}   "
               f"wrong-polarized expelled={frame['rejections']}")
        fig.text(0.012, 0.045, hud, color=phase_c, fontsize=10,
                 family="monospace")
        fig.text(0.012, 0.018,
                 "Replay of emitted TRECH state. No fixed osmotic law drives this "
                 "video; radial coordinate conformed to the emitted membrane.",
                 color="#838c97", fontsize=8)

        if end_card and summary:
            val = summary.get("validation") or {}
            mem = summary.get("membrane") or {}
            lines = [
                f"validation checks: {sum(1 for v in val.values() if v)}/{len(val)} passed",
                f"net water flux out: {summary.get('net_water_flux_out')}  "
                f"(first crossing tick {summary.get('first_crossing_tick')})",
                f"wrong-polarized molecules expelled: {summary.get('wrong_polarized_rejections')}",
                f"cell radius: {mem.get('initial_mean_radius')} -> "
                f"{mem.get('final_mean_radius')}  "
                f"(area -{int(100 * float(mem.get('area_shrink_fraction', 0)))}%, crenated)",
            ]
            axc.text(0.5, 0.5, "\n".join(lines), transform=axc.transAxes,
                     ha="center", va="center", color=FG_COLOR, fontsize=11,
                     family="monospace", zorder=20,
                     bbox=dict(facecolor="#10151c", edgecolor=TRECH_GREEN,
                               boxstyle="round,pad=0.7", alpha=0.95))

        fig.savefig(frames_dir / f"frame_{frame_idx:04d}.png", facecolor=BG_COLOR)
        plt.close(fig)
        if (frame_idx + 1) % 30 == 0 or frame_idx + 1 == n_frames:
            print(f"  frame {frame_idx + 1}/{n_frames}")

    print(f"encoding {args.out}")
    rc = encode_video(frames_dir, args.out, args.fps)
    if rc == 0 and args.gif:
        gif = args.out.with_suffix(".gif")
        palette = frames_dir / "palette.png"
        subprocess.run(["ffmpeg", "-y", "-i", str(args.out),
                        "-vf", "fps=12,scale=720:-1:flags=lanczos,palettegen",
                        str(palette)], capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(args.out), "-i", str(palette),
                        "-lavfi", "fps=12,scale=720:-1:flags=lanczos[x];[x][1:v]paletteuse",
                        str(gif)], capture_output=True)
        print(f"wrote {gif}")
    if rc == 0 and not args.keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)
    if rc == 0:
        print(f"wrote {args.out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
