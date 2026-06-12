"""Render the TRECH carbon-nanotube band-gap vs diameter comparison.

A single-wall nanotube's electronic character is fixed by its (n,m) chirality:
metallic if (n-m) is divisible by 3, otherwise semiconducting with a band gap
inversely proportional to the diameter. ``cnt_band_structure.js`` computes this
for a panel of chiralities (tight-binding zone-folding in the hook layer); this
script plots it against the textbook physics:

* **theory / measured** (amber) — the leading-order zone-folding law
  E_g = 2 a_cc gamma0 / d (a hyperbola in d), and the STM-measured semiconducting
  gaps (Wildoer/Odom 1998) as reference points.
* **TRECH simulated** (green = semiconducting, grey = metallic) — the computed
  per-tube band gap vs diameter; metallic tubes sit on E_g = 0.

The headline is that the model reproduces both the metallic/semiconducting
classification (the (n-m) mod 3 rule) and the E_g ~ 1/d gap law on the measured
points. Honest residual on the plot: leading-order zone-folding only (no
curvature secondary gaps, no trigonal-warping family split).

Run::

    cd tools/viz
    source .venv/bin/activate
    python demos/render_cnt_band_structure.py

Input:  ``build/dev/out_cnt_band_structure/trech_hook_emits.jsonl``.
Output: ``tools/viz/demos/cnt_band_structure.png``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_cnt_band_structure"
DEFAULT_OUT = Path(__file__).resolve().parent / "cnt_band_structure.png"

BG_COLOR = "#16181d"
FG_COLOR = "#e8e8e8"
EXP_COLOR = "#ffb347"     # amber — theory / measured
SEMI_COLOR = "#7fdc7f"    # green — TRECH semiconducting
METAL_COLOR = "#9aa3ad"   # grey  — TRECH metallic


def load_panel(run_dir: Path) -> Optional[Dict]:
    path = run_dir / "trech_hook_emits.jsonl"
    if not path.exists():
        raise SystemExit(f"error: {path} not found; run cnt_band_structure.js first")
    panel = None
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("tag") == "cnt_panel":
                panel = rec.get("payload")
    if not panel or not panel.get("tubes"):
        raise SystemExit("error: no cnt_panel emit found")
    return panel


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    panel = load_panel(args.run)
    tubes = panel["tubes"]
    scaling = float(panel["gap_scaling_eV_nm"])      # 2 a_cc gamma0, eV*nm
    gamma0 = float(panel["gamma0_eV"])

    semi = [t for t in tubes if not t["metallic"]]
    metal = [t for t in tubes if t["metallic"]]

    fig, ax = plt.subplots(figsize=(7.6, 5.0), dpi=110, facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    for s in ax.spines.values():
        s.set_color("#555c66")
    ax.tick_params(colors=FG_COLOR, labelsize=9)

    # theory hyperbola E_g = scaling / d
    dd = np.linspace(min(t["diameter_nm"] for t in tubes) * 0.95,
                     max(t["diameter_nm"] for t in tubes) * 1.05, 200)
    ax.plot(dd, scaling / dd, color=EXP_COLOR, lw=1.8,
            label=f"zone-folding law  E$_g$ = 2 a$_{{cc}}$γ₀ / d  ({scaling:.2f} eV·nm)")

    # TRECH semiconducting tubes
    ds = np.array([t["diameter_nm"] for t in semi])
    es = np.array([t["band_gap_eV"] for t in semi])
    ax.plot(ds, es, "s", color=SEMI_COLOR, ms=9, markeredgecolor="white",
            markeredgewidth=0.7, label="TRECH semiconducting (n−m mod 3 ≠ 0)")
    # TRECH metallic tubes (E_g = 0)
    dm = np.array([t["diameter_nm"] for t in metal])
    ax.plot(dm, np.zeros_like(dm), "o", color=METAL_COLOR, ms=8,
            markeredgecolor="white", markeredgewidth=0.6,
            label="TRECH metallic (n−m mod 3 = 0)")

    # measured anchors
    anchors = [(t["diameter_nm"], t["measured_gap_eV"], t)
               for t in tubes if t.get("measured_gap_eV")]
    if anchors:
        ax.plot([a[0] for a in anchors], [a[1] for a in anchors], "*",
                color=EXP_COLOR, ms=16, markeredgecolor="white",
                markeredgewidth=0.6, label="measured (STM, Wildöer/Odom 1998)")

    # label a few representative tubes
    for t in semi:
        if (t["n"], t["m"]) in {(10, 0), (17, 0), (7, 3), (14, 7)}:
            ax.annotate(f"({t['n']},{t['m']})", (t["diameter_nm"], t["band_gap_eV"]),
                        textcoords="offset points", xytext=(8, 6),
                        color=SEMI_COLOR, fontsize=8.5)
    for t in metal:
        if (t["n"], t["m"]) in {(5, 5), (9, 0), (12, 6)}:
            ax.annotate(f"({t['n']},{t['m']})", (t["diameter_nm"], 0.0),
                        textcoords="offset points", xytext=(6, 6),
                        color=METAL_COLOR, fontsize=8.5)

    ax.set_xlabel("nanotube diameter  d  [nm]", color=FG_COLOR, fontsize=10)
    ax.set_ylabel("band gap  E$_g$  [eV]", color=FG_COLOR, fontsize=10)
    ax.set_title("TRECH carbon-nanotube band gap vs diameter (set by chirality)",
                 color=FG_COLOR, fontsize=12)
    ax.set_ylim(-0.08, max(es) * 1.12)
    ax.axhline(0.0, color="#555c66", lw=0.8, ls=":")

    val = panel.get("validation") or {}
    txt = (f"metallicity rule (n−m) mod 3:  "
           f"{'holds' if val.get('metallicity_rule_holds') else 'FAILS'}\n"
           f"E$_g$·d = {panel['mean_gap_times_diameter_eV_nm']:.2f} eV·nm "
           f"(measured ~0.7–0.9)\n"
           f"anchors within {panel['max_anchor_rel_err'] * 100:.0f}%   "
           f"(γ₀ = {gamma0:.1f} eV)\n"
           f"{panel['metallic_count']} metallic / {panel['semiconducting_count']} "
           f"semiconducting tubes")
    ax.text(0.97, 0.97, txt, transform=ax.transAxes, va="top", ha="right",
            color=FG_COLOR, fontsize=9, family="monospace",
            bbox=dict(facecolor="#23272e", edgecolor=EXP_COLOR,
                      boxstyle="round,pad=0.5", alpha=0.92))
    leg = ax.legend(loc="lower left", fontsize=8.5, facecolor=BG_COLOR,
                    edgecolor="#555c66")
    for t in leg.get_texts():
        t.set_color(FG_COLOR)

    fig.tight_layout()
    fig.savefig(args.out, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"wrote {args.out}")
    print(f"  {panel['metallic_count']} metallic / {panel['semiconducting_count']} "
          f"semiconducting; E_g*d = {panel['mean_gap_times_diameter_eV_nm']:.3f} eV*nm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
