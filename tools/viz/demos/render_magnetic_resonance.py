#!/usr/bin/env python3
"""Render the Stage-1 magnetic-resonance scenario as a static comparison figure.

Consumes the hook emits of ``testscenario_magnetic_resonance.js``
(``mr_spectrum`` / ``mr_fid`` / ``mr_summary``) and renders three panels, in the
same dark palette / honest-end-card style as the bulk-water and efflux demos:

  1. the swept-RF spectroscopy response (broad, apparatus-bandwidth-limited),
     with the precise Larmor line DISCOVERED from the FID carrier marked against
     the textbook gamma/2pi * B0 truth line;
  2. the free-induction-decay envelope with its recovered T2*, plus an inset of
     the lab-frame carrier oscillation at the discovered frequency;
  3. the Geant4-derived proton-density contrast for the reference tissues (the
     Stage-2 preview) -- water=1, cortical bone the classic MRI-dark tissue.

Nothing here is hard-coded physics: every number is read from the run emits;
Geant4 supplied the proton density and the hook layer discovered the resonance.

Usage:
  build/render-venv/bin/python tools/viz/demos/render_magnetic_resonance.py \
      --run build/dev/out_mr --out tools/viz/demos/magnetic_resonance.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN = REPO_ROOT / "build" / "dev" / "out_mr"
DEFAULT_OUT = Path(__file__).resolve().parent / "magnetic_resonance.png"

BG = "#080b11"
FG = "#e8edf2"
GRID = "#3a414c"
SWEEP = "#5cc8ff"       # spectroscopy sweep
DISCOVERED = "#7fdc7f"  # discovered Larmor (green = TRECH)
TRUTH = "#f2b25a"       # textbook truth (amber)
FID_C = "#c870ff"       # FID envelope
BONE = "#f2b25a"
SOFT = "#5cc8ff"


def load_emits(run_dir: Path) -> Dict[str, dict]:
    path = run_dir / "trech_hook_emits.jsonl"
    if not path.exists():
        raise SystemExit(f"no hook emits at {path} (run the scenario first)")
    latest: Dict[str, dict] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        tag = rec.get("tag")
        if tag in ("mr_spectrum", "mr_fid", "mr_summary"):
            latest[tag] = rec.get("payload") or {}
    for need in ("mr_spectrum", "mr_fid", "mr_summary"):
        if need not in latest:
            raise SystemExit(f"missing '{need}' emit (run incomplete?)")
    return latest


def render(run_dir: Path, out_path: Path) -> None:
    emits = load_emits(run_dir)
    spec = emits["mr_spectrum"]
    fid = emits["mr_fid"]
    summ = emits["mr_summary"]

    disc = summ.get("discovered") or {}
    gap = summ.get("gap_to_truth") or {}
    g4 = summ.get("geant4_material") or {}

    larmor = float(disc.get("larmor_mhz") or 0.0)
    coarse = float(disc.get("sweep_coarse_peak_mhz") or 0.0)
    expected = float(gap.get("larmor_expected_mhz") or 0.0)
    gamma_rec = float(disc.get("gamma_recovered_mhz_per_t") or 0.0)
    gamma_ref = float(gap.get("gamma_reference_mhz_per_t") or 42.577478518)
    b0 = float((summ.get("machine") or {}).get("b0_tesla") or 0.0)
    proton = float(g4.get("water_proton_per_cm3") or 0.0)
    t2_fit = float(disc.get("t2_star_s_fit") or 0.0)
    t2_in = float((summ.get("machine") or {}).get("t2_star_s_input") or 0.0)
    rf_photons = float(disc.get("detected_rf_photons") or 0.0)

    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "text.color": FG, "axes.labelcolor": FG, "xtick.color": FG,
        "ytick.color": FG, "axes.edgecolor": GRID, "font.size": 9.5,
    })
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.2))
    fig.suptitle(
        "TRECH magnetic resonance (Stage 1): a 5 cm³ water cube — "
        "Larmor DISCOVERED, proton density from Geant4",
        color=FG, fontsize=13.5, y=0.99)

    # --- Panel 1: spectroscopy sweep ---
    ax = axes[0]
    f = np.array([p["freq_mhz"] for p in spec.get("points") or []])
    r = np.array([p["response"] for p in spec.get("points") or []])
    ax.plot(f, r, color=SWEEP, lw=1.4, label="swept-RF response |M$_{xy}$|")
    ax.axvline(expected, color=TRUTH, lw=1.6, ls="--",
               label=f"textbook $\\gamma/2\\pi\\cdot B_0$ = {expected:.3f} MHz")
    ax.axvline(larmor, color=DISCOVERED, lw=1.6,
               label=f"discovered (FID) = {larmor:.3f} MHz")
    ax.set_xlabel("RF frequency (MHz)")
    ax.set_ylabel("normalized response")
    ax.set_title("Spectroscopy sweep\n(broad = pulse bandwidth)", fontsize=10.5)
    ax.grid(True, color=GRID, alpha=0.35, lw=0.5)
    ax.legend(loc="lower center", fontsize=7.8, facecolor="#161b22",
              edgecolor=GRID, labelcolor=FG)

    # --- Panel 2: FID envelope + carrier inset ---
    ax = axes[1]
    tms = np.array([p["t_ms"] for p in fid.get("envelope") or []])
    amp = np.array([p["amplitude"] for p in fid.get("envelope") or []])
    a0 = amp[0] if len(amp) else 1.0
    ax.plot(tms, amp / a0, color=FID_C, lw=1.6, label="FID envelope (measured)")
    if t2_fit > 0:
        tfit = np.linspace(0, tms.max() if len(tms) else 1.0, 200)
        ax.plot(tfit, np.exp(-tfit / (t2_fit * 1e3)), color=DISCOVERED, lw=1.1,
                ls="--", label=f"exp(-t/T2*), T2*={t2_fit*1e3:.2f} ms")
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("|M$_{xy}$| / M$_0$")
    ax.set_title("Free-induction decay\n(detected RF signal)", fontsize=10.5)
    ax.grid(True, color=GRID, alpha=0.35, lw=0.5)
    ax.legend(loc="upper right", fontsize=8, facecolor="#161b22",
              edgecolor=GRID, labelcolor=FG)
    snip = fid.get("carrier_snippet") or []
    if snip:
        axin = ax.inset_axes([0.40, 0.30, 0.54, 0.40])
        tn = np.array([p["t_ns"] for p in snip])
        sg = np.array([p["signal"] for p in snip])
        sgn = sg / (np.max(np.abs(sg)) or 1.0)
        axin.plot(tn, sgn, color=SWEEP, lw=0.9)
        axin.set_facecolor("#0c1420")
        axin.tick_params(labelsize=6, colors=FG)
        axin.set_xlabel("t (ns)", fontsize=6.5)
        axin.set_title(f"carrier @ {larmor:.1f} MHz", fontsize=7, color=FG)
        for s in axin.spines.values():
            s.set_color(GRID)

    # --- Panel 3: Geant4-derived tissue proton-density contrast ---
    ax = axes[2]
    tissues = summ.get("tissue_preview") or []
    labels = ["water"] + [t["material"].replace("G4_", "").replace("_ICRP", "")
                          .replace("_", " ").title() for t in tissues]
    signals = [1.0] + [float(t.get("relative_signal") or 0.0) for t in tissues]
    colors = [SOFT] + [BONE if s < 0.75 else SOFT for s in signals[1:]]
    ypos = np.arange(len(labels))[::-1]
    ax.barh(ypos, signals, color=colors, edgecolor="#06121a", height=0.62)
    for y, s in zip(ypos, signals):
        ax.text(s + 0.01, y, f"{s:.2f}×", va="center", fontsize=8.5, color=FG)
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set_xlim(0, 1.15)
    ax.set_xlabel("relative MR signal (∝ Geant4 ¹H density)")
    ax.set_title("Proton-density contrast\n(Stage-2 preview, Geant4-derived)",
                 fontsize=10.5)
    ax.grid(True, axis="x", color=GRID, alpha=0.3, lw=0.5)

    # honest end-card footer (two lines so nothing clips at the edges)
    fig.text(
        0.5, 0.045,
        f"Discovered γ/2π = {gamma_rec:.4f} MHz/T  vs  CODATA {gamma_ref:.4f} "
        f"({abs(gamma_rec-gamma_ref)/gamma_ref:.2%})     •     "
        f"Geant4 water ¹H = {proton:.3e} /cm³ (= literature)     •     "
        f"B₀ = {b0:g} T     •     detected RF quanta ≈ {rf_photons:.2e}",
        color="#c7d0da", fontsize=8.4, ha="center")
    fig.text(
        0.5, 0.014,
        "Geant4 does not simulate nuclear spin — the Bloch dynamics are hook-layer "
        "physics-for-comparison; the textbook values grade the gap only.",
        color="#9aa3ad", fontsize=8.0, ha="center", style="italic")

    fig.tight_layout(rect=(0, 0.07, 1, 0.955))
    fig.savefig(out_path, dpi=130)
    print(f"wrote {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    render(args.run, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
