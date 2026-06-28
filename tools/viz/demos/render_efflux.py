"""Render the membrane-efflux scenario as a TRECH-vs-classical-law comparison.

Same spirit as the bulk-water g(r) demo: a physical simulation on the left, an
accumulating quantitative comparison against a closed-form law on the right.

``testscenario_efflux.js`` models a cell clearing a lipophilic "waste" molecule
by passive permeation across the lipid bilayer (Overton's rule) into an
extracellular sink, while retaining its polar "essential" molecules. The
scenario emits, from Geant4 event callbacks (one event = one MD tick):

* ``efflux_snapshot`` -- per-molecule positions/state + the internal waste count;
* ``efflux_summary`` -- the least-squares first-order fit (rate k, R^2, half-life,
  back-derived permeability) and the Geant4-derived membrane/cytosol interaction
  ratio that scaled the permeation probability;
* ``scenario`` -- geometry + the Geant4 nanoscale anchors.

The right panel overlays the **simulated** internal count N(t) (green, replayed
from the emits) on the **classical first-order clearance law** N0*exp(-k t)
(amber) -- demonstrating that random microscopic permeation events reproduce the
macroscopic Fick/Overton clearance kinetics. No fixed law moves the molecules;
the law is the comparison target, exactly like the measured 2.80 A peak in the
bulk-water demo.

Run::

    PYTHONPATH=tools/pubchem python3 -m trech_pubchem fetch \
        --cache-dir build/dev/pubchem_cache benzene "D-glucose"

    TRECH_PUBCHEM_CACHE_DIR=build/dev/pubchem_cache \
    trech run examples/experiments/testscenario_efflux.js \
        --events 6000 --output build/dev/out_efflux

    cd tools/viz
    source .venv/bin/activate
    python demos/render_efflux.py --gif

Output: ``tools/viz/demos/efflux_clearance.mp4`` (+ ``.gif`` with --gif).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_efflux"
DEFAULT_OUT = Path(__file__).resolve().parent / "efflux_clearance.mp4"


def pubchem_cache_dirs() -> List[Path]:
    dirs: List[Path] = []
    env = os.environ.get("TRECH_PUBCHEM_CACHE_DIR")
    if env:
        dirs.append(Path(env))
    dirs.append(REPO_ROOT / "build" / "dev" / "pubchem_cache")
    dirs.append(REPO_ROOT / "data" / "pubchem")
    return dirs


def pubchem_png(name: str):
    """Load a cached PubChem 2D structure image (white background) or None."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    for root in pubchem_cache_dirs():
        path = root / f"{slug}.png"
        if path.exists():
            try:
                return mpimg.imread(str(path))
            except Exception:
                return None
    return None

BG_COLOR = "#080b11"
EXTRA_COLOR = "#0c1420"
FG_COLOR = "#e8edf2"
GRID_COLOR = "#3a414c"
WASTE_COLOR = "#c870ff"      # lipophilic xenobiotic / "waste"
ESSENTIAL_COLOR = "#5cc8ff"  # polar molecules the cell retains
MEMBRANE_HEAD = "#ffd27f"
MEMBRANE_TAIL = "#caa24e"
CYTOPLASM = "#16b39a"
NUCLEUS = "#7c5cc0"
ORGANELLE = "#3fae9a"
SIM_GREEN = "#7fdc7f"
LAW_AMBER = "#f2b25a"
TWO_PI = 2.0 * math.pi
TELEPORT_STEP = 30.0


def load_emits(run_dir: Path) -> Tuple[Dict, List[Dict], Dict]:
    emits = run_dir / "trech_hook_emits.jsonl"
    if not emits.exists():
        raise SystemExit(f"error: {emits} not found; run testscenario_efflux.js first")
    scenario: Optional[Dict] = None
    summary: Optional[Dict] = None
    snaps: Dict[int, Dict] = {}
    with emits.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            payload = rec.get("payload") or {}
            tag = rec.get("tag")
            if tag == "scenario":
                scenario = payload
            elif tag == "efflux_snapshot":
                snaps[int(payload.get("tick", 0))] = payload
            elif tag == "efflux_summary":
                summary = payload
    if scenario is None or summary is None or not snaps:
        raise SystemExit("error: missing scenario/efflux_summary/efflux_snapshot emits "
                         "(use a clean --output dir; emits append)")
    ordered = [snaps[t] for t in sorted(snaps)]
    return scenario, ordered, summary


def index_by_id(snapshot: Dict) -> Dict[int, Dict]:
    return {int(p["id"]): p for p in snapshot.get("particles") or []}


def interp_frame(snap_a: Dict, snap_b: Dict, u: float) -> Dict:
    idx_a = index_by_id(snap_a)
    idx_b = index_by_id(snap_b)
    rows: List[List[float]] = []
    for pid, pa in idx_a.items():
        pb = idx_b.get(pid, pa)
        ax_, ay_ = float(pa["x"]), float(pa["y"])
        bx_, by_ = float(pb["x"]), float(pb["y"])
        kind = 0.0 if pa.get("k") == "waste" else 1.0
        if math.hypot(bx_ - ax_, by_ - ay_) > TELEPORT_STEP:
            src = pa if u < 0.5 else pb
            x, y, s = float(src["x"]), float(src["y"]), float(src["s"])
        else:
            x = (1.0 - u) * ax_ + u * bx_
            y = (1.0 - u) * ay_ + u * by_
            s = float((pa if u < 0.5 else pb).get("s", 0))
        rows.append([x, y, kind, s])
    arr = np.array(rows) if rows else np.zeros((0, 4))
    return {
        "p": arr,  # columns: x, y, kind(0 waste / 1 essential), state(0 in /2 cleared)
        "tick": int(snap_a["tick"]),
        "waste_inside": int(snap_a["waste_inside"]),
        "waste_cleared": int(snap_a["waste_cleared"]),
        "retained_inside": int(snap_a["retained_inside"]),
    }


def draw_cell(ax, frame: Dict, scenario: Dict) -> None:
    r0 = float(scenario["cellRadius"])
    half = float(scenario["domainHalfSize"])
    ax.set_facecolor(BG_COLOR)
    ax.set_xlim(-half * 0.82, half * 0.82)
    ax.set_ylim(-half * 0.82, half * 0.82)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.add_patch(plt.Rectangle((-half, -half), 2 * half, 2 * half,
                               facecolor=EXTRA_COLOR, edgecolor="none", zorder=0))
    th = np.linspace(0, TWO_PI, 220)
    ox, oy = r0 * np.cos(th), r0 * np.sin(th)
    inner = r0 - 1.5
    ix, iy = inner * np.cos(th), inner * np.sin(th)
    ax.add_patch(Polygon(np.column_stack([ox, oy]), closed=True,
                         facecolor=MEMBRANE_TAIL, alpha=0.22, edgecolor="none", zorder=1))
    ax.add_patch(Polygon(np.column_stack([ix, iy]), closed=True,
                         facecolor=BG_COLOR, alpha=1.0, edgecolor="none", zorder=1))
    ax.add_patch(Polygon(np.column_stack([ix, iy]), closed=True,
                         facecolor=CYTOPLASM, alpha=0.15, edgecolor="none", zorder=2))
    ax.plot(ox, oy, color=MEMBRANE_HEAD, lw=1.8, alpha=0.95, zorder=4)
    ax.plot(ix, iy, color=MEMBRANE_HEAD, lw=1.1, alpha=0.65, zorder=4)
    head_th = np.linspace(0, TWO_PI, 110, endpoint=False)
    ax.scatter(r0 * np.cos(head_th), r0 * np.sin(head_th), s=9,
               c=MEMBRANE_HEAD, alpha=0.5, edgecolors="none", zorder=4)

    ax.add_patch(Ellipse((0, 0), 2 * 0.32 * r0, 2 * 0.28 * r0, facecolor=NUCLEUS,
                         alpha=0.30, edgecolor=NUCLEUS, lw=1.0, zorder=3))
    ax.add_patch(Ellipse((0.05 * r0, -0.02 * r0), 2 * 0.09 * r0, 2 * 0.08 * r0,
                         facecolor=NUCLEUS, alpha=0.55, edgecolor="none", zorder=3))
    for ang, rad, w, h in [(0.9, 0.6, 0.11, 0.055), (3.7, 0.56, 0.09, 0.05),
                           (5.3, 0.58, 0.10, 0.05)]:
        ax.add_patch(Ellipse((rad * r0 * math.cos(ang), rad * r0 * math.sin(ang)),
                             2 * w * r0, 2 * h * r0, angle=math.degrees(ang),
                             facecolor=ORGANELLE, alpha=0.42, edgecolor="none", zorder=3))

    p = frame["p"]
    if len(p):
        waste = p[p[:, 2] == 0.0]
        ess = p[p[:, 2] == 1.0]
        # essentials (retained, inside) -- drawn as ring-molecule hexagons
        if len(ess):
            ax.scatter(ess[:, 0], ess[:, 1], s=58, c=ESSENTIAL_COLOR, marker="h",
                       alpha=0.95, edgecolors="#06121a", linewidths=0.4, zorder=6)
        # waste: inside (bright) vs cleared/leaving (fading outward)
        win = waste[waste[:, 3] == 0.0]
        wout = waste[waste[:, 3] == 2.0]
        if len(win):
            ax.scatter(win[:, 0], win[:, 1], s=58, c=WASTE_COLOR, marker="h",
                       alpha=0.95, edgecolors="#06121a", linewidths=0.4, zorder=7)
        if len(wout):
            rr = np.hypot(wout[:, 0], wout[:, 1])
            fade = np.clip(1.1 - (rr - r0) / (half - r0), 0.12, 0.85)
            for (xx, yy, a) in zip(wout[:, 0], wout[:, 1], fade):
                ax.scatter([xx], [yy], s=44, c=WASTE_COLOR, marker="h",
                           alpha=float(a), edgecolors="none", zorder=5)


def encode_video(frames_dir: Path, out: Path, fps: int) -> int:
    cmd = ["ffmpeg", "-y", "-framerate", str(fps),
           "-i", str(frames_dir / "frame_%04d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
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
    ap.add_argument("--tween", type=int, default=3)
    ap.add_argument("--hold-seconds", type=float, default=3.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--gif", action="store_true")
    ap.add_argument("--keep-frames", action="store_true")
    args = ap.parse_args()

    scenario, snaps, summary = load_emits(args.run)
    total_ticks = int(scenario.get("ticks") or snaps[-1]["tick"])
    n0 = float(summary["initial_waste"])
    fit = summary["fit"]
    k = float(fit["rate_per_tick"])
    r2 = float(fit["r_squared"])
    half_life = float(fit["half_life_ticks"])
    p_eff = float(fit["permeability_eff_units_per_tick"])
    g4 = summary["geant4"]
    ratio = float(g4["interaction_ratio"])
    pub = (summary.get("pubchem") or scenario.get("pubchem") or {})
    perm = pub.get("permeant") or {"name": "permeant", "xlogp": None}
    ret = pub.get("retained") or {"name": "retained", "xlogp": None}
    perm_img = pubchem_png(perm.get("name"))
    ret_img = pubchem_png(ret.get("name"))

    series_t = np.array([int(s["tick"]) for s in snaps])
    series_n = np.array([int(s["waste_inside"]) for s in snaps])
    law_t = np.linspace(0, total_ticks, 400)
    law_n = n0 * np.exp(-k * law_t)

    frames_dir = args.frames_dir or args.out.parent / (args.out.stem + "_frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    n_anim = len(snaps)
    tween = max(1, int(args.tween))
    n_motion = (n_anim - 1) * tween + 1
    n_hold = int(round(args.hold_seconds * args.fps))
    n_frames = n_motion + n_hold
    dpi = 100
    figsize = (args.width / dpi, args.height / dpi)
    print(f"loaded {n_anim} efflux snapshots from {args.run}")
    print(f"rendering {n_frames} frames @ {args.fps} fps (tween x{tween})")

    for fi in range(n_frames):
        if fi >= n_motion:
            idx = n_anim - 1
            frame = interp_frame(snaps[idx], snaps[idx], 0.0)
            end_card = True
        else:
            pair = min(fi // tween, n_anim - 2)
            u = (fi - pair * tween) / tween
            idx = pair
            frame = interp_frame(snaps[pair], snaps[pair + 1], u)
            end_card = False
        tick = frame["tick"]

        fig = plt.figure(figsize=figsize, dpi=dpi, facecolor=BG_COLOR)
        gs = GridSpec(1, 2, width_ratios=[1.0, 1.18], figure=fig,
                      left=0.01, right=0.955, top=0.90, bottom=0.31, wspace=0.16)
        axc = fig.add_subplot(gs[0, 0])
        draw_cell(axc, frame, scenario)

        # --- comparison panel: simulated decay vs first-order law ---
        ax = fig.add_subplot(gs[0, 1], facecolor=BG_COLOR)
        for sp in ax.spines.values():
            sp.set_color(GRID_COLOR)
        ax.tick_params(colors=FG_COLOR, labelsize=9)
        ax.set_xlim(0, total_ticks)
        ax.set_ylim(0, n0 * 1.08)
        ax.set_xlabel("TRECH event tick", color=FG_COLOR, fontsize=10)
        ax.set_ylabel("waste molecules inside the cell", color=FG_COLOR, fontsize=10)
        ax.grid(True, color=GRID_COLOR, alpha=0.25)
        # classical law (full range, faint ahead of playback)
        ax.plot(law_t, law_n, color=LAW_AMBER, lw=2.4, ls="--",
                label=r"classical law  $N_0\,e^{-kt}$  (Fick / first-order)")
        # half-life marker
        ax.axvline(half_life, color="#6b7280", lw=0.9, ls=":")
        ax.text(half_life + total_ticks * 0.012, n0 * 0.5,
                f"t½ = {half_life:.0f} ticks", color="#9aa3ad", fontsize=8.5,
                rotation=90, va="center")
        ax.axhline(n0 * 0.5, color="#6b7280", lw=0.6, ls=":")
        # simulated, up to current tick
        upto = series_t <= tick
        ax.plot(series_t[upto], series_n[upto], color=SIM_GREEN, lw=1.6, alpha=0.6)
        ax.scatter(series_t[upto], series_n[upto], s=16, c=SIM_GREEN,
                   edgecolors="none", zorder=5,
                   label="TRECH simulated  N(t)")
        leg = ax.legend(loc="upper right", fontsize=9, facecolor="#161b22",
                        edgecolor=GRID_COLOR)
        for txt in leg.get_texts():
            txt.set_color(FG_COLOR)
        ax.text(0.50, 0.62,
                f"R² = {r2:.3f}", transform=ax.transAxes, color=SIM_GREEN,
                fontsize=12, ha="left", va="center", family="monospace")

        fig.suptitle("TRECH membrane efflux — a cell clears a lipophilic waste molecule "
                     "vs the first-order clearance law",
                     color=FG_COLOR, fontsize=13.5, y=0.965, weight="bold")
        fig.text(0.012, 0.925,
                 "Geant4 event clock + deterministic hook MD  ·  passive lipid permeation "
                 "(Overton's rule), polar essentials retained",
                 color="#9aa3ad", fontsize=8.3)

        # --- bottom "molecule passport" strip: real PubChem structures ---
        def structure_card(img, rect, color, title, sub):
            cax = fig.add_axes(rect)
            if img is not None:
                cax.imshow(img)
            cax.set_xticks([]); cax.set_yticks([])
            for s in cax.spines.values():
                s.set_color(color); s.set_linewidth(1.6)
            cax.set_facecolor("white")
            fig.text(rect[0] + rect[2] + 0.008, rect[1] + rect[3] - 0.02, title,
                     color=color, fontsize=10.5, weight="bold", va="top")
            fig.text(rect[0] + rect[2] + 0.008, rect[1] + rect[3] - 0.075, sub,
                     color=FG_COLOR, fontsize=8.6, va="top")

        px = perm.get("xlogp")
        rx = ret.get("xlogp")
        structure_card(
            perm_img, [0.035, 0.045, 0.115, 0.20], WASTE_COLOR,
            f"{perm.get('name')}  (waste)",
            f"PubChem CID {perm.get('cid','?')}\nXLogP {px:+.1f} → lipophilic\n→ permeates the\n   bilayer, cleared"
            if px is not None else "lipophilic → cleared")
        structure_card(
            ret_img, [0.305, 0.045, 0.115, 0.20], ESSENTIAL_COLOR,
            f"{ret.get('name')}  (essential)",
            f"PubChem CID {ret.get('cid','?')}\nXLogP {rx:+.1f} → polar\n→ cannot enter lipid,\n   retained"
            if rx is not None else "polar → retained")

        hud = (f"tick {tick:4d}/{total_ticks}    waste inside={frame['waste_inside']:2d}/"
               f"{int(n0)}    cleared={frame['waste_cleared']:2d}    "
               f"essentials retained={frame['retained_inside']}/{int(scenario['initialRetained'])}")
        fig.text(0.52, 0.225, hud, color=SIM_GREEN, fontsize=9.5, family="monospace")
        fig.text(0.52, 0.165,
                 "Two real anchors drive the run:", color=FG_COLOR, fontsize=9.2,
                 weight="bold")
        fig.text(0.52, 0.125,
                 f"• PubChem XLogP (Overton's rule) sets WHICH molecule permeates "
                 f"({perm.get('name')} {px:+.1f} vs {ret.get('name')} {rx:+.1f}).",
                 color="#c7d0da", fontsize=8.6)
        fig.text(0.52, 0.088,
                 f"• Geant4 G4EmCalculator μ(membrane)={g4['mu_membrane_per_mm']:.4f} vs "
                 f"μ(cytosol)={g4['mu_cytosol_per_mm']:.4f} /mm → ratio {ratio:.2f} scales "
                 f"HOW FAST (illustrative).",
                 color="#c7d0da", fontsize=8.6)
        fig.text(0.52, 0.048,
                 "Random microscopic permeation reproduces the macroscopic first-order law. "
                 "Replay of emitted TRECH state.",
                 color="#838c97", fontsize=8.2)

        if end_card:
            lines = [
                "first-order clearance confirmed",
                f"R² = {r2:.3f}   (N(t) = N₀·e^(−kt))",
                f"half-life = {half_life:.0f} ticks",
                f"cleared {summary['total_cleared']}/{int(n0)} waste, "
                f"retained {summary['retained_inside']}/{int(scenario['initialRetained'])} essentials",
                f"P_eff = {p_eff:.4f} (units/tick), from Geant4 μ-ratio {ratio:.2f}",
            ]
            axc.text(0.5, 0.5, "\n".join(lines), transform=axc.transAxes,
                     ha="center", va="center", color=FG_COLOR, fontsize=10.5,
                     family="monospace", zorder=20,
                     bbox=dict(facecolor="#10151c", edgecolor=SIM_GREEN,
                               boxstyle="round,pad=0.7", alpha=0.95))

        fig.savefig(frames_dir / f"frame_{fi:04d}.png", facecolor=BG_COLOR)
        plt.close(fig)
        if (fi + 1) % 40 == 0 or fi + 1 == n_frames:
            print(f"  frame {fi + 1}/{n_frames}")

    print(f"encoding {args.out}")
    rc = encode_video(frames_dir, args.out, args.fps)
    if rc == 0 and args.gif:
        gif = args.out.with_suffix(".gif")
        palette = frames_dir / "palette.png"
        subprocess.run(["ffmpeg", "-y", "-i", str(args.out), "-vf",
                        "fps=10,scale=620:-1:flags=lanczos,palettegen=max_colors=128",
                        str(palette)], capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(args.out), "-i", str(palette), "-lavfi",
                        "fps=10,scale=620:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=2",
                        str(gif)], capture_output=True)
        print(f"wrote {gif}")
    if rc == 0 and not args.keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)
    if rc == 0:
        print(f"wrote {args.out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
