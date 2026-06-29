"""Evident 3D animation of a carbon-nanotube logic circuit (CNTFET inverter chain).

A series of carbon-nanotube field-effect transistor channels (rolled-graphene
honeycomb tubes) wired as a 3-stage inverter chain IN -> NOT -> NOT -> NOT -> OUT.
Electrons stream through the CNT channels; a signal edge propagates down the
chain and the logic level at each node flips (the inverting CMOS stage), while
the camera pans across the circuit so the whole datapath is visible -- the
"electrons passing through a series of gates" view.

This is the device/circuit companion to ``cnt_structure.gif`` (single tubes) and
visualises what ``cnt_logic_gates.js`` computes: CNTFETs built from the
tight-binding band gap form static-CMOS gates whose truth tables are confirmed.
Honest scope (same as the CNT track): Geant4 transports electrons through the
channel geometry; the gate logic / Fermi-level switching is the hook-layer model.

Run::

    cd tools/viz
    source .venv/bin/activate
    python demos/render_cnt_circuit.py

Output: ``tools/viz/demos/cnt_circuit.gif``.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import List

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection  # noqa: E402

OUT = Path(__file__).resolve().parent / "cnt_circuit.gif"

BG = "#0e1014"
FG = "#e8e8e8"
MUTED = "#9aa3ad"
CARBON = "#aab4c2"
BOND = "#4a525f"
ELEC = "#5fe3ff"      # flowing electrons
HIGH = "#7fdc7f"      # logic 1
LOW = "#ff6b6b"       # logic 0
GATE = "#c89bff"      # gate electrode
ACC = 0.142


def build_segment(x0: float, ncirc: int, nz: int):
    """Honeycomb CNT channel along x starting at x0. Returns xyz, bonds, R, L."""
    a = math.sqrt(3.0) * ACC
    lx = a
    laxis = math.sqrt(3.0) * a
    cell = [(0.0, 0.0), (lx / 2, laxis / 6), (lx / 2, laxis / 2), (0.0, laxis * 2 / 3)]
    width = ncirc * lx
    radius = width / (2.0 * math.pi)
    pts: List[List[float]] = []
    for i in range(ncirc):
        for j in range(nz):
            for (cx, caxis) in cell:
                around = i * lx + cx
                x = x0 + j * laxis + caxis
                theta = 2.0 * math.pi * around / width
                pts.append([x, radius * math.cos(theta), radius * math.sin(theta)])
    P = np.array(pts)
    segs = []
    n = len(P)
    rcut = ACC * 1.25
    for i in range(n):
        d = P[i + 1:] - P[i]
        dist = np.sqrt((d * d).sum(axis=1))
        for k, dd in enumerate(dist):
            if dd < rcut:
                segs.append([P[i], P[i + 1 + k]])
    return P, segs, radius, nz * laxis


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--frames", type=int, default=80)
    ap.add_argument("--fps", type=int, default=15)
    args = ap.parse_args()

    nstage = 3
    seg_len_cells = 9
    a = math.sqrt(3.0) * ACC
    laxis = math.sqrt(3.0) * a
    seg_len = seg_len_cells * laxis           # ~3.3 nm
    gapx = 0.9                                 # gate gap between channels
    pitch = seg_len + gapx
    segments = []
    for s in range(nstage):
        P, segs, R, L = build_segment(s * pitch, ncirc=11, nz=seg_len_cells)
        segments.append((P, segs, R, s * pitch, s * pitch + L))
    x_start = segments[0][3]
    x_end = segments[-1][4]
    total_len = x_end - x_start

    # node levels: IN(1) then each NOT flips -> [1,0,1,0]
    node_x = [x_start - 0.3] + [seg[4] + gapx / 2 for seg in segments]
    base_levels = [1, 0, 1, 0]

    rng = np.random.default_rng(3)
    # electrons per channel (always conducting -> always flowing)
    e_phase = [rng.uniform(0, 1, 6) for _ in range(nstage)]
    e_ang = [rng.uniform(0, 2 * math.pi, 6) for _ in range(nstage)]

    fig = plt.figure(figsize=(7.6, 4.3), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111, projection="3d")

    def draw(i):
        t = i / args.frames
        ax.cla()
        ax.set_facecolor(BG)
        ax.set_axis_off()
        ax.set_box_aspect((3.4, 1.0, 1.0))

        # signal edge position travels across the circuit (slightly past OUT so
        # the final node flips before the camera pulls back)
        edge_x = x_start + (total_len + gapx) * min(1.0, t / 0.78)

        # CNT channels
        for (P, segs, R, xa, xb) in segments:
            ax.add_collection3d(Line3DCollection(segs, colors=BOND, linewidths=0.8))
            ax.scatter(P[:, 0], P[:, 1], P[:, 2], c=CARBON, s=12, depthshade=True, edgecolors="none")

        # gate electrodes (rings) at each inter-stage gap
        th = np.linspace(0, 2 * math.pi, 40)
        for s in range(nstage):
            gx = segments[s][4] + gapx / 2
            Rg = segments[s][2] * 1.5
            on = gx < edge_x
            ax.plot(gx * np.ones_like(th), Rg * np.cos(th), Rg * np.sin(th),
                    color=GATE, alpha=0.85 if on else 0.3, lw=2.6)

        # electrons flowing through every channel
        for s, (P, segs, R, xa, xb) in enumerate(segments):
            re = 0.55 * R
            xs, ys, zs = [], [], []
            for k in range(len(e_phase[s])):
                x = xa + ((e_phase[s][k] + t * 1.6) % 1.0) * (xb - xa)
                ang = e_ang[s][k] + 1.1 * x
                xs.append(x); ys.append(re * math.cos(ang)); zs.append(re * math.sin(ang))
            ax.scatter(xs, ys, zs, c=ELEC, s=95, depthshade=False,
                       edgecolors="white", linewidths=0.5, zorder=12)

        # bright propagating signal edge
        if edge_x < x_end + 0.1:
            ax.scatter([edge_x], [0], [0], c="white", s=240, edgecolors=HIGH,
                       linewidths=2.0, zorder=15)

        # camera pans to follow the edge, then pulls back to show the whole chain
        if t < 0.82:
            cx = edge_x
            half = 2.6
        else:
            cx = (x_start + x_end) / 2
            half = total_len / 2 + 1.0
        ax.view_init(elev=16 + 4 * math.sin(2 * math.pi * t), azim=-66 + 10 * math.sin(2 * math.pi * t))
        ax.set_xlim(cx - half, cx + half)
        ax.set_ylim(-1.6, 1.6)
        ax.set_zlim(-1.6, 1.6)

        # overlay: title + node level chips (flip as the edge passes)
        fig.text(0.5, 0.95, "Carbon-nanotube logic circuit — 3-stage CNTFET inverter chain",
                 color=FG, fontsize=12.5, ha="center", fontweight="bold")
        fig.text(0.5, 0.905, "electrons flow through the CNT channels · the signal edge flips each NOT stage",
                 color=MUTED, fontsize=8.4, ha="center", family="monospace")
        labels = ["IN", "NOT", "NOT", "OUT"]
        for k, nx in enumerate(node_x):
            passed = nx < edge_x
            lvl = base_levels[k] if passed else (1 - base_levels[k] if k > 0 else base_levels[k])
            # before the edge reaches a downstream node it holds its previous (pre-edge) level
            shown = base_levels[k] if (k == 0 or passed) else "·"
            col = HIGH if shown == 1 else (LOW if shown == 0 else MUTED)
            fx = 0.09 + 0.82 * (k / (len(node_x) - 1))
            fig.text(fx, 0.10, f"{labels[k]}\n{shown}", color=col, fontsize=10,
                     ha="center", va="center", family="monospace", fontweight="bold")
        return []

    total = args.frames + 8
    anim = FuncAnimation(fig, draw, frames=total, interval=1000 / args.fps, blit=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    anim.save(args.out, writer=PillowWriter(fps=args.fps))
    plt.close(fig)
    print(f"wrote {args.out}  ({nstage} stages, {args.frames} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
