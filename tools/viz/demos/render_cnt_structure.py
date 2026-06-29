"""Evident 3D animation of carbon-nanotube electron transport vs chirality.

Two single-wall carbon nanotubes are built atom-by-atom from a rolled graphene
honeycomb (correct C-C bond length 0.142 nm and realistic diameter) and laid out
horizontally; electrons stream through them along the axis while the camera
orbits so the rolled hexagonal lattice is clearly visible:

* TOP    — a metallic tube: electrons flow straight through (no gap).
* BOTTOM — a semiconducting tube: the band gap E_g blocks low-energy electrons,
  which pile up at the gap and are reflected; only the occasional energetic one
  gets through.

The honeycomb mesh is a faithful rolled-graphene lattice; which tube is metallic
vs semiconducting is the result of the tight-binding (n,m) model in
``cnt_band_structure.js`` (metallic iff (n-m) mod 3 == 0). Honest scope, same as
the rest of the CNT track: Geant4 transports electrons through the tube geometry
but does not compute the band structure -- the metallic/semiconducting electron
behaviour shown here is the hook-layer physics, visualised.

Run::

    cd tools/viz
    source .venv/bin/activate
    python demos/render_cnt_structure.py

Output: ``tools/viz/demos/cnt_structure.gif``.
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

OUT = Path(__file__).resolve().parent / "cnt_structure.gif"

BG = "#0e1014"
FG = "#e8e8e8"
CARBON = "#aab4c2"
BOND = "#4a525f"
E_METAL = "#5fe3ff"   # cyan electrons (metallic, flowing)
E_SEMI = "#ffd27f"    # amber electrons (semiconducting)
GAP = "#ff6b6b"       # band-gap barrier
ACC = 0.142           # C-C bond length (nm)


def build_tube(ncirc: int, nz: int, y_off: float, z_off: float):
    """Roll a graphene honeycomb (4-atom rectangular cell) into a tube whose axis
    runs along x. ncirc sets the circumference (=> diameter), nz the length.
    Returns atom xyz (N,3), bond segments, radius, length.
    """
    a = math.sqrt(3.0) * ACC          # graphene lattice constant 0.246 nm
    lx = a                            # zigzag period (around circumference)
    laxis = math.sqrt(3.0) * a        # armchair period (along the tube axis)
    cell = [(0.0, 0.0), (lx / 2, laxis / 6), (lx / 2, laxis / 2), (0.0, laxis * 2 / 3)]
    width = ncirc * lx
    radius = width / (2.0 * math.pi)
    pts: List[List[float]] = []
    for i in range(ncirc):
        for j in range(nz):
            for (cx, caxis) in cell:
                around = i * lx + cx
                x = j * laxis + caxis
                theta = 2.0 * math.pi * around / width
                pts.append([x, y_off + radius * math.cos(theta),
                            z_off + radius * math.sin(theta)])
    P = np.array(pts)
    length = nz * laxis
    segs = []
    n = len(P)
    rcut = ACC * 1.25
    for i in range(n):
        d = P[i + 1:] - P[i]
        dist = np.sqrt((d * d).sum(axis=1))
        for k, dd in enumerate(dist):
            if dd < rcut:
                segs.append([P[i], P[i + 1 + k]])
    return P, segs, radius, length


class Electron:
    __slots__ = ("phase", "ang", "speed", "energetic")

    def __init__(self, rng, speed, energetic=False):
        self.phase = rng.uniform(0, 1)
        self.ang = rng.uniform(0, 2 * math.pi)
        self.speed = speed * rng.uniform(0.85, 1.15)
        self.energetic = energetic


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--frames", type=int, default=70)
    ap.add_argument("--fps", type=int, default=15)
    args = ap.parse_args()

    rng = np.random.default_rng(7)
    sep = 1.35
    Pm, Sm, Rm, L = build_tube(ncirc=10, nz=11, y_off=0.0, z_off=+sep)   # metallic
    Ps, Ss, Rs, _ = build_tube(ncirc=13, nz=11, y_off=0.0, z_off=-sep)   # semiconducting
    e_metal = [Electron(rng, 0.026, energetic=True) for _ in range(8)]
    e_semi = [Electron(rng, 0.024, energetic=(k % 5 == 0)) for k in range(8)]
    gapx0, gapx1 = 0.47 * L, 0.55 * L     # band-gap barrier band (axial)

    fig = plt.figure(figsize=(7.4, 4.4), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111, projection="3d")

    def draw(i):
        t = i / args.frames
        ax.cla()
        ax.set_facecolor(BG)
        ax.set_axis_off()
        ax.set_box_aspect((3.0, 1.0, 1.2))

        ax.add_collection3d(Line3DCollection(Sm, colors=BOND, linewidths=0.9))
        ax.add_collection3d(Line3DCollection(Ss, colors=BOND, linewidths=0.9))
        ax.scatter(Pm[:, 0], Pm[:, 1], Pm[:, 2], c=CARBON, s=16, depthshade=True, edgecolors="none")
        ax.scatter(Ps[:, 0], Ps[:, 1], Ps[:, 2], c=CARBON, s=16, depthshade=True, edgecolors="none")

        # band-gap barrier disk on the semiconducting tube (glowing red rings)
        th = np.linspace(0, 2 * math.pi, 48)
        for gx in np.linspace(gapx0, gapx1, 5):
            ax.plot(gx * np.ones_like(th), Rs * np.cos(th), -sep + Rs * np.sin(th),
                    color=GAP, alpha=0.30, lw=2.2)

        def draw_es(elist, R, zo, color, allow):
            ex, ey, ez, ec, es = [], [], [], [], []
            re = 0.55 * R
            for e in elist:
                x = ((e.phase + t * e.speed * 42.0) % 1.0) * L
                blocked = False
                if not allow and not e.energetic and x > gapx0:
                    x = gapx0 - 0.05 * L * (0.5 + 0.5 * math.sin(t * 13 + e.phase * 7))
                    blocked = True
                ang = e.ang + 1.1 * x
                ex.append(x)
                ey.append(re * math.cos(ang))
                ez.append(zo + re * math.sin(ang))
                ec.append(GAP if blocked else color)
                es.append(150 if blocked else 120)
            ax.scatter(ex, ey, ez, c=ec, s=es, depthshade=False,
                       edgecolors="white", linewidths=0.6, zorder=12)
        draw_es(e_metal, Rm, +sep, E_METAL, allow=True)
        draw_es(e_semi, Rs, -sep, E_SEMI, allow=False)

        # gentle camera orbit (oscillate azimuth + slight elevation breathing)
        ax.view_init(elev=14 + 6 * math.sin(2 * math.pi * t),
                     azim=-72 + 34 * math.sin(2 * math.pi * t))
        ax.set_xlim(-0.4, L + 0.4)
        ax.set_ylim(-2.6, 2.6)
        ax.set_zlim(-2.6, 2.6)

        fig.text(0.5, 0.95, "Carbon nanotubes — electron transport set by chirality",
                 color=FG, fontsize=13.5, ha="center", fontweight="bold")
        fig.text(0.5, 0.90, "rolled graphene honeycomb · a_cc = 0.142 nm · electrons flow along the axis",
                 color="#9aa3ad", fontsize=8.6, ha="center", family="monospace")
        fig.text(0.13, 0.74, "metallic\n(n−m) mod 3 = 0\nelectrons flow",
                 color=E_METAL, fontsize=9.5, ha="left", family="monospace", va="top")
        fig.text(0.13, 0.30, "semiconducting\nE_g ≠ 0\nblocked at the gap",
                 color=E_SEMI, fontsize=9.5, ha="left", family="monospace", va="top")
        return []

    total = args.frames + 5
    anim = FuncAnimation(fig, draw, frames=total, interval=1000 / args.fps, blit=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    anim.save(args.out, writer=PillowWriter(fps=args.fps))
    plt.close(fig)
    print(f"wrote {args.out}  ({len(Pm)+len(Ps)} atoms, {args.frames} frames, "
          f"d_metal={2*Rm:.2f}nm d_semi={2*Rs:.2f}nm L={L:.2f}nm)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
