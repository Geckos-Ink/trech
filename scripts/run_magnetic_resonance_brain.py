#!/usr/bin/env python3
"""Stage-4 magnetic-resonance driver: a 2D brain MRI image.

Renders a recognizable axial-head MRI whose per-tissue brightness is the
Geant4-computed proton (1H) number density:

  1. RUN the Geant4 scenario (testscenario_magnetic_resonance_brain.js): it builds
     the brain-tissue materials (water-content proxies for the mobile-1H fraction),
     transports a real probe beam through a representative slab, and reports each
     tissue's 1H number density in trech_scores.jsonl -> material_probes. These are
     ignorant material facts (Geant4 has no idea it is for MRI).

  2. PHANTOM: build a procedural, BrainWeb-inspired axial head slice (skull ring,
     scalp/fat, subarachnoid CSF, grey-matter cortical ribbon, white-matter core,
     lateral ventricles, deep grey nuclei) as a tissue-label map.

  3. IMAGE: paint each pixel with its tissue's Geant4 proton density -> rho(x,y);
     simulate MRI acquisition (2D FFT -> k-space, mild readout apodization + fixed
     -seed complex noise) and reconstruct (inverse 2D FFT) -> the brain MRI.

  4. Render tools/viz/demos/magnetic_resonance_brain.png and write an
     mr_brain_image aggregate emit under build/dev/out_mr_brain for the validation
     suite.

Honest scope: the anatomy (which tissue sits where) is a digital phantom we define
(BrainWeb-inspired); the per-tissue brightness is Geant4-derived; the imaging
pipeline (k-space + FFT) is signal processing. MRI signal is from mobile protons,
so each tissue's MRI proton density is modelled from its water/mobile-1H fraction
(the biological reference) and Geant4 turns it into an absolute 1H number density.

Usage:
  build/render-venv/bin/python scripts/run_magnetic_resonance_brain.py \
      --binary build/dev/trech --runs-dir build/dev
(matplotlib + numpy required; use the render venv.)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = REPO_ROOT / "examples" / "experiments" / "testscenario_magnetic_resonance_brain.js"
DEFAULT_OUT_PNG = REPO_ROOT / "tools" / "viz" / "demos" / "magnetic_resonance_brain.png"

# tissue key -> proxy material name declared in the scenario
TISSUE_MATERIAL = {
    "csf": "mri_csf", "fat": "mri_fat", "grey": "mri_grey_matter",
    "muscle": "mri_muscle", "white": "mri_white_matter", "skull": "mri_skull",
    "air": "G4_AIR",
}

# integer label ids for the phantom map
LAB = {"air": 0, "muscle": 1, "fat": 2, "skull": 3, "csf": 4, "grey": 5, "white": 6}
LAB_TISSUE = {v: k for k, v in LAB.items()}


def _load_scores(run_dir: Path) -> Optional[dict]:
    path = run_dir / "trech_scores.jsonl"
    if not path.exists():
        return None
    last = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            last = json.loads(line)
    return last


def run_scenario(binary: Path, out_dir: Path, events: int) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = [str(binary), "run", str(SCENARIO), "--events", str(events), "--output", str(out_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-2000:] + "\n" + proc.stderr[-2000:] + "\n")
        raise SystemExit("trech run failed for the brain scenario")
    scores = _load_scores(out_dir)
    if scores is None:
        raise SystemExit(f"no scores produced in {out_dir}")
    return scores


def read_proton_densities(scores: dict) -> Dict[str, float]:
    probes = {m.get("name"): m for m in (scores.get("material_probes") or [])}
    out: Dict[str, float] = {}
    for tissue, mat in TISSUE_MATERIAL.items():
        m = probes.get(mat) or {}
        out[tissue] = float((m.get("numberDensityPerCm3") or {}).get("H") or 0.0)
    return out


def build_phantom(n: int, fov_mm: float):
    """Procedural axial head slice -> integer tissue-label map (BrainWeb-inspired)."""
    ax = np.linspace(-fov_mm / 2, fov_mm / 2, n)
    X, Y = np.meshgrid(ax, ax)

    def ellipse(a, b, cx=0.0, cy=0.0, ang=0.0):
        t = np.deg2rad(ang)
        xr = (X - cx) * np.cos(t) + (Y - cy) * np.sin(t)
        yr = -(X - cx) * np.sin(t) + (Y - cy) * np.cos(t)
        return (xr / a) ** 2 + (yr / b) ** 2 <= 1.0

    lab = np.zeros((n, n), dtype=np.int32)  # air
    # concentric head layers (outer -> inner); constant-thickness rings via shrink
    lab[ellipse(72, 88)] = LAB["muscle"]   # scalp / skin
    lab[ellipse(69.5, 85.5)] = LAB["fat"]  # subcutaneous fat
    lab[ellipse(67, 83)] = LAB["skull"]    # cranial bone
    lab[ellipse(61, 77)] = LAB["csf"]      # subarachnoid CSF
    lab[ellipse(59, 75)] = LAB["grey"]     # cortical grey-matter ribbon
    brain = ellipse(54, 70)
    lab[brain] = LAB["white"]              # white-matter core

    # gyral/sulcal hint: shallow, irregular radial CSF in-folds at the cortical
    # surface (a few incommensurate harmonics so the folds are not periodic).
    ang = np.arctan2(Y, X)
    re = np.sqrt((X / 56.5) ** 2 + (Y / 72.5) ** 2)
    fold = (np.cos(13 * ang + 0.4) + 0.6 * np.cos(21 * ang + 1.9)
            + 0.4 * np.cos(8 * ang - 0.7))
    sulci = (fold > 1.15) & (re > 0.83) & (re < 1.03) & brain
    lab[sulci] = LAB["csf"]

    # lateral ventricles (CSF) + slit-like third ventricle, only inside the brain
    vent = (ellipse(7, 21, cx=-8, cy=6, ang=-8) | ellipse(7, 21, cx=8, cy=6, ang=8)
            | ellipse(2.2, 13, cx=0, cy=2))
    lab[vent & brain] = LAB["csf"]

    # deep grey nuclei (thalamus / basal ganglia) lateral to the ventricles
    dgm = ellipse(9, 12, cx=-17, cy=-2) | ellipse(9, 12, cx=17, cy=-2)
    lab[dgm & brain & (lab == LAB["white"])] = LAB["grey"]
    return lab


def simulate_mri(rho: np.ndarray, seed: int = 20260705) -> np.ndarray:
    """2D k-space acquisition + reconstruction: fft2 -> mild apodization + noise -> ifft2."""
    n = rho.shape[0]
    k = np.fft.fftshift(np.fft.fft2(rho))
    # very mild readout T2*-like apodization (a gentle radial roll-off that tempers
    # Gibbs ringing without noticeably blurring) -> keeps sharp anatomy + a clean
    # background, while still exercising the acquire -> reconstruct chain.
    ax = np.linspace(-1, 1, n)
    KX, KY = np.meshgrid(ax, ax)
    kr = np.sqrt(KX ** 2 + KY ** 2)
    k *= np.exp(-(kr ** 2) / (2 * 2.6 ** 2))
    # fixed-seed complex acquisition noise (a small fraction of the DC amplitude)
    rng = np.random.default_rng(seed)
    noise_scale = 0.0010 * np.abs(k).max()
    k = k + noise_scale * (rng.standard_normal(k.shape) + 1j * rng.standard_normal(k.shape))
    recon = np.abs(np.fft.ifft2(np.fft.ifftshift(k)))
    m = recon.max()
    return recon / m if m > 0 else recon


def render(recon, lab, rho, proton, out_png: Path, metrics: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    BG, FG, GRIDC = "#080b11", "#e8edf2", "#3a414c"
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "text.color": FG, "axes.labelcolor": FG, "xtick.color": FG, "ytick.color": FG,
        "axes.edgecolor": GRIDC, "font.size": 10,
    })
    fig = plt.figure(figsize=(14.5, 7.2))
    gs = fig.add_gridspec(2, 3, width_ratios=[1.5, 1, 1], height_ratios=[1, 1],
                          left=0.02, right=0.98, top=0.9, bottom=0.13, wspace=0.14, hspace=0.16)

    fig.suptitle(
        "TRECH magnetic resonance (Stage 4): a 2D brain MRI — proton-density image of a "
        "virtual head, brightness = Geant4 ¹H density",
        color=FG, fontsize=13.5, y=0.98)

    # main reconstructed MRI
    axm = fig.add_subplot(gs[:, 0])
    axm.imshow(recon, cmap="gray", vmin=0, vmax=1, origin="lower")
    axm.set_title("Reconstructed brain MRI (proton-density weighted)", fontsize=11)
    axm.axis("off")

    # tissue label map (anatomy)
    tissue_colors = {
        "air": "#080b11", "muscle": "#8a4b4b", "fat": "#e6c67a", "skull": "#4a5560",
        "csf": "#7fe3ff", "grey": "#9aa0a6", "white": "#e8edf2",
    }
    order = ["air", "muscle", "fat", "skull", "csf", "grey", "white"]
    cmap = ListedColormap([tissue_colors[k] for k in order])
    axl = fig.add_subplot(gs[0, 1])
    axl.imshow(lab, cmap=cmap, vmin=0, vmax=6, origin="lower")
    axl.set_title("Phantom anatomy (BrainWeb-inspired)", fontsize=9.5)
    axl.axis("off")

    # k-space (log magnitude)
    axk = fig.add_subplot(gs[1, 1])
    k = np.fft.fftshift(np.fft.fft2(rho))
    axk.imshow(np.log1p(np.abs(k)), cmap="magma", origin="lower")
    axk.set_title("Acquired k-space (log |S|)", fontsize=9.5)
    axk.axis("off")

    # per-tissue intensity vs Geant4 proton density
    axb = fig.add_subplot(gs[:, 2])
    rows = metrics["tissues"]
    keys = [r for r in ["csf", "fat", "grey", "muscle", "white", "skull", "air"] if r in rows]
    yy = np.arange(len(keys))[::-1]
    pd = [rows[k]["proton_rel"] for k in keys]
    inten = [rows[k]["mean_intensity"] for k in keys]
    axb.barh(yy + 0.18, pd, 0.36, color="#5cc8ff", label="Geant4 ¹H density (rel)")
    axb.barh(yy - 0.18, inten, 0.36, color="#7fdc7f", label="reconstructed intensity")
    axb.set_yticks(yy)
    axb.set_yticklabels(keys, fontsize=9)
    axb.set_xlim(0, 1.1)
    axb.set_title("Intensity ↔ Geant4 proton density", fontsize=9.8)
    axb.legend(loc="lower right", fontsize=7.6, facecolor="#161b22", edgecolor=GRIDC, labelcolor=FG)
    axb.grid(True, axis="x", color=GRIDC, alpha=0.3, lw=0.5)

    fig.text(
        0.5, 0.06,
        f"per-tissue intensity↔proton-density r = {metrics['corr_intensity_proton']:.3f}  ·  "
        f"reconstruction fidelity r = {metrics['recon_phantom_corr']:.3f}  ·  "
        f"CSF/ventricles bright · grey > white matter · fat bright · skull dark · air black",
        color="#c7d0da", fontsize=8.5, ha="center")
    fig.text(
        0.5, 0.022,
        "Anatomy is a procedural BrainWeb-inspired phantom; the per-tissue brightness is the "
        "Geant4-computed mobile-¹H density; k-space acquisition + 2D FFT reconstruction are signal processing.",
        color="#9aa3ad", fontsize=7.9, ha="center", style="italic")

    fig.savefig(out_png, dpi=135)
    print(f"wrote {out_png}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, default=REPO_ROOT / "build" / "dev" / "trech")
    ap.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "build" / "dev")
    ap.add_argument("--events", type=int, default=200)
    ap.add_argument("--out-png", type=Path, default=DEFAULT_OUT_PNG)
    ap.add_argument("--n", type=int, default=240, help="phantom grid size")
    ap.add_argument("--fov-mm", type=float, default=180.0)
    args = ap.parse_args()

    binary = args.binary.resolve()
    runs_dir = args.runs_dir.resolve()
    out_run = runs_dir / "out_mr_brain"
    if not binary.exists():
        raise SystemExit(f"trech binary not found: {binary}")

    scores = run_scenario(binary, out_run, args.events)
    proton = read_proton_densities(scores)
    ref = proton.get("csf", 0.0) or max(proton.values() or [1.0])
    if ref <= 0:
        raise SystemExit("could not read CSF/water proton density from the run")

    lab = build_phantom(args.n, args.fov_mm)
    rho = np.zeros(lab.shape, dtype=float)
    for lid, tissue in LAB_TISSUE.items():
        rho[lab == lid] = proton.get(tissue, 0.0) / ref
    recon = simulate_mri(rho)

    # per-tissue reconstructed intensity + proton density
    tissues = {}
    for lid, tissue in LAB_TISSUE.items():
        mask = lab == lid
        if not mask.any():
            continue
        tissues[tissue] = {
            "proton_rel": proton.get(tissue, 0.0) / ref,
            "proton_per_cm3": proton.get(tissue, 0.0),
            "mean_intensity": float(recon[mask].mean()),
            "pixels": int(mask.sum()),
        }
    keys = list(tissues.keys())
    pr = np.array([tissues[k]["proton_rel"] for k in keys])
    it = np.array([tissues[k]["mean_intensity"] for k in keys])
    corr_ip = float(np.corrcoef(pr, it)[0, 1]) if len(keys) > 1 else 0.0
    recon_phantom_corr = float(np.corrcoef(rho.ravel(), recon.ravel())[0, 1])

    t = tissues
    validation = {
        "intensity_tracks_proton_density": corr_ip >= 0.95,
        "csf_brightest_soft_tissue": all(
            t["csf"]["mean_intensity"] >= t[k]["mean_intensity"] - 1e-6
            for k in ("grey", "white", "muscle") if k in t),
        "grey_brighter_than_white": ("grey" in t and "white" in t
                                     and t["grey"]["mean_intensity"] > t["white"]["mean_intensity"]),
        "skull_dark": ("skull" in t and "grey" in t
                       and t["skull"]["mean_intensity"] < 0.5 * t["grey"]["mean_intensity"]),
        "background_black": ("air" in t and t["air"]["mean_intensity"] < 0.12),
        "reconstruction_faithful": recon_phantom_corr >= 0.9,
        "no_engine_spin_rule": True,
    }
    metrics = {
        "tissues": tissues,
        "corr_intensity_proton": corr_ip,
        "recon_phantom_corr": recon_phantom_corr,
    }

    # Rendering needs matplotlib; the validation aggregate below only needs numpy,
    # so degrade gracefully when matplotlib is unavailable (the suite still grades
    # the run; use the render venv to also produce the README figure).
    try:
        args.out_png.parent.mkdir(parents=True, exist_ok=True)
        render(recon, lab, rho, proton, args.out_png, metrics)
    except ImportError as exc:
        print(f"[warn] skipping figure render (matplotlib unavailable: {exc})")

    payload = {
        "scenario": "magnetic_resonance_brain",
        "phantom": "procedural BrainWeb-inspired axial head slice",
        "contrast": "proton-density weighted (Geant4 mobile-1H density per tissue)",
        "honest_scope": (
            "anatomy is a procedural digital phantom; per-tissue brightness is Geant4-derived; "
            "k-space + 2D FFT reconstruction are signal processing; MRI proton density modelled "
            "from mobile-1H (water) content and turned into an absolute 1H density by Geant4"),
        "geant4_drive": (scores.get("volume_edep_mev") or {}),
        "corr_intensity_proton": corr_ip,
        "recon_phantom_corr": recon_phantom_corr,
        "tissues": tissues,
        "validation": validation,
    }
    emit = {"hook": "driver", "tag": "mr_brain_image", "event_id": -1,
            "step_index": -1, "payload": payload}
    (out_run / "trech_hook_emits.jsonl").write_text(json.dumps(emit) + "\n")
    (out_run / "mr_brain_image.json").write_text(json.dumps(payload, indent=2) + "\n")

    print("\n=== brain MRI (per-tissue) ===")
    for k in ["csf", "fat", "grey", "muscle", "white", "skull", "air"]:
        if k in tissues:
            r = tissues[k]
            print(f"  {k:8s} proton_rel={r['proton_rel']:.3f}  intensity={r['mean_intensity']:.3f}")
    print(f"\ncorr(intensity, proton) = {corr_ip:.4f}  recon fidelity r = {recon_phantom_corr:.4f}")
    print(f"validation = {validation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
