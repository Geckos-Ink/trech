"""Evident physics animations for the essential test-suite scenarios that did not
already have one (the CNT tubes/circuit, glass-of-water, efflux, bulk-water and
osmotic scenarios have their own dedicated renderers).

Each function builds a short 2D physics animation that *shows what the scenario
simulates* -- a proton stopping at its Bragg peak, a photon beam attenuating in a
slab, a water molecule vibrating, etc. -- and overlays the live validated status
read from ``docs/validation_report.json`` (status badge + summary line), so the
GIF doubles as a "current status" view. The numbers are pulled from the report so
the animation stays faithful to the latest run.

Run::

    cd tools/viz
    source .venv/bin/activate
    python demos/render_physics_anims.py            # all
    python demos/render_physics_anims.py csda beer  # a subset (by key)

Output: ``tools/viz/demos/<key>.gif``.
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
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT = REPO_ROOT / "docs" / "validation_report.json"
OUT_DIR = Path(__file__).resolve().parent

BG = "#0e1014"
PANEL = "#1b1f26"
FG = "#e8e8e8"
MUTED = "#9aa3ad"
GRID = "#555c66"
GREEN = "#7fdc7f"
AMBER = "#ffb347"
RED = "#ff6b6b"
BLUE = "#6fb7ff"
CYAN = "#5fe3ff"
VIOLET = "#c89bff"
WATER = "#1f3a5f"
STATUS_C = {"pass": GREEN, "info": AMBER, "fail": RED, "skip": MUTED, "error": RED}


def load_cases() -> Dict[str, Dict]:
    data = json.loads(REPORT.read_text())
    return {c["name"]: c for c in data["results"]}


def status_of(cases: Dict, names: List[str]) -> str:
    sts = [cases[n]["status"] for n in names if n in cases]
    if not sts:
        return "skip"
    if "fail" in sts or "error" in sts:
        return "fail"
    return "pass" if any(s == "pass" for s in sts) else sts[0]


def overlay(fig, title: str, subtitle: str, cases: Dict, case_names: List[str]) -> None:
    """Static title + status badge + footer summary (added once, not per frame)."""
    st = status_of(cases, case_names)
    c = STATUS_C.get(st, MUTED)
    # left-aligned title/subtitle so they never run under the top-right badge
    fig.text(0.035, 0.955, title, color=FG, fontsize=12.0, ha="left", fontweight="bold")
    fig.text(0.035, 0.915, subtitle, color=MUTED, fontsize=8.2, ha="left", family="monospace")
    # badge (top-right corner)
    ax = fig.add_axes([0.865, 0.925, 0.11, 0.058]); ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0.05, 0.1), 0.9, 0.8, boxstyle="round,pad=0.06",
                                facecolor=BG, edgecolor=c, linewidth=1.6))
    ax.text(0.5, 0.5, {"pass": "PASS", "info": "INFO", "fail": "FAIL"}.get(st, st.upper()),
            color=c, fontsize=10, fontweight="bold", ha="center", va="center", family="monospace")
    primary = case_names[0]
    summary = cases.get(primary, {}).get("summary", "")
    if len(summary) > 104:
        summary = summary[:102] + "…"
    fig.text(0.035, 0.032, "validated by  " + "  ·  ".join(case_names), color=FG,
             fontsize=7.6, family="monospace")
    fig.text(0.035, 0.010, summary, color=MUTED, fontsize=7.0, family="monospace")


def save(anim, key: str, fps: int = 18) -> None:
    out = OUT_DIR / f"{key}.gif"
    anim.save(out, writer=PillowWriter(fps=fps))
    print(f"wrote {out.relative_to(REPO_ROOT)}")


def _phys_ax(fig, rect=(0.09, 0.20, 0.86, 0.62)):
    ax = fig.add_axes(rect)
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    return ax


# --------------------------------------------------------------------------- #
# 1. CSDA range — a 20 MeV proton stops at its Bragg peak in water
# --------------------------------------------------------------------------- #
def anim_csda(cases: Dict, frames=64, fps=18):
    m = cases["analytic_csda_range_cross_check"]["measured"][0]
    R = float(m["mean_track_length_mm_measured"])          # ~4.266 mm
    R_pred = float(m["csda_range_mm_derived"])              # ~4.282 mm
    fig = plt.figure(figsize=(7.2, 4.2), dpi=100, facecolor=BG)
    overlay(fig, "CSDA range — 20 MeV proton stops at its Bragg peak (water)",
            "derived range = ∫dE/(dE/dx) from Geant4 stopping power  vs  measured track length",
            cases, ["analytic_csda_range_cross_check"])
    ax = _phys_ax(fig)
    xmax = R * 1.25
    # Bragg depth-dose profile (approximate): rises then sharp fall at R
    xs = np.linspace(0, xmax, 400)
    with np.errstate(divide="ignore"):
        dose = np.where(xs < R, 1.0 / np.power(np.clip(R - xs, 1e-3, None), 0.78), 0.0)
    dose = np.clip(dose, 0, np.percentile(dose[xs < R * 0.999], 99.3))
    dose /= dose.max()

    def draw(i):
        t = min(1.0, i / (frames - 6))
        ax.cla()
        ax.set_facecolor(BG)
        ax.set_xlim(0, xmax); ax.set_ylim(0, 1.25)
        ax.set_xlabel("depth in water  [mm]", color=FG, fontsize=9.5)
        ax.set_ylabel("relative dose  dE/dx", color=FG, fontsize=9.5)
        ax.tick_params(colors=MUTED, labelsize=8)
        for s in ax.spines.values():
            s.set_color(GRID)
        ax.add_patch(Rectangle((0, 0), xmax, 1.25, color=WATER, alpha=0.25, zorder=0))
        p = R * (1 - (1 - t) ** 2)                          # proton depth (decelerating)
        mask = xs <= p
        ax.fill_between(xs[mask], dose[mask], color=AMBER, alpha=0.7, zorder=2)
        ax.plot(xs[mask], dose[mask], color=AMBER, lw=1.6, zorder=3)
        ax.plot([p], [np.interp(p, xs, dose) if p < R else 0], "o", color="white",
                ms=11, markeredgecolor=RED, markeredgewidth=2, zorder=5)
        ax.plot([0, p], [0.04, 0.04], color=CYAN, lw=2.5, alpha=0.8, zorder=4)  # track
        ax.axvline(R_pred, color=GREEN, ls="--", lw=1.4)
        ax.text(R_pred, 1.13, f"Geant4 CSDA range {R_pred:.3f} mm", color=GREEN,
                fontsize=8.6, ha="right", family="monospace")
        ax.text(0.02 * xmax, 1.13, f"proton depth {p:.2f} mm", color=CYAN,
                fontsize=8.6, family="monospace")
        if t > 0.9:
            ax.text(R, 0.5, f"measured track {R:.3f} mm\nΔ {abs(R-R_pred)/R_pred*100:.2f}%",
                    color=FG, fontsize=8.6, ha="center", family="monospace",
                    bbox=dict(facecolor=PANEL, edgecolor=GREEN, boxstyle="round,pad=0.4"))
        return []
    save(FuncAnimation(fig, draw, frames=frames + 8, interval=1000/fps), "csda_bragg", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 2. Beer-Lambert — photon beam attenuating in a water slab
# --------------------------------------------------------------------------- #
def anim_beer(cases: Dict, frames=70, fps=18):
    c = cases["analytic_beer_lambert_cross_check"]["measured"][0]
    T_meas = float(c["geant4_measured"]); T_clas = float(c["classical_predicted"])
    slab = 50.0
    mu = -math.log(T_clas) / slab
    rng = np.random.default_rng(5)
    n = 80
    y = np.linspace(0.08, 0.92, n)
    # each photon's interaction depth ~ exp(-mu x); inf => uncollided (passes)
    u = rng.uniform(size=n)
    xint = -np.log(u) / mu
    passes = xint >= slab
    fig = plt.figure(figsize=(7.2, 4.2), dpi=100, facecolor=BG)
    overlay(fig, "Beer–Lambert attenuation — 100 keV γ through 50 mm water",
            "T = exp(−μx), μ from Geant4 cross-sections  vs  measured uncollided fraction",
            cases, ["analytic_beer_lambert_cross_check"])
    ax = _phys_ax(fig)

    def draw(i):
        t = min(1.0, i / (frames - 8))
        ax.cla(); ax.set_facecolor(BG)
        ax.set_xlim(-8, slab + 22); ax.set_ylim(0, 1)
        ax.set_axis_off()
        ax.add_patch(Rectangle((0, 0), slab, 1, color=WATER, alpha=0.30))
        ax.text(slab / 2, 0.97, "water slab (50 mm)", color=BLUE, fontsize=8.5, ha="center")
        front = t * (slab + 22) - 8
        survived = 0
        for k in range(n):
            stop = min(xint[k], slab) if not passes[k] else slab + 20
            xh = min(front, stop)
            if xh <= -8:
                continue
            col = CYAN if (passes[k] or front < xint[k]) else RED
            ax.plot([-8, xh], [y[k], y[k]], color=col, lw=1.0,
                    alpha=0.85 if col == CYAN else 0.5)
            if not passes[k] and front >= xint[k]:
                ax.plot([xint[k]], [y[k]], "x", color=RED, ms=5, mew=1.2)
            if passes[k] and front >= slab:
                survived += 1
        ax.text(-7, 0.02, "γ beam →", color=CYAN, fontsize=9, family="monospace")
        frac = survived / n
        ax.text(slab + 21, 0.5, f"transmitted\n(uncollided)\n{frac*100:.0f}%",
                color=GREEN, fontsize=9, ha="right", family="monospace", va="center")
        ax.text(slab / 2, 0.03,
                f"classical T = {T_clas:.4f}   Geant4 T = {T_meas:.4f}   μ = {mu:.4f}/mm",
                color=FG, fontsize=8.3, ha="center", family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames + 10, interval=1000/fps), "beer_lambert", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 3. Nuclear cycle — N-14 + n -> C-14 + p ; C-14 -> N-14 + e- + nu_bar
# --------------------------------------------------------------------------- #
def anim_nuclear(cases: Dict, frames=90, fps=18):
    q = float(cases["nuclear_cycle_q_value_closure"]["measured"])
    fig = plt.figure(figsize=(7.2, 4.2), dpi=100, facecolor=BG)
    overlay(fig, "Nuclear cycle  N-14 ↔ C-14  (Q-values from Geant4 masses)",
            "forward: ¹⁴N + n → ¹⁴C + p     back: ¹⁴C → ¹⁴N + e⁻ + ν̄",
            cases, ["nuclear_cycle_conservation", "nuclear_cycle_q_value_closure"])
    ax = fig.add_axes([0.04, 0.10, 0.92, 0.74]); ax.set_axis_off()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    def nucleus(x, y, r, col, label):
        ax.add_patch(Circle((x, y), r, color=col, ec="white", lw=1.2, zorder=4))
        ax.text(x, y, label, color="white", fontsize=9, ha="center", va="center",
                fontweight="bold", zorder=5)

    def draw(i):
        t = i / frames
        ax.cla(); ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ph = (t * 2) % 2  # two phases: forward then beta decay
        if ph < 1:  # forward capture
            s = ph
            nucleus(0.30, 0.6, 0.10, BLUE, "¹⁴N")
            nx = 0.05 + 0.25 * min(1, s * 2)  # neutron flying in
            if s < 0.5:
                ax.plot([nx], [0.6], "o", color=MUTED, ms=10)
                ax.text(nx, 0.72, "n", color=MUTED, fontsize=8, ha="center")
            else:
                nucleus(0.30, 0.6, 0.105, "#2a7", "¹⁴C")
                px = 0.40 + 0.45 * (s - 0.5) * 2  # proton ejected
                ax.plot([px], [0.6 + 0.08 * (s - 0.5)], "o", color=RED, ms=9)
                ax.text(px, 0.72, "p", color=RED, fontsize=8, ha="center")
            ax.text(0.5, 0.9, "forward:  ¹⁴N + n → ¹⁴C + p   (Q_f)", color=GREEN,
                    fontsize=9.5, ha="center", family="monospace")
        else:  # beta decay
            s = ph - 1
            nucleus(0.30, 0.6, 0.105, "#2a7", "¹⁴C" if s < 0.5 else "¹⁴N")
            if s >= 0.4:
                ex = 0.40 + 0.5 * (s - 0.4) / 0.6
                ax.plot([ex], [0.6 + 0.12 * (s - 0.4)], "o", color=CYAN, ms=7)
                ax.text(ex, 0.74, "e⁻", color=CYAN, fontsize=8, ha="center")
                ax.plot([ex], [0.6 - 0.12 * (s - 0.4)], "o", color=VIOLET, ms=5)
                ax.text(ex, 0.46, "ν̄", color=VIOLET, fontsize=8, ha="center")
            ax.text(0.5, 0.9, "back:  ¹⁴C → ¹⁴N + e⁻ + ν̄   (Q_b)", color=AMBER,
                    fontsize=9.5, ha="center", family="monospace")
        # cycle arrow
        ax.annotate("", xy=(0.62, 0.28), xytext=(0.30, 0.28),
                    arrowprops=dict(arrowstyle="->", color=GRID, lw=1.4))
        ax.annotate("", xy=(0.30, 0.20), xytext=(0.62, 0.20),
                    arrowprops=dict(arrowstyle="->", color=GRID, lw=1.4))
        ax.text(0.5, 0.10, f"baryon + charge conserved · |Q_f + Q_b| = {q:.3f} MeV (tol 1 MeV)",
                color=FG, fontsize=8.6, ha="center", family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames, interval=1000/fps), "nuclear_cycle", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 4. H2O molecule — bonds vibrating around equilibrium
# --------------------------------------------------------------------------- #
def anim_molecule(cases: Dict, frames=72, fps=18):
    m = cases["h2o_molecule_bonds_stable"]["measured"]
    r0 = float(m["mean_bond_A"]); rmax = float(m["max_bond_A"]); ang0 = float(m["mean_angle_deg"])
    amp = (rmax - r0)
    fig = plt.figure(figsize=(6.4, 4.4), dpi=100, facecolor=BG)
    overlay(fig, "H₂O molecule — bonds vibrate but stay bound",
            "classical flexible-water MD (Geant4 per-tick clock) · O–H ≈ 0.957 Å, ∠ ≈ 104.5°",
            cases, ["h2o_molecule_bonds_stable"])
    ax = fig.add_axes([0.06, 0.12, 0.88, 0.72]); ax.set_axis_off()
    ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.2, 1.6); ax.set_aspect("equal")

    def draw(i):
        t = i / frames
        ax.cla(); ax.set_axis_off(); ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.2, 1.6)
        ax.set_aspect("equal")
        # symmetric stretch + bend
        r1 = r0 + amp * math.sin(2 * math.pi * t * 3)
        r2 = r0 + amp * math.sin(2 * math.pi * t * 3 + 0.6)
        ang = ang0 + 6 * math.sin(2 * math.pi * t * 2)
        ha = math.radians(ang / 2)
        h1 = (-r1 * math.sin(ha), -r1 * math.cos(ha) + 0.3)
        h2 = (r2 * math.sin(ha), -r2 * math.cos(ha) + 0.3)
        O = (0, 0.3)
        for H, r in ((h1, r1), (h2, r2)):
            col = AMBER if r > r0 + 0.6 * amp else GRID
            ax.plot([O[0], H[0]], [O[1], H[1]], color=col, lw=3.2, zorder=2)
        ax.add_patch(Circle(O, 0.30, color=RED, ec="white", lw=1.2, zorder=3))
        ax.text(O[0], O[1], "O", color="white", ha="center", va="center", fontweight="bold", zorder=4)
        for H in (h1, h2):
            ax.add_patch(Circle(H, 0.17, color="#dfe6ee", ec="white", lw=1.0, zorder=3))
            ax.text(H[0], H[1], "H", color="#222", ha="center", va="center", fontsize=8, zorder=4)
        ax.text(0, 1.45, f"O–H = {r1:.3f} Å    ∠HOH = {ang:.1f}°", color=FG,
                fontsize=10, ha="center", family="monospace")
        ax.text(0, -1.05, f"energy drift {float(m['energy_drift_fraction'])*100:.2f}% over the run — stays bound",
                color=GREEN, fontsize=8.6, ha="center", family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames, interval=1000/fps), "h2o_molecule", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 5. Pascal's principle — rigid vs deformable wall
# --------------------------------------------------------------------------- #
def anim_pascal(cases: Dict, frames=72, fps=18):
    m = cases["pascal_principle_holds"]["measured"]
    rigid = float(m["rigid_wall_displacement"]); deform = float(m["deformable_wall_displacement"])
    fig = plt.figure(figsize=(7.2, 4.2), dpi=100, facecolor=BG)
    overlay(fig, "Pascal's principle — pressure transmitted vs wall stiffness",
            "rigid wall holds (tiny displacement) · Hookean-deformable wall bulges",
            cases, ["pascal_principle_holds"])
    ax = fig.add_axes([0.06, 0.12, 0.88, 0.72]); ax.set_axis_off()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    def vessel(x0, w, bulge, label, col):
        ax.add_patch(Rectangle((x0, 0.18), w, 0.5, facecolor=WATER, alpha=0.5,
                               edgecolor=col, lw=2))
        # right wall displaces by `bulge` (normalised)
        ax.add_patch(Rectangle((x0 + w, 0.18), 0.012 + bulge, 0.5, facecolor=col, alpha=0.9))
        ax.text(x0 + w / 2, 0.10, label, color=col, fontsize=8.6, ha="center", family="monospace")

    def draw(i):
        t = min(1.0, i / (frames - 8))
        ax.cla(); ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        press = math.sin(min(1, t) * math.pi / 2)          # piston push 0..1
        # piston
        py = 0.78 - 0.12 * press
        ax.add_patch(Rectangle((0.10, py), 0.18, 0.05, facecolor=MUTED))
        ax.annotate("", xy=(0.19, py), xytext=(0.19, py + 0.12),
                    arrowprops=dict(arrowstyle="->", color=RED, lw=2.4))
        ax.text(0.19, py + 0.15, "F", color=RED, fontsize=11, ha="center")
        vessel(0.10, 0.30, 0.004 * press, "rigid wall", GREEN)
        vessel(0.58, 0.30, 0.14 * press, "deformable wall", AMBER)
        ax.text(0.5, 0.03,
                f"rigid disp {rigid:.1e}   <<   deformable disp {deform:.2f}   (x{deform/max(rigid,1e-12):.0f})",
                color=FG, fontsize=8.4, ha="center", family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames + 10, interval=1000/fps), "pascal_press", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 6. Electrolysis + inverse combustion — H2 at cathodes, O2 at collector (2:1)
# --------------------------------------------------------------------------- #
def anim_electrolysis(cases: Dict, frames=84, fps=18):
    fig = plt.figure(figsize=(7.0, 4.4), dpi=100, facecolor=BG)
    overlay(fig, "Electrolysis + inverse combustion — 2 H₂O → 2 H₂ + O₂ → 2 H₂O",
            "Geant4 event drive + EM anchors scale the rates · H₂:O₂ = 2:1 · atoms conserved",
            cases, ["h2o_electrolysis_combustion_cycle"])
    ax = fig.add_axes([0.06, 0.12, 0.88, 0.74]); ax.set_axis_off()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    rng = np.random.default_rng(11)
    NH, NO = 18, 9
    hphase = rng.uniform(0, 1, NH); hx = rng.choice([0.16, 0.84], NH); hxoff = rng.uniform(-0.04, 0.04, NH)
    ophase = rng.uniform(0, 1, NO); oxoff = rng.uniform(-0.07, 0.07, NO)

    def draw(i):
        t = i / frames
        ax.cla(); ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        split = min(1.0, t / 0.62); burn = max(0.0, (t - 0.72) / 0.28)
        # cell water
        wlev = 0.18 + 0.4 * (1 - split) + 0.4 * burn * split
        ax.add_patch(Rectangle((0.08, 0.1), 0.84, min(0.62, wlev), facecolor=WATER, alpha=0.5))
        # electrodes
        for ex, lab in ((0.16, "cathode"), (0.84, "cathode")):
            ax.add_patch(Rectangle((ex - 0.012, 0.1), 0.024, 0.55, facecolor=MUTED))
            ax.text(ex, 0.05, lab, color=MUTED, fontsize=7.5, ha="center")
        ax.add_patch(Rectangle((0.5 - 0.012, 0.1), 0.024, 0.55, facecolor="#b55"))
        ax.text(0.5, 0.05, "O₂ collector", color="#d77", fontsize=7.5, ha="center")
        # H2 bubbles rising at cathodes
        nH = int(NH * split)
        for k in range(nH):
            yb = 0.2 + ((hphase[k] + t * 1.4) % 1.0) * (0.7)
            ax.add_patch(Circle((hx[k] + hxoff[k], yb), 0.016, color=CYAN, alpha=0.9))
        nO = int(NO * split)
        for k in range(nO):
            yb = 0.2 + ((ophase[k] + t * 1.2) % 1.0) * 0.7
            ax.add_patch(Circle((0.5 + oxoff[k], yb), 0.02, color=AMBER, alpha=0.9))
        if burn > 0.05:
            ax.text(0.5, 0.85, "⚡ ignition → recombine", color=RED, fontsize=10, ha="center")
        ax.text(0.18, 0.93, f"H₂ {int(NH*10*split)}", color=CYAN, fontsize=10, family="monospace")
        ax.text(0.78, 0.93, f"O₂ {int(NO*10*split)}", color=AMBER, fontsize=10, family="monospace")
        ax.text(0.5, 0.015, "180 H₂O → 180 H₂ + 90 O₂ → 180 H₂O · 24 MeV Geant4 drive",
                color=FG, fontsize=8.0, ha="center", family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames + 6, interval=1000/fps), "electrolysis", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 7. H2O cluster — 8 molecules in a hydrogen-bonded droplet
# --------------------------------------------------------------------------- #
def anim_cluster(cases: Dict, frames=70, fps=18):
    m = cases["h2o_cluster_fluid_stable"]["measured"]
    fig = plt.figure(figsize=(6.6, 4.4), dpi=100, facecolor=BG)
    overlay(fig, "H₂O cluster — a stable hydrogen-bonded droplet (8 molecules)",
            f"classical MD (Geant4 per-tick clock) · ~{m['mean_hbond_contacts']:.0f} H-bonds · T≈{m['mean_temperature_K']:.0f} K",
            cases, ["h2o_cluster_fluid_stable"])
    ax = fig.add_axes([0.06, 0.10, 0.88, 0.74]); ax.set_axis_off()
    ax.set_xlim(-3.4, 3.4); ax.set_ylim(-3.0, 3.0); ax.set_aspect("equal")
    rng = np.random.default_rng(21)
    n = 8
    ang0 = rng.uniform(0, 2 * math.pi, n)
    rad = rng.uniform(0.6, 2.2, n)
    spin = rng.uniform(-1, 1, n)
    mol_or = rng.uniform(0, 2 * math.pi, n)

    def draw(i):
        t = i / frames
        ax.cla(); ax.set_axis_off(); ax.set_xlim(-3.4, 3.4); ax.set_ylim(-3.0, 3.0)
        ax.set_aspect("equal")
        # soft droplet boundary
        th = np.linspace(0, 2 * math.pi, 60)
        ax.plot(2.85 * np.cos(th), 2.85 * np.sin(th), color=BLUE, alpha=0.3, lw=1.5, ls="--")
        Os = []
        for k in range(n):
            a = ang0[k] + 0.5 * math.sin(2 * math.pi * t + k)
            r = rad[k] + 0.25 * math.sin(2 * math.pi * t * 2 + k * 1.3)
            ox, oy = r * math.cos(a), r * math.sin(a)
            Os.append((ox, oy))
            ori = mol_or[k] + spin[k] * t * 4
            for s in (-1, 1):
                hx = ox + 0.55 * math.cos(ori + s * 0.91)
                hy = oy + 0.55 * math.sin(ori + s * 0.91)
                ax.plot([ox, hx], [oy, hy], color=GRID, lw=2.0, zorder=2)
                ax.add_patch(Circle((hx, hy), 0.12, color="#dfe6ee", zorder=3))
            ax.add_patch(Circle((ox, oy), 0.22, color=RED, ec="white", lw=0.8, zorder=4))
        # hydrogen bonds (dashed) between near O's
        for a in range(n):
            for b in range(a + 1, n):
                dx = Os[a][0] - Os[b][0]; dy = Os[a][1] - Os[b][1]
                d = math.hypot(dx, dy)
                if d < 1.5:
                    ax.plot([Os[a][0], Os[b][0]], [Os[a][1], Os[b][1]], color=CYAN,
                            alpha=0.5, lw=1.0, ls=":", zorder=1)
        ax.text(0, -2.95, f"Rg ≈ {m['mean_radius_of_gyration_A']:.2f} Å (bounded) — neither evaporates nor collapses",
                color=GREEN, fontsize=8.2, ha="center", family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames, interval=1000/fps), "h2o_cluster", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 8. Self-diffusion D(T) — particles spread faster at higher temperature
# --------------------------------------------------------------------------- #
def anim_diffusion(cases: Dict, frames=72, fps=18):
    pts = cases["h2o_diffusion_temperature_trend"]["measured"]["points"]
    fig = plt.figure(figsize=(7.4, 4.2), dpi=100, facecolor=BG)
    overlay(fig, "Self-diffusion D(T) — water molecules spread faster as T rises",
            "rigid-SPC/E MD (Geant4 per-tick clock) · D rises monotonically, tracks measured water",
            cases, ["h2o_diffusion_temperature_trend"])
    rng = np.random.default_rng(31)
    npart = 60
    starts = [rng.uniform(-0.25, 0.25, (npart, 2)) for _ in pts]
    dirs = [rng.normal(size=(npart, 2)) for _ in pts]
    axes = []
    for j in range(3):
        a = fig.add_axes([0.06 + j * 0.31, 0.16, 0.28, 0.62]); a.set_facecolor("#14181f")
        a.set_xticks([]); a.set_yticks([])
        for s in a.spines.values():
            s.set_color(GRID)
        axes.append(a)

    def draw(i):
        t = i / frames
        for j, p in enumerate(pts):
            a = axes[j]; a.cla(); a.set_facecolor("#14181f"); a.set_xticks([]); a.set_yticks([])
            for s in a.spines.values():
                s.set_color(GRID)
            a.set_xlim(-2.4, 2.4); a.set_ylim(-2.4, 2.4)
            sigma = math.sqrt(max(1e-3, p["D_1e9_m2_per_s"]) * t) * 1.05
            pos = starts[j] + dirs[j] * sigma
            a.scatter(pos[:, 0], pos[:, 1], s=14, c=[CYAN, AMBER, RED][j], alpha=0.8, edgecolors="none")
            a.set_title(f"{p['T_K']:.0f} K", color=FG, fontsize=9.5)
            a.text(0, -2.15, f"D = {p['D_1e9_m2_per_s']:.2f}\n(exp {p['D_exp_1e9_m2_per_s']:.2f})",
                   color=[CYAN, AMBER, RED][j], fontsize=8, ha="center", family="monospace")
        fig.text(0.5, 0.085, "D in 10⁻⁹ m²/s — rise ×3.7 (SPC/E) vs measured ×2.3",
                 color=MUTED, fontsize=8.0, ha="center", family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames, interval=1000/fps), "diffusion_temperature", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 9. Optics surrogate — learned ridge n lifts NaI refraction into transport
# --------------------------------------------------------------------------- #
def anim_surrogate(cases: Dict, frames=66, fps=18):
    m = cases["optics_surrogate_transport_applied"]["measured"]
    n_surr = float(m["mean_n"]); n_ext = 1.33; n_hand = 1.775
    fig = plt.figure(figsize=(7.2, 4.2), dpi=100, facecolor=BG)
    overlay(fig, "Optics surrogate — learned n lifts NaI refraction into transport",
            "ridge model (trained on handbook) corrects the f-sum extractor · feeds RINDEX",
            cases, ["optics_surrogate_transport_applied"])
    ax = fig.add_axes([0.30, 0.16, 0.66, 0.66]); ax.set_facecolor("#14181f")
    ax.set_xticks([]); ax.set_yticks([])

    def draw(i):
        t = min(1.0, i / (frames - 8))
        ax.cla(); ax.set_facecolor("#14181f"); ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(GRID)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1.4)
        # incident ray from top-left to interface, refracts by current n
        n_now = n_ext + (n_surr - n_ext) * t
        ax.axhline(0.5, color=BLUE, lw=2, alpha=0.5)             # NaI surface
        ax.add_patch(Rectangle((0, 0), 1, 0.5, color=VIOLET, alpha=0.18))
        ax.text(0.5, 0.08, "NaI crystal", color=VIOLET, fontsize=9, ha="center")
        # Snell: theta_t from theta_i=45deg, n_air=1
        ti = math.radians(45)
        st = math.sin(ti) / n_now
        tt = math.asin(min(1, st))
        x0 = 0.5
        ax.plot([x0 - 0.4, x0], [1.3, 0.5], color="white", lw=2)         # incident
        ax.plot([x0, x0 + 0.5 * math.tan(tt)], [0.5, 0.0], color=AMBER, lw=2.5)  # refracted
        ax.plot([x0, x0], [0.5, 1.0], color=GRID, ls=":", lw=1)          # normal
        ax.text(0.06, 1.25, f"n(NaI) = {n_now:.3f}", color=AMBER, fontsize=13, family="monospace")
        # gauge
        ax.barh(1.12, (n_now - 1) / (n_hand - 1) * 0.9, height=0.06, left=0.05, color=GREEN)
        ax.text(0.05, 1.05, f"extractor {n_ext:.2f}  →  surrogate {n_surr:.3f}  (handbook {n_hand})",
                color=FG, fontsize=8.2, family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames + 8, interval=1000/fps), "optics_surrogate", fps)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 10. Brine build — electron beam deposits energy in a salt-water box
# --------------------------------------------------------------------------- #
def anim_brine(cases: Dict, frames=66, fps=18):
    m = cases["h2o_fluid_brine_run_closes"]["measured"]
    edep = float(m["total_edep_mev"])
    fig = plt.figure(figsize=(7.0, 4.2), dpi=100, facecolor=BG)
    overlay(fig, "Brine material build — electron beam deposits energy in salt water",
            "element-component build (Na + Cl by mass) closes without the historical SIGSEGV",
            cases, ["h2o_fluid_brine_run_closes"])
    ax = fig.add_axes([0.06, 0.12, 0.88, 0.72]); ax.set_axis_off()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    rng = np.random.default_rng(41)
    nions = 28
    ix = rng.uniform(0.12, 0.88, nions); iy = rng.uniform(0.18, 0.82, nions)
    isna = rng.uniform(size=nions) < 0.5
    deps = []

    def draw(i):
        t = i / frames
        ax.cla(); ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.add_patch(Rectangle((0.1, 0.15), 0.8, 0.7, facecolor=WATER, alpha=0.45, edgecolor=BLUE, lw=1.5))
        # dissolved ions
        for k in range(nions):
            ax.add_patch(Circle((ix[k], iy[k]), 0.015, color=("#ffd27f" if isna[k] else "#7fdcc0"), alpha=0.8))
        # beam sweeps across, scattering deposits
        bx = 0.1 + 0.8 * min(1, t / 0.85)
        ax.plot([0.02, bx], [0.5, 0.5], color=CYAN, lw=2.2)
        ax.plot([bx], [0.5], "o", color="white", ms=8, markeredgecolor=CYAN, mew=2)
        if t < 0.86 and rng.uniform() < 0.8:
            deps.append((bx, 0.5 + rng.normal(0, 0.06)))
        for (dx, dy) in deps:
            ax.add_patch(Circle((dx, dy), 0.02, color=RED, alpha=0.35))
        ax.text(0.02, 0.55, "e⁻ →", color=CYAN, fontsize=9, family="monospace")
        ax.text(0.5, 0.05, f"total energy deposited {edep*min(1,t/0.85):.1f} MeV / {edep:.1f} MeV  ·  brine {m['fluid_bulk_edep_mev']:.1f} MeV  ·  50/50 primaries",
                color=FG, fontsize=7.8, ha="center", family="monospace")
        ax.text(0.78, 0.88, "Na⁺", color="#ffd27f", fontsize=8, family="monospace")
        ax.text(0.88, 0.88, "Cl⁻", color="#7fdcc0", fontsize=8, family="monospace")
        return []
    save(FuncAnimation(fig, draw, frames=frames + 6, interval=1000/fps), "brine_deposit", fps)
    plt.close(fig)


BUILDERS = {
    "csda": anim_csda, "beer": anim_beer, "nuclear": anim_nuclear,
    "molecule": anim_molecule, "pascal": anim_pascal,
    "electrolysis": anim_electrolysis, "cluster": anim_cluster,
    "diffusion": anim_diffusion, "surrogate": anim_surrogate, "brine": anim_brine,
}


def main(argv: List[str]) -> int:
    cases = load_cases()
    keys = argv[1:] if len(argv) > 1 else list(BUILDERS)
    for k in keys:
        fn = BUILDERS.get(k)
        if fn is None:
            print(f"unknown key {k} (have: {', '.join(BUILDERS)})"); continue
        fn(cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
