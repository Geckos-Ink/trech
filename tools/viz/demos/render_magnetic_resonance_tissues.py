#!/usr/bin/env python3
"""Render the Stage-2 virtual-tissue magnetic-resonance contrast.

Consumes the mr_tissue_contrast aggregate emitted by
scripts/run_magnetic_resonance_tissues.py (build/dev/out_mr_tissues) and shows, per
NIST tissue, the REAL Geant4-detected "output photon" signal next to the
Geant4-derived proton density that set the emission count. The point of the figure:
the detected signal is a genuine Geant4 Monte-Carlo tally (every consequent photon's
energy in a NaI shell), and because the excitation count = Geant4's ignorant proton
prediction, the contrast reproduces MRI proton-density weighting -- cortical bone is
the classic dark tissue -- with the small radiographic photon-yield gap made visible.

Usage:
  build/render-venv/bin/python tools/viz/demos/render_magnetic_resonance_tissues.py \
      --run build/dev/out_mr_tissues --out tools/viz/demos/magnetic_resonance_tissues.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN = REPO_ROOT / "build" / "dev" / "out_mr_tissues"
DEFAULT_OUT = Path(__file__).resolve().parent / "magnetic_resonance_tissues.png"

BG = "#080b11"
FG = "#e8edf2"
GRID = "#3a414c"
SIGNAL = "#7fdc7f"   # real detected signal (green = TRECH measurement)
PROTON = "#5cc8ff"   # Geant4 proton density (blue)
DARK = "#f2b25a"     # highlight for the MRI-dark tissue


def load_contrast(run_dir: Path) -> dict:
    path = run_dir / "trech_hook_emits.jsonl"
    if not path.exists():
        raise SystemExit(f"no {path} (run scripts/run_magnetic_resonance_tissues.py first)")
    payload: Optional[dict] = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("tag") == "mr_tissue_contrast":
            payload = rec.get("payload") or {}
    if not payload:
        raise SystemExit("no mr_tissue_contrast emit found")
    return payload


def render(run_dir: Path, out_path: Path) -> None:
    c = load_contrast(run_dir)
    rows = c.get("tissues") or []
    labels = [r.get("label", "?") for r in rows]
    rel_signal = [float(r.get("relative_signal") or 0.0) for r in rows]
    proton_ratio = [float(r.get("proton_ratio") or 0.0) for r in rows]
    events = [int(r.get("events_emitted") or 0) for r in rows]
    signal_mev = [float(r.get("detected_signal_mev") or 0.0) for r in rows]
    corr = float(c.get("corr_signal_vs_proton_density") or 0.0)

    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "text.color": FG, "axes.labelcolor": FG, "xtick.color": FG,
        "ytick.color": FG, "axes.edgecolor": GRID, "font.size": 10,
    })
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.6), gridspec_kw={"width_ratios": [1.35, 1]})
    fig.suptitle(
        "TRECH magnetic resonance (Stage 2): REAL Geant4-detected tissue contrast — "
        "emission count set by Geant4's ignorant proton prediction",
        color=FG, fontsize=13.5, y=0.99)

    # --- Panel 1: grouped bars, real detected signal vs proton density ---
    ax = axes[0]
    x = np.arange(len(labels))
    w = 0.4
    bars1 = ax.bar(x - w / 2, rel_signal, w, color=SIGNAL, edgecolor="#06121a",
                   label="REAL detected signal S(T)/S(water)")
    ax.bar(x + w / 2, proton_ratio, w, color=PROTON, edgecolor="#06121a",
           label="Geant4 proton density N$_H$(T)/N$_H$(water)")
    # highlight the MRI-dark tissue (lowest relative signal)
    if rel_signal:
        dark_i = int(np.argmin(rel_signal))
        bars1[dark_i].set_color(DARK)
    for xi, s in zip(x, rel_signal):
        ax.text(xi - w / 2, s + 0.01, f"{s:.2f}", ha="center", va="bottom",
                fontsize=8, color=FG)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right", fontsize=9)
    ax.set_ylabel("relative to water")
    ax.set_ylim(0, 1.18)
    ax.axhline(1.0, color=GRID, lw=0.7, ls=":")
    ax.set_title("Per-tissue response (water = 1)", fontsize=11)
    ax.grid(True, axis="y", color=GRID, alpha=0.3, lw=0.5)
    ax.legend(loc="lower center", fontsize=8.5, facecolor="#161b22",
              edgecolor=GRID, labelcolor=FG)

    # --- Panel 2: scatter, detected signal vs proton density (real correlation) ---
    ax = axes[1]
    nh = [r.get("proton_per_cm3", 0.0) / 1e22 for r in rows]
    ax.scatter(nh, signal_mev, s=70, color=SIGNAL, edgecolors="#06121a", zorder=5)
    for xi, yi, lab in zip(nh, signal_mev, labels):
        ax.annotate(lab, (xi, yi), textcoords="offset points", xytext=(6, 4),
                    fontsize=7.5, color="#c7d0da")
    if len(nh) >= 2:
        a, b = np.polyfit(nh, signal_mev, 1)
        xs = np.linspace(min(nh), max(nh), 50)
        ax.plot(xs, a * xs + b, color=PROTON, lw=1.1, ls="--",
                label=f"linear fit (r = {corr:.3f})")
        ax.legend(loc="upper left", fontsize=8.5, facecolor="#161b22",
                  edgecolor=GRID, labelcolor=FG)
    ax.set_xlabel("Geant4 proton density  (10$^{22}$ /cm³)")
    ax.set_ylabel("REAL detected signal  (MeV in NaI shell)")
    ax.set_title("Detected photons track proton density", fontsize=11)
    ax.grid(True, color=GRID, alpha=0.3, lw=0.5)

    bone = next((r for r in rows if "bone" in (r.get("label") or "")), None)
    bone_txt = ""
    if bone:
        bone_txt = (f"cortical bone (1H-poor) → MRI-dark: real signal "
                    f"{float(bone.get('relative_signal') or 0):.2f}× water "
                    f"(proton ratio {float(bone.get('proton_ratio') or 0):.2f})     •     ")
    fig.text(
        0.5, 0.045,
        bone_txt + f"detected signal vs proton density: r = {corr:.4f}     •     "
        f"emission count = Geant4 material-probe ¹H density (ignorant of NMR)",
        color="#c7d0da", fontsize=8.6, ha="center")
    fig.text(
        0.5, 0.014,
        "Every detected photon is a REAL Geant4 transport tally (all consequent radiation into a NaI shell); "
        "the excitation-per-proton is a labelled proxy, and the signal↔proton gap is the radiographic photon-yield term.",
        color="#9aa3ad", fontsize=7.9, ha="center", style="italic")

    fig.tight_layout(rect=(0, 0.075, 1, 0.955))
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
