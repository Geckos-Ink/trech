"""Evident 3D animation of carbon-nanotube electron transport vs chirality.

Three single-wall carbon nanotubes are built atom-by-atom by rolling a *real*
graphene honeycomb around each tube's own chiral vector C = n·a1 + m·a2 (C-C
bond length 0.142 nm), so the lattice **wrapping pattern** — not just the
diameter — differs between them. This is the structural "asymmetry" between
chiralities: an armchair tube shows rings of hexagons running around the
circumference, a zigzag tube shows them running along the axis.

The three tubes are the archetypes emitted by ``cnt_logic_gates.js``:

* TOP    — metallic armchair (5,5): θ=30°, no gap, electrons flow straight.
* MIDDLE — quasi-metallic zigzag (9,0): a small curvature gap slows electrons.
* BOTTOM — semiconducting zigzag (16,0): the band gap E_g blocks low-energy
  electrons, which pile up at the gap and reflect; only hot ones cross.

Electrons are **injected from a clearly-labelled source contact (the base)** at
the left end and drift toward the drain on the right, so it is obvious where the
particles come from and which way current flows. Which tube is metallic vs
semiconducting is the result of the tight-binding (n,m) model in
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
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_cnt_logic_gates"
OUT = Path(__file__).resolve().parent / "cnt_structure.gif"

BG = "#0e1014"
FG = "#e8e8e8"
MUTED = "#9aa3ad"
CARBON = "#aab4c2"
BOND = "#4a525f"
E_METAL = "#5fe3ff"   # cyan electrons (metallic, flowing)
E_QUASI = "#b9ff7f"   # green electrons (quasi-metallic, slowed)
E_SEMI = "#ffd27f"    # amber electrons (semiconducting)
GAP = "#ff6b6b"       # band-gap barrier
CONTACT = "#8fb7ff"   # metal contact / electrode
ACC = 0.142           # C-C bond length (nm)


def _optimize_gif(path: Path) -> None:
    """Re-encode against one shared palette to keep the file embeddable. The
    camera pans, so every pixel changes frame-to-frame (no inter-frame diff is
    possible); disposal=2 + a reduced shared palette is the safe win here."""
    try:
        from PIL import Image
    except Exception:
        return
    im = Image.open(path)
    duration = im.info.get("duration", 66)
    rgb = []
    try:
        while True:
            rgb.append(im.convert("RGB"))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    if not rgb:
        return
    master = rgb[len(rgb) // 2].quantize(colors=128, method=Image.MEDIANCUT)
    frames = [f.quantize(palette=master, dither=Image.NONE) for f in rgb]
    frames[0].save(path, save_all=True, append_images=frames[1:], loop=0,
                   duration=duration, optimize=True, disposal=2)


def load_emit(run_dir: Path, tag: str) -> Dict:
    path = run_dir / "trech_hook_emits.jsonl"
    if not path.exists():
        raise SystemExit(f"error: {path} not found; run cnt_logic_gates.js first")
    found = None
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("tag") == tag:
                found = rec.get("payload")
    if not found:
        raise SystemExit(f"error: no {tag} emit found in {path}")
    return found


def chirality_kind(n: int, m: int) -> str:
    if m == 0 or n == 0:
        return "zigzag"
    if n == m:
        return "armchair"
    return "chiral"


def build_tube_chiral(n: int, m: int, length_nm: float, y_off: float, z_off: float):
    """Roll a real graphene honeycomb around the chiral vector C = n·a1 + m·a2.

    Unlike a fixed rectangular cell rolled to an arbitrary radius, this places
    every atom at its true position on the (n,m) tube, so the *wrapping* of the
    hexagons (armchair rings vs zigzag rings vs a chiral helix) is faithful and
    visibly different between chiralities. The tube axis runs along +x.

    Returns atom xyz (N,3), bond segments, radius, length.
    """
    # Graphene lattice vectors (A/B two-atom basis).
    a1 = np.array([1.5 * ACC, math.sqrt(3.0) / 2.0 * ACC])
    a2 = np.array([1.5 * ACC, -math.sqrt(3.0) / 2.0 * ACC])
    basis_b = np.array([ACC, 0.0])

    ch = n * a1 + m * a2                # chiral (circumferential) vector
    circ = float(np.linalg.norm(ch))   # circumference
    u_hat = ch / circ                  # around the tube
    v_hat = np.array([-u_hat[1], u_hat[0]])  # along the axis
    radius = circ / (2.0 * math.pi)

    # Scan a generous graphene patch, then keep the fundamental domain
    # s in [0, circ) (one turn) x z in [0, length) (open axis). Because C is a
    # lattice vector the selection tiles the cylinder exactly with no seam gap.
    span = int(math.ceil((circ + length_nm) / (1.5 * ACC))) + 6
    idx = np.arange(-span, span + 1)
    ii, jj = np.meshgrid(idx, idx)
    ii = ii.ravel()
    jj = jj.ravel()
    bx = ii * a1[0] + jj * a2[0]
    by = ii * a1[1] + jj * a2[1]
    ax_all = np.concatenate([bx, bx + basis_b[0]])
    ay_all = np.concatenate([by, by + basis_b[1]])
    s = ax_all * u_hat[0] + ay_all * u_hat[1]
    z = ax_all * v_hat[0] + ay_all * v_hat[1]
    eps = 1e-6
    keep = (s >= -eps) & (s < circ - eps) & (z >= -eps) & (z < length_nm - eps)
    s = s[keep]
    z = z[keep]
    theta = 2.0 * math.pi * s / circ
    pts = np.column_stack([
        z,
        y_off + radius * np.cos(theta),
        z_off + radius * np.sin(theta),
    ])

    # Bonds by true 3D nearest-neighbour distance (handles the seam for free).
    segs: List = []
    rcut = ACC * 1.30
    nA = len(pts)
    for i in range(nA):
        d = pts[i + 1:] - pts[i]
        dist = np.sqrt((d * d).sum(axis=1))
        for k, dd in enumerate(dist):
            if dd < rcut:
                segs.append([pts[i], pts[i + 1 + k]])
    return pts, segs, radius, length_nm


class Electron:
    __slots__ = ("phase", "ang", "speed", "energetic")

    def __init__(self, rng, speed, energetic=False):
        self.phase = rng.uniform(0, 1)
        self.ang = rng.uniform(0, 2 * math.pi)
        self.speed = speed * rng.uniform(0.9, 1.1)
        self.energetic = energetic


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN_DIR)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--frames", type=int, default=90)
    ap.add_argument("--fps", type=int, default=15)
    args = ap.parse_args()

    summary = load_emit(args.run, "cnt_gates_summary")
    metal_dev = summary["metallic_device"]
    quasi_dev = summary.get("quasi_metallic_device")
    semi_dev = summary["working_device"]

    rng = np.random.default_rng(7)
    length = 2.9          # nm, same length for all so wrapping is comparable
    sep = 1.5             # vertical spacing between tube axes

    # Build faithful tubes from each device's own chirality.
    Pm, Sm, Rm, L = build_tube_chiral(int(round(metal_dev["n"])), int(round(metal_dev["m"])),
                                      length, y_off=0.0, z_off=+sep)
    if quasi_dev:
        Pq, Sq, Rq, _ = build_tube_chiral(int(round(quasi_dev["n"])), int(round(quasi_dev["m"])),
                                          length, y_off=0.0, z_off=0.0)
    Ps, Ss, Rs, _ = build_tube_chiral(int(round(semi_dev["n"])), int(round(semi_dev["m"])),
                                      length, y_off=0.0, z_off=-sep)

    e_metal = [Electron(rng, 0.026, energetic=True) for _ in range(7)]
    e_quasi = [Electron(rng, 0.020, energetic=(k % 3 == 0)) for k in range(6)] if quasi_dev else []
    e_semi = [Electron(rng, 0.024, energetic=(k % 5 == 0)) for k in range(7)]

    # Band-gap barrier bands (axial position where low-energy e- reflect).
    semi_gap0, semi_gap1 = 0.50 * L, 0.58 * L
    quasi_gap0, quasi_gap1 = 0.52 * L, 0.56 * L
    x_source = -0.32      # electron source contact (the "base")
    x_drain = L + 0.32    # collecting drain contact

    fig = plt.figure(figsize=(7.8, 5.0), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111, projection="3d")

    def contact_plate(x: float, color: str, alpha: float):
        """A translucent electrode plate spanning all three tubes at axial x."""
        y0, y1, z0, z1 = -0.95, 0.95, -sep - 0.95, sep + 0.95
        verts = [[(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]]
        plate = Poly3DCollection(verts, facecolors=color, edgecolors=color,
                                 alpha=alpha, linewidths=1.0)
        ax.add_collection3d(plate)

    def draw(i):
        t = i / args.frames
        fig.texts.clear()
        ax.cla()
        ax.set_facecolor(BG)
        ax.set_axis_off()
        ax.set_box_aspect((3.0, 1.0, 1.7))

        # --- electrode contacts (the base / source on the left, drain right) ---
        contact_plate(x_source, CONTACT, 0.18)
        contact_plate(x_drain, "#6f7787", 0.12)

        # --- carbon lattices (bonds thick enough that the armchair-vs-zigzag
        #     hexagon wrapping is legible, not just the diameter) ---
        ax.add_collection3d(Line3DCollection(Sm, colors=BOND, linewidths=1.4))
        ax.add_collection3d(Line3DCollection(Ss, colors=BOND, linewidths=1.4))
        ax.scatter(Pm[:, 0], Pm[:, 1], Pm[:, 2], c=CARBON, s=20, depthshade=True, edgecolors="none")
        ax.scatter(Ps[:, 0], Ps[:, 1], Ps[:, 2], c=CARBON, s=20, depthshade=True, edgecolors="none")
        if quasi_dev:
            ax.add_collection3d(Line3DCollection(Sq, colors=BOND, linewidths=1.4))
            ax.scatter(Pq[:, 0], Pq[:, 1], Pq[:, 2], c=CARBON, s=20, depthshade=True, edgecolors="none")

        # --- band-gap barriers (glowing red rings) ---
        th = np.linspace(0, 2 * math.pi, 48)
        for gx in np.linspace(semi_gap0, semi_gap1, 5):
            ax.plot(gx * np.ones_like(th), Rs * np.cos(th), -sep + Rs * np.sin(th),
                    color=GAP, alpha=0.32, lw=2.2)
        if quasi_dev:
            for gx in np.linspace(quasi_gap0, quasi_gap1, 3):
                ax.plot(gx * np.ones_like(th), Rq * np.cos(th), 0.0 + Rq * np.sin(th),
                        color=GAP, alpha=0.18, lw=1.6)

        # --- current channel guides + injection arrows from the source ---
        ax.plot([x_source, x_drain], [0, 0], [sep, sep], color=E_METAL, alpha=0.22, lw=3.0)
        if quasi_dev:
            ax.plot([x_source, x_drain], [0, 0], [0, 0], color=E_QUASI, alpha=0.18, lw=2.4)
        ax.plot([x_source, semi_gap0], [0, 0], [-sep, -sep], color=E_SEMI, alpha=0.26, lw=3.0)

        def draw_es(elist, R, zo, color, gap0, block):
            ex, ey, ez, ec, es = [], [], [], [], []
            re = 0.55 * R
            for e in elist:
                # electrons are injected at the source and drift toward the drain
                x = x_source + ((e.phase + t * e.speed * 42.0) % 1.0) * (x_drain - x_source)
                blocked = False
                if block and not e.energetic and x > gap0:
                    x = gap0 - 0.05 * L * (0.5 + 0.5 * math.sin(t * 13 + e.phase * 7))
                    blocked = True
                ang = e.ang + 1.1 * x
                ex.append(x)
                ey.append(re * math.cos(ang))
                ez.append(zo + re * math.sin(ang))
                ec.append(GAP if blocked else color)
                es.append(150 if blocked else 115)
            ax.scatter(ex, ey, ez, c=ec, s=es, depthshade=False,
                       edgecolors="white", linewidths=0.6, zorder=12)

        draw_es(e_metal, Rm, +sep, E_METAL, semi_gap0, block=False)
        if quasi_dev:
            draw_es(e_quasi, Rq, 0.0, E_QUASI, quasi_gap0, block=True)
        draw_es(e_semi, Rs, -sep, E_SEMI, semi_gap0, block=True)

        # gentle, readable camera (small azimuth sweep, no fast tumbling);
        # a modest elevation lets the rolled hexagon wrapping stay visible
        ax.view_init(elev=20 + 3 * math.sin(2 * math.pi * t),
                     azim=-74 + 14 * math.sin(2 * math.pi * t))
        ax.set_xlim(x_source - 0.3, x_drain + 0.3)
        ax.set_ylim(-2.9, 2.9)
        ax.set_zlim(-2.9, 2.9)

        # --- titles ---
        fig.text(0.5, 0.955, "Carbon nanotubes — structure (chirality) sets electron transport",
                 color=FG, fontsize=13.0, ha="center", fontweight="bold")
        fig.text(0.5, 0.915,
                 "real rolled-graphene lattice · a_cc = 0.142 nm · same wrapping asymmetry, not just diameter",
                 color=MUTED, fontsize=8.4, ha="center", family="monospace")

        # --- source / drain callouts (where the particles come from) ---
        fig.text(0.055, 0.50, "e⁻ SOURCE\n(the base /\ncathode)\n→ inject", color=CONTACT,
                 fontsize=8.6, ha="left", family="monospace", va="center", fontweight="bold")
        fig.text(0.90, 0.50, "DRAIN\n(anode)\ncollect →", color="#c3cad6",
                 fontsize=8.0, ha="left", family="monospace", va="center")

        # --- per-tube status cards ---
        mk = chirality_kind(int(metal_dev["n"]), int(metal_dev["m"]))
        fig.text(0.155, 0.80,
                 f"metallic {mk} ({metal_dev['n']},{metal_dev['m']})\n"
                 f"θ={metal_dev.get('chiral_angle_deg', 0):.0f}°  d={metal_dev['diameter_nm']:.2f} nm\n"
                 f"(n-m) mod 3 = 0 · no gap\nelectrons flow through",
                 color=E_METAL, fontsize=8.6, ha="left", family="monospace", va="top")
        if quasi_dev:
            qk = chirality_kind(int(quasi_dev["n"]), int(quasi_dev["m"]))
            fig.text(0.155, 0.505,
                     f"quasi-metallic {qk} ({quasi_dev['n']},{quasi_dev['m']})\n"
                     f"θ={quasi_dev.get('chiral_angle_deg', 0):.0f}°  d={quasi_dev['diameter_nm']:.2f} nm\n"
                     f"tiny curvature gap {quasi_dev['band_gap_eV']*1000:.0f} meV\nmost e- pass, some slow",
                     color=E_QUASI, fontsize=8.6, ha="left", family="monospace", va="top")
        sk = chirality_kind(int(semi_dev["n"]), int(semi_dev["m"]))
        fig.text(0.155, 0.235,
                 f"semiconducting {sk} ({semi_dev['n']},{semi_dev['m']})\n"
                 f"θ={semi_dev.get('chiral_angle_deg', 0):.0f}°  d={semi_dev['diameter_nm']:.2f} nm\n"
                 f"E_g={semi_dev['band_gap_eV']:.2f} eV · red rings = gap\nlow-energy e- reflect",
                 color=E_SEMI, fontsize=8.6, ha="left", family="monospace", va="top")
        return []

    total = args.frames + 6
    anim = FuncAnimation(fig, draw, frames=total, interval=1000 / args.fps, blit=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    anim.save(args.out, writer=PillowWriter(fps=args.fps))
    plt.close(fig)
    _optimize_gif(args.out)
    natoms = len(Pm) + len(Ps) + (len(Pq) if quasi_dev else 0)
    print(f"wrote {args.out}  ({natoms} atoms, {args.frames} frames, "
          f"metal=({metal_dev['n']},{metal_dev['m']}) "
          f"{'quasi=(' + str(quasi_dev['n']) + ',' + str(quasi_dev['m']) + ') ' if quasi_dev else ''}"
          f"semi=({semi_dev['n']},{semi_dev['m']}) L={length:.2f}nm)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
