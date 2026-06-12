"""Render the TRECH water self-diffusion vs temperature comparison.

The single-state-point bulk run (``render_bulk_water.py``) showed rigid SPC/E
water reproduces the measured self-diffusion D at ~300 K. A single point can be
lucky; a *trend* cannot. ``h2o_diffusion_temperature.js`` sweeps three
temperatures in one deterministic run and measures D at each, and this script
plots that D(T) against the measured temperature dependence of liquid-water
self-diffusion (Holz, Heil & Sacco, PCCP 2000):

* **experiment** (amber) — the measured D(T) curve; water's self-diffusion
  roughly triples between 278 and 318 K. Reference only; never fed to the sim.
* **TRECH simulated** (green) — D from the production-phase O-atom MSD via the
  Einstein relation, at each block's measured mean temperature.

The headline is the *trend*: TRECH's D rises monotonically and strongly with T,
tracking the measured curve. Honest caveats are stated on the plot
(constant-density sweep, single-origin MSD, finite N + cutoff).

Run::

    cd tools/viz
    source .venv/bin/activate
    python demos/render_diffusion_temperature.py

Input:  ``build/dev/out_h2o_diffusion_T/trech_hook_emits.jsonl``.
Output: ``tools/viz/demos/h2o_diffusion_temperature.png``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_h2o_diffusion_T"
DEFAULT_OUT = Path(__file__).resolve().parent / "h2o_diffusion_temperature.png"

BG_COLOR = "#16181d"
FG_COLOR = "#e8e8e8"
EXP_COLOR = "#ffb347"     # amber — measured physics
TRECH_COLOR = "#7fdc7f"   # green — TRECH simulation

# Measured water self-diffusion (Holz, Heil & Sacco, PCCP 2000), 1e-9 m^2/s.
# Reference curve only; the engine never sees these.
EXP_D_TABLE = [
    (278, 1.31), (283, 1.54), (288, 1.78), (293, 2.03), (298, 2.30),
    (303, 2.60), (308, 2.92), (313, 3.24), (318, 3.58),
]


def load_diffusion(run_dir: Path) -> Optional[Dict]:
    path = run_dir / "trech_hook_emits.jsonl"
    if not path.exists():
        raise SystemExit(f"error: {path} not found; run h2o_diffusion_temperature.js first")
    final = None
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("tag") == "diffusion_vs_temperature":
                final = rec.get("payload")
    if not final or not final.get("points"):
        raise SystemExit("error: no diffusion_vs_temperature emit found")
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    data = load_diffusion(args.run)
    pts = data["points"]
    tt = np.array([p["mean_temperature_K"] for p in pts])
    dd = np.array([p["self_diffusion_m2_per_s"] for p in pts]) * 1e9   # 1e-9 m^2/s
    de = np.array([p["experiment_self_diffusion_m2_per_s"] for p in pts]) * 1e9

    exp_t = np.array([t for t, _ in EXP_D_TABLE])
    exp_d = np.array([d for _, d in EXP_D_TABLE])

    fig, ax = plt.subplots(figsize=(7.4, 5.0), dpi=110, facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    for s in ax.spines.values():
        s.set_color("#555c66")
    ax.tick_params(colors=FG_COLOR, labelsize=9)

    ax.plot(exp_t, exp_d, color=EXP_COLOR, lw=2.0, marker="o", ms=4,
            label="experiment (Holz et al. 2000)")
    ax.plot(tt, dd, color=TRECH_COLOR, lw=0, marker="s", ms=10,
            markeredgecolor="white", markeredgewidth=0.8,
            label="TRECH rigid-SPC/E (this run)")
    # connect the TRECH points to show the trend
    order = np.argsort(tt)
    ax.plot(tt[order], dd[order], color=TRECH_COLOR, lw=1.4, ls="--", alpha=0.7)
    # thin guide from each TRECH point to the experiment value at the same T
    for ti, di, ei in zip(tt, dd, de):
        ax.plot([ti, ti], [di, ei], color="#777", lw=0.8, ls=":", alpha=0.6)

    ax.set_xlabel("temperature  [K]", color=FG_COLOR, fontsize=10)
    ax.set_ylabel("self-diffusion D  [10⁻⁹ m²/s]", color=FG_COLOR, fontsize=10)
    ax.set_title("TRECH water self-diffusion vs temperature — tracking the "
                 "measured trend",
                 color=FG_COLOR, fontsize=12)
    ax.set_xlim(274, 324)
    ax.set_ylim(0, max(dd.max(), exp_d.max()) * 1.15)

    ratio_tr = float(data.get("d_ratio_trech") or 0.0)
    ratio_ex = float(data.get("d_ratio_experiment") or 0.0)
    span = data.get("temperature_span_K") or [tt.min(), tt.max()]
    txt = (f"D rise over {span[0]:.0f}→{span[1]:.0f} K:\n"
           f"  TRECH       ×{ratio_tr:.2f}\n"
           f"  experiment  ×{ratio_ex:.2f}\n"
           f"(N={data.get('molecules')}, constant-density,\n"
           f" multi-origin MSD; SPC/E rise is\n"
           f" a touch steep — the known feature)")
    ax.text(0.03, 0.97, txt, transform=ax.transAxes, va="top", ha="left",
            color=FG_COLOR, fontsize=9.5, family="monospace",
            bbox=dict(facecolor="#23272e", edgecolor=EXP_COLOR,
                      boxstyle="round,pad=0.5", alpha=0.92))
    leg = ax.legend(loc="lower right", fontsize=9.5, facecolor=BG_COLOR,
                    edgecolor="#555c66")
    for t in leg.get_texts():
        t.set_color(FG_COLOR)

    fig.tight_layout()
    fig.savefig(args.out, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"wrote {args.out}")
    print(f"  TRECH D(T): " +
          "  ".join(f"{t:.0f}K={d:.2f}" for t, d in zip(tt, dd)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
