#!/usr/bin/env python3
"""Render the Stage-3 1D magnetic-resonance image line.

Consumes the mr_image_line emit of testscenario_magnetic_resonance_imaging.js and
shows how a field gradient turns per-tissue proton density into an actual image:

  1. the reconstructed 1D image line (DFT of the frequency-encoded readout), with
     the two dark features -- the air gap (black) and cortical bone -- resolved at
     their true positions;
  2. a grayscale "image strip" of that same profile (what a 1D MRI readout looks
     like), annotated with each tissue;
  3. the recovered-vs-true position check and each voxel's Larmor offset frequency.

Everything is read from the run emit: Geant4 supplied the proton densities and the
real phantom + transport; the gradient encoding + reconstruction are hook-layer.

Usage:
  build/render-venv/bin/python tools/viz/demos/render_magnetic_resonance_imaging.py \
      --run build/dev/out_mr_imaging --out tools/viz/demos/magnetic_resonance_imaging.png
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
DEFAULT_RUN = REPO_ROOT / "build" / "dev" / "out_mr_imaging"
DEFAULT_OUT = Path(__file__).resolve().parent / "magnetic_resonance_imaging.png"

BG = "#080b11"
FG = "#e8edf2"
GRID = "#3a414c"
LINE = "#7fdc7f"
TRUE = "#5cc8ff"
DARK = "#f2b25a"


def load_image_line(run_dir: Path) -> dict:
    path = run_dir / "trech_hook_emits.jsonl"
    if not path.exists():
        raise SystemExit(f"no {path} (run the imaging scenario first)")
    payload: Optional[dict] = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("tag") == "mr_image_line":
            payload = rec.get("payload") or {}
    if not payload:
        raise SystemExit("no mr_image_line emit found")
    return payload


def render(run_dir: Path, out_path: Path) -> None:
    p = load_image_line(run_dir)
    prof = p.get("image_profile") or []
    xs = np.array([q["x_mm"] for q in prof])
    ii = np.array([q["intensity"] for q in prof])
    voxels = p.get("voxels") or []
    machine = p.get("machine") or {}
    met = p.get("metrics") or {}

    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "text.color": FG, "axes.labelcolor": FG, "xtick.color": FG,
        "ytick.color": FG, "axes.edgecolor": GRID, "font.size": 10,
    })
    fig = plt.figure(figsize=(15, 6.8))
    gs = fig.add_gridspec(2, 2, height_ratios=[3.0, 0.6], width_ratios=[1.55, 1],
                          hspace=0.35, wspace=0.22,
                          left=0.055, right=0.965, top=0.9, bottom=0.16)
    fig.suptitle(
        "TRECH magnetic resonance (Stage 3): a 1D MRI image line — field gradient "
        "encodes position, DFT reconstructs the Geant4 proton-density profile",
        color=FG, fontsize=13.5, y=0.99)

    # --- reconstructed image line ---
    ax = fig.add_subplot(gs[0, 0])
    ax.plot(xs, ii, color=LINE, lw=1.8)
    ax.fill_between(xs, ii, color=LINE, alpha=0.12)
    for v in voxels:
        xt = v["x_true_mm"]
        lab = v["label"]
        inten = float(v.get("recovered_intensity") or 0.0)
        col = DARK if v.get("is_dark_feature") or inten < 0.7 else FG
        ax.annotate(lab, (xt, inten + 0.03), ha="center", fontsize=8, color=col)
        ax.axvline(xt, color=GRID, lw=0.5, ls=":")
    ax.set_xlabel("position along readout gradient  x (mm)")
    ax.set_ylabel("reconstructed |ρ(x)|  (norm.)")
    ax.set_ylim(0, 1.18)
    ax.set_title("Reconstructed 1D image line", fontsize=11)
    ax.grid(True, color=GRID, alpha=0.25, lw=0.5)

    # --- grayscale image strip (what the 1D readout looks like) ---
    axs = fig.add_subplot(gs[1, 0])
    strip = ii.reshape(1, -1)
    axs.imshow(strip, aspect="auto", cmap="gray", vmin=0, vmax=1,
               extent=[xs.min(), xs.max(), 0, 1])
    for v in voxels:
        axs.text(v["x_true_mm"], 0.5, v["label"], ha="center", va="center",
                 fontsize=7.5, color=("#101418" if float(v.get("recovered_intensity") or 0) > 0.5 else "#e8edf2"))
    axs.set_yticks([])
    axs.set_xlabel("MRI image strip (brightness = reconstructed signal)")

    # --- recovered vs true position + offsets ---
    ax2 = fig.add_subplot(gs[:, 1])
    bright = [v for v in voxels if v.get("x_recovered_mm") is not None]
    xt = [v["x_true_mm"] for v in bright]
    xr = [v["x_recovered_mm"] for v in bright]
    off = [v["larmor_offset_khz"] for v in bright]
    ax2.plot([-28, 28], [-28, 28], color=GRID, lw=0.8, ls="--")
    sc = ax2.scatter(xt, xr, c=off, cmap="coolwarm", s=90, edgecolors="#06121a", zorder=5)
    for v in bright:
        ax2.annotate(f"{v['label']}\n{v['larmor_offset_khz']:+.1f} kHz",
                     (v["x_true_mm"], v["x_recovered_mm"]),
                     textcoords="offset points", xytext=(7, -2), fontsize=7, color="#c7d0da")
    ax2.set_xlabel("true position (mm)")
    ax2.set_ylabel("recovered from peak frequency (mm)")
    ax2.set_title("Position recovered from Larmor offset\nω(x)=γ(B₀+G$_x$·x)", fontsize=11)
    ax2.grid(True, color=GRID, alpha=0.25, lw=0.5)
    cb = fig.colorbar(sc, ax=ax2, fraction=0.046, pad=0.04)
    cb.set_label("gradient offset (kHz)", color=FG, fontsize=8.5)
    cb.ax.tick_params(colors=FG, labelsize=7.5)

    air = next((v for v in voxels if v["label"] == "air gap"), {})
    bone = next((v for v in voxels if v["label"] == "bone"), {})
    fig.text(
        0.5, 0.07,
        f"gradient {machine.get('gradient_t_per_m', 0)*1e3:.0f} mT/m  ·  "
        f"encoding bandwidth {machine.get('bandwidth_khz', 0):.0f} kHz over "
        f"{machine.get('fov_mm', 0):.0f} mm FOV  ·  max position error "
        f"{met.get('max_position_error_mm', 0):.3f} mm  ·  amplitude↔proton r = "
        f"{met.get('amplitude_proton_corr', 0):.3f}  ·  air gap {float(air.get('recovered_intensity') or 0):.2f} "
        f"(black), cortical bone {float(bone.get('recovered_intensity') or 0):.2f} (dark)",
        color="#c7d0da", fontsize=8.4, ha="center")
    fig.text(
        0.5, 0.028,
        "Geant4 builds the real phantom + transports the probe and supplies the ¹H densities; "
        "the gradient encoding + DFT reconstruction are hook-layer signal processing (no engine spin rule).",
        color="#9aa3ad", fontsize=7.9, ha="center", style="italic")

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
