"""Briggs-Rauscher oscillating-reaction animation.

Reads the ``br_frame`` hook emits from a run of
``examples/experiments/briggs_rauscher_oscillator.js`` and draws what an observer
sees: an open beaker whose liquid cycles colourless -> amber -> deep blue-black
-> colourless, beside the live emergent [I2] / [I-] concentration traces and a
phase-band timeline. Every colour, concentration, and the cycle count come
straight from TRECH's emitted frames -- the renderer adds no chemistry. If
``docs/validation_report.json`` carries the ``briggs_rauscher_oscillation`` case,
its status badge + summary are overlaid so the GIF doubles as a status view.

Run::

    cd tools/viz
    .venv/bin/python demos/render_briggs_rauscher.py            # default run dir
    .venv/bin/python demos/render_briggs_rauscher.py <run_dir>

Output: ``tools/viz/demos/briggs_rauscher.gif``.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle, Polygon  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
REPORT = REPO_ROOT / "docs" / "validation_report.json"

BG = "#0e1014"
PANEL = "#1b1f26"
FG = "#e8e8e8"
MUTED = "#9aa3ad"
GRID = "#555c66"
GREEN = "#7fdc7f"
AMBER = "#ffb347"
RED = "#ff6b6b"

# Display swatches (rendering choice; the *timing* of each is TRECH's emergent
# chemistry, read from the emitted amber/blue intensities).
WATER_CLEAR = np.array([0.82, 0.91, 0.99])
AMBER_RGB = np.array([0.88, 0.53, 0.05])
BLUE_BLACK = np.array([0.05, 0.11, 0.42])
IODINE_C = "#ffb347"   # [I2] trace
IODIDE_C = "#5fa8ff"   # [I-] trace


def load_frames(run_dir: Path):
    path = run_dir / "trech_hook_emits.jsonl"
    if not path.exists():
        raise SystemExit(f"no hook emits at {path}")
    frames: List[Dict] = []
    summary: Optional[Dict] = None
    scenario: Optional[Dict] = None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        tag, payload = rec.get("tag"), rec.get("payload")
        if tag == "br_frame":
            frames.append(payload)
        elif tag == "briggs_rauscher_summary":
            summary = payload
        elif tag == "briggs_rauscher_scenario":
            scenario = payload
    frames.sort(key=lambda f: f.get("frame", 0))
    return frames, summary, scenario


def load_case() -> Optional[Dict]:
    if not REPORT.exists():
        return None
    try:
        data = json.loads(REPORT.read_text())
    except json.JSONDecodeError:
        return None
    for c in data.get("results", []):
        if c.get("name") == "briggs_rauscher_oscillation":
            return c
    return None


def display_rgb(amber: float, blue: float):
    c = WATER_CLEAR * (1 - amber) + AMBER_RGB * amber
    c = c * (1 - blue) + BLUE_BLACK * blue
    return np.clip(c, 0, 1)


def beaker_outline(cx, base_y, top_y, half_w):
    """A rounded-bottom beaker as a polygon (open top)."""
    pts = [(cx - half_w, top_y)]
    n = 22
    for k in range(n + 1):
        a = math.pi * (1.0 - k / n)  # pi -> 0 across the bottom arc
        pts.append((cx + half_w * math.cos(a), base_y + 0.10 * half_w * (math.sin(a) - 1) + 0.0))
    pts.append((cx + half_w, top_y))
    return pts


def render(run_dir: Path):
    frames, summary, scenario = load_frames(run_dir)
    if not frames:
        raise SystemExit("no br_frame emits found")
    n = len(frames)
    t = np.array([f.get("time_s", i) for i, f in enumerate(frames)], dtype=float)
    I2 = np.array([f["concentrations"]["iodine_I2"] for f in frames])
    Im = np.array([f["concentrations"]["iodide_I_minus"] for f in frames])
    amber = np.array([f["intensities"]["amber"] for f in frames])
    blue = np.array([f["intensities"]["blue"] for f in frames])
    cyc = np.array([f.get("cycle_index", 0) for f in frames])
    regimes = [f["phase"].split(":")[-1] for f in frames]

    coeff = (summary or {}).get("inferred_coefficients", {})
    emergent = (summary or {}).get("emergent", {})
    recipe = (scenario or {}).get("recipe", {})
    g4 = (summary or {}).get("geant4", {})
    case = load_case()

    period = float(emergent.get("mean_period_seconds", 0.0))
    cycles_done = int(emergent.get("cycles_completed", 0))

    # persistent O2-bubble streams (deterministic; smooth rise -> low GIF churn)
    brng = np.random.default_rng(7)
    NB = 16
    bub = [{"x0": brng.uniform(-0.7, 0.7), "phase": brng.uniform(0, 1),
            "speed": 0.010 + 0.010 * brng.uniform(), "r": 0.006 + 0.004 * brng.uniform(),
            "sway": brng.uniform(0, 2 * math.pi)} for _ in range(NB)]

    fig = plt.figure(figsize=(9.2, 5.0), dpi=98, facecolor=BG)
    fig.text(0.035, 0.955, "Briggs–Rauscher oscillator — colourless → amber → deep blue, from the beaker alone",
             color=FG, fontsize=12.5, ha="left", fontweight="bold")
    fig.text(0.035, 0.912,
             "Geant4 sees the reagents; ctx.cascade infers the Oregonator coefficients; the oscillation, colours & period EMERGE",
             color=MUTED, fontsize=8.4, ha="left", family="monospace")

    # status badge
    if case:
        st = case.get("status", "info")
        c = {"pass": GREEN, "info": AMBER, "fail": RED}.get(st, MUTED)
        axb = fig.add_axes([0.86, 0.925, 0.11, 0.055]); axb.set_axis_off()
        axb.add_patch(FancyBboxPatch((0.05, 0.1), 0.9, 0.8, boxstyle="round,pad=0.06",
                      facecolor=BG, edgecolor=c, linewidth=1.6))
        axb.text(0.5, 0.5, st.upper(), color=c, fontsize=10, fontweight="bold",
                 ha="center", va="center", family="monospace")

    # beaker axis (left)
    axB = fig.add_axes([0.04, 0.13, 0.36, 0.72]); axB.set_axis_off()
    axB.set_xlim(0, 1); axB.set_ylim(0, 1); axB.set_aspect("auto")
    cx, half_w, base_y, top_y = 0.5, 0.30, 0.16, 0.88
    liquid_top = 0.70
    outline = beaker_outline(cx, base_y, top_y, half_w)

    # concentration axis (right top)
    axC = fig.add_axes([0.48, 0.52, 0.48, 0.33]); axC.set_facecolor("#14181f")
    axC.set_xlim(t[0], t[-1]); axC.set_ylim(0, max(0.45, float(I2.max()) * 1.15))
    axC.tick_params(colors=MUTED, labelsize=7.5)
    for s in axC.spines.values():
        s.set_color(GRID)
    axC.set_ylabel("concentration (arb.)", color=FG, fontsize=8.5)
    axC.set_title("emergent species — free iodine [I₂] and iodide [I⁻]", color=MUTED, fontsize=8.5)

    # phase-band axis (right bottom)
    axP = fig.add_axes([0.48, 0.28, 0.48, 0.15]); axP.set_axis_off()
    axP.set_xlim(t[0], t[-1]); axP.set_ylim(0, 1)
    band_c = {"colourless": "#c7d2dc", "amber_free_iodine": "#e8963c",
              "deep_blue_triiodide_starch": "#20306e"}
    for i in range(n):
        axP.add_patch(Rectangle((t[i], 0.35), (t[1] - t[0]) if n > 1 else 1, 0.55,
                      color=band_c.get(regimes[i], MUTED), ec="none"))

    footer = ("recipe (known): KIO₃ %.2f M · H₂O₂ %.2f M · malonic %.2f M · H⁺ %.2f M · MnSO₄ %.1f mM   |   "
              "Geant4 sees  I %.2g /cm³ · Mn %.2g /cm³" % (
                  recipe.get("iodateMolarity", 0), recipe.get("peroxideMolarity", 0),
                  recipe.get("malonicMolarity", 0), recipe.get("acidMolarity", 0),
                  recipe.get("manganeseMilliMolarity", 0),
                  g4.get("iodine_atoms_per_cm3", 0), g4.get("manganese_atoms_per_cm3", 0)))
    fig.text(0.035, 0.055, footer, color=FG, fontsize=7.2, family="monospace")
    if case:
        summ = case.get("summary", "")
        if len(summ) > 118:
            summ = summ[:116] + "…"
        fig.text(0.035, 0.028, "validated by  briggs_rauscher_oscillation   " + summ,
                 color=MUTED, fontsize=7.0, family="monospace")
    else:
        fig.text(0.035, 0.028,
                 "inferred Oregonator: f=%.2f ε=%.2f  |  emergent: %d cycles, period ≈ %.1f s, then settles (reagent depletion)"
                 % (coeff.get("macro_oregonator_f", coeff.get("f", 0.0)) if False else coeff.get("f", 0.0),
                    coeff.get("epsilon", 0.0), cycles_done, period),
                 color=MUTED, fontsize=7.0, family="monospace")

    def draw(i):
        axB.cla(); axB.set_axis_off(); axB.set_xlim(0, 1); axB.set_ylim(0, 1)
        rgb = display_rgb(float(amber[i]), float(blue[i]))
        colouredness = max(float(amber[i]), float(blue[i]))
        alpha = 0.5 + 0.48 * min(1.0, colouredness)
        # liquid: clip the beaker polygon down to the liquid surface. A pale
        # backdrop makes the colourless phase read as clear liquid, not empty.
        liquid = [(x, min(y, liquid_top)) for (x, y) in outline]
        axB.add_patch(Polygon(liquid, closed=True, facecolor="#20262e", alpha=1.0,
                              edgecolor="none", zorder=1))
        axB.add_patch(Polygon(liquid, closed=True, facecolor=tuple(rgb), alpha=alpha,
                              edgecolor="none", zorder=2))
        axB.plot([cx - half_w, cx + half_w], [liquid_top, liquid_top],
                 color=tuple(np.clip(rgb * 0.7, 0, 1)), lw=1.6, alpha=min(1.0, alpha + 0.2), zorder=3)
        # glass outline (open top)
        axB.plot([p[0] for p in outline], [p[1] for p in outline],
                 color="#9fb0c0", lw=2.4, zorder=4, solid_capstyle="round")
        # O2 bubbles rising from the reaction (persistent streams; O2 is a real
        # product of the overall reaction). More visible while the run is active.
        active = 0.35 + 0.5 * min(1.0, colouredness + float(I2[i]) * 2.0)
        span = liquid_top - base_y - 0.04
        for b in bub:
            frac = (b["phase"] + i * b["speed"]) % 1.0
            yy = base_y + 0.02 + frac * span
            xx = cx + b["x0"] * half_w * 0.72 * (1 - frac * 0.25) + 0.012 * math.sin(b["sway"] + frac * 6.0)
            axB.add_patch(Circle((xx, yy), b["r"], color="#eaf2ff",
                          alpha=0.30 * active, zorder=3))
        # stir bar (spinning)
        ang = i * 22.0
        axB.add_patch(Rectangle((cx - 0.07, base_y - 0.005), 0.14, 0.02, angle=ang,
                      rotation_point="center", color="#d8dde3", alpha=0.85, zorder=3))
        # phase label chip
        label = {"colourless": "colourless", "amber_free_iodine": "amber  (free I₂)",
                 "deep_blue_triiodide_starch": "deep blue  (I₃⁻·starch)"}[regimes[i]]
        lc = {"colourless": "#c7d2dc", "amber_free_iodine": AMBER,
              "deep_blue_triiodide_starch": "#6f8bff"}[regimes[i]]
        axB.text(cx, 0.965, label, color=lc, fontsize=10.5, ha="center",
                 va="top", family="monospace", fontweight="bold")
        axB.text(cx, 0.055, "cycle %d · t = %5.1f s" % (int(cyc[i]), float(t[i])),
                 color=FG, fontsize=8.5, ha="center", family="monospace")

        # concentration traces up to i
        axC.cla(); axC.set_facecolor("#14181f")
        axC.set_xlim(t[0], t[-1]); axC.set_ylim(0, max(0.45, float(I2.max()) * 1.15))
        axC.tick_params(colors=MUTED, labelsize=7.5)
        for s in axC.spines.values():
            s.set_color(GRID)
        axC.set_title("emergent species — free iodine [I₂] and iodide [I⁻]",
                      color=MUTED, fontsize=8.5)
        j = i + 1
        axC.plot(t[:j], I2[:j], color=IODINE_C, lw=1.7, label="[I₂] free iodine")
        axC.plot(t[:j], Im[:j], color=IODIDE_C, lw=1.4, alpha=0.9, label="[I⁻] iodide")
        axC.axvline(t[i], color=FG, lw=0.8, alpha=0.5)
        axC.legend(loc="upper right", fontsize=7, facecolor=PANEL, edgecolor=GRID,
                   labelcolor=FG, framealpha=0.8)

        # phase cursor
        axP.set_title("")
        for ln in list(axP.lines):
            ln.remove()
        axP.plot([t[i], t[i]], [0.30, 0.95], color=FG, lw=1.2, alpha=0.8)
        axP.text(t[0], 0.12, "colourless", color="#c7d2dc", fontsize=7, family="monospace")
        axP.text(t[0] + (t[-1] - t[0]) * 0.33, 0.12, "amber", color=AMBER, fontsize=7, family="monospace")
        axP.text(t[0] + (t[-1] - t[0]) * 0.55, 0.12, "deep blue", color="#6f8bff", fontsize=7, family="monospace")
        return []

    fps = 20
    anim = FuncAnimation(fig, draw, frames=n, interval=1000 / fps)
    out = OUT_DIR / "briggs_rauscher.gif"
    anim.save(out, writer=PillowWriter(fps=fps))
    plt.close(fig)
    # shrink: quantize every frame onto ONE shared adaptive palette (built from a
    # mid-run frame that carries all three colour regimes), then let PIL emit
    # minimal inter-frame diffs.
    try:
        from PIL import Image, ImageSequence
        src = Image.open(out)
        rgb_frames = [f.convert("RGB") for f in ImageSequence.Iterator(src)]
        palette_src = rgb_frames[min(len(rgb_frames) - 1, int(len(rgb_frames) * 0.55))]
        pal = palette_src.quantize(colors=96, method=Image.FASTOCTREE)
        seq = [f.quantize(palette=pal, dither=Image.NONE) for f in rgb_frames]
        seq[0].save(out, save_all=True, append_images=seq[1:], loop=0,
                    duration=int(1000 / fps), disposal=1, optimize=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  (palette optimize skipped: {exc})")
    size_mb = out.stat().st_size / 1e6
    print(f"wrote {out.relative_to(REPO_ROOT)}  ({n} frames, {size_mb:.1f} MB)")


if __name__ == "__main__":
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "build" / "dev" / "out_briggs_rauscher"
    render(run)
