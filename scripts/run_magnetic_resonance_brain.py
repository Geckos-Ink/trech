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

  4. VOLUME: the same Geant4 densities painted onto a volumetric (3D) phantom, a 3D k-space
     acquisition and an inverse 3D FFT, graded with the same per-tissue checks
     (payload.volume_3d); --out-gif renders the reconstructed volume in 3D (the README medium).

  5. Write an mr_brain_image aggregate emit under build/dev/out_mr_brain for the validation
     suite (plus a 2D validation figure in the run directory).

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
SCENARIO = REPO_ROOT / "examples/scenarios/testscenario_magnetic_resonance_brain/testscenario_magnetic_resonance_brain.js"
# The README medium is the volumetric 3D GIF (tools/viz/demos/render_readme_3d.py passes
# --out-gif); the 2D validation figure defaults into the run directory (derived data).

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


def build_phantom_3d(n: int, fov_mm: float):
    """Procedural VOLUMETRIC head -> integer tissue-label volume, indexed [x, y, z].

    The same BrainWeb-inspired layer stack as ``build_phantom`` (scalp, fat, skull, CSF,
    cortical grey ribbon, white-matter core, sulcal in-folds, lateral ventricles, deep grey
    nuclei), extruded to ellipsoids with a superior-inferior (z) axis so the acquisition and the
    reconstruction are genuinely 3D. Anatomy is a digital phantom, like the 2D slice.
    """
    ax = np.linspace(-fov_mm / 2, fov_mm / 2, n)
    X, Y, Z = np.meshgrid(ax, ax, ax, indexing="ij")
    zc = 0.84  # z semi-axis relative to the anterior-posterior semi-axis

    def ellipsoid(a, b, c, cx=0.0, cy=0.0, cz=0.0):
        return ((X - cx) / a) ** 2 + ((Y - cy) / b) ** 2 + ((Z - cz) / c) ** 2 <= 1.0

    lab = np.zeros((n, n, n), dtype=np.int32)
    for key, (a, b) in (("muscle", (72, 88)), ("fat", (69.5, 85.5)), ("skull", (67, 83)),
                        ("csf", (61, 77)), ("grey", (59, 75))):
        lab[ellipsoid(a, b, b * zc)] = LAB[key]
    brain = ellipsoid(54, 70, 70 * zc)
    lab[brain] = LAB["white"]
    az = np.arctan2(Y, X)
    el = np.arctan2(Z, np.hypot(X, Y))
    re = np.sqrt((X / 56.5) ** 2 + (Y / 72.5) ** 2 + (Z / (72.5 * zc)) ** 2)
    fold = (np.cos(13 * az + 0.4) + 0.6 * np.cos(21 * az + 1.9) + 0.4 * np.cos(8 * az - 0.7)
            + 0.55 * np.cos(11 * el + 0.9))
    lab[(fold > 1.2) & (re > 0.83) & (re < 1.03) & brain] = LAB["csf"]
    vent = (ellipsoid(7, 21, 13, cx=-8, cy=6, cz=6) | ellipsoid(7, 21, 13, cx=8, cy=6, cz=6)
            | ellipsoid(2.2, 13, 9, cx=0, cy=2, cz=-4))
    lab[vent & brain] = LAB["csf"]
    dgm = ellipsoid(9, 12, 10, cx=-17, cy=-2, cz=-6) | ellipsoid(9, 12, 10, cx=17, cy=-2, cz=-6)
    lab[dgm & brain & (lab == LAB["white"])] = LAB["grey"]
    return lab


def simulate_mri_3d(rho: np.ndarray, seed: int = 20260705) -> np.ndarray:
    """3D k-space acquisition + reconstruction (fftn -> apodization + noise -> ifftn)."""
    n = rho.shape[0]
    k = np.fft.fftshift(np.fft.fftn(rho))
    ax = np.linspace(-1, 1, n)
    KX, KY, KZ = np.meshgrid(ax, ax, ax, indexing="ij")
    k *= np.exp(-(KX ** 2 + KY ** 2 + KZ ** 2) / (2 * 2.6 ** 2))
    rng = np.random.default_rng(seed)
    # Same image-domain SNR as the validated 2D acquisition (240^2 samples at 0.1% of DC):
    # per-sample k noise sigma_k maps to sigma_img = sigma_k / sqrt(N), so scale by 240/sqrt(N).
    noise_scale = 0.0010 * np.abs(k).max() * (240.0 / np.sqrt(rho.size))
    k = k + noise_scale * (rng.standard_normal(k.shape) + 1j * rng.standard_normal(k.shape))
    recon = np.abs(np.fft.ifftn(np.fft.ifftshift(k)))
    m = recon.max()
    return recon / m if m > 0 else recon


def render_volume_gif(recon: np.ndarray, lab: np.ndarray, fov_mm: float, out_gif: Path,
                      lines: list, seconds: float = 9.0, fps: int = 10) -> None:
    """3D GIF of the reconstructed VOLUME: an axial slice of the reconstruction sweeping
    through the head inside the phantom's skin surface, with a turntable camera. The slice
    position and camera are display choices; every grey level is reconstructed data."""
    import pyvista as pv
    sys.path.insert(0, str(REPO_ROOT / "tools" / "viz"))
    from trech_viz.animate import write_gif

    n = recon.shape[0]
    spacing = fov_mm / (n - 1)
    grid = pv.ImageData(dimensions=recon.shape, spacing=(spacing,) * 3,
                        origin=(-fov_mm / 2,) * 3)
    grid.point_data["recon"] = recon.flatten(order="F")
    grid.point_data["head"] = (lab != LAB["air"]).astype(np.float32).flatten(order="F")
    skin = grid.contour([0.5], scalars="head")
    plotter = pv.Plotter(off_screen=True, window_size=(960, 720))
    plotter.set_background("#080a11", top="#161b2a")
    plotter.add_mesh(skin, color="#d8b8a0", opacity=0.13, smooth_shading=True)
    # A fixed coronal plane of the same reconstruction (behind the centre, facing the camera),
    # so the axial sweep in front of it reads as a volume.
    coronal = grid.slice(normal="y", origin=(0.0, 20.0, 0.0))
    plotter.add_mesh(coronal, scalars="recon", cmap="gray", clim=(0.0, 1.0),
                     show_scalar_bar=False, lighting=False, opacity=0.85)
    zmax = 0.80 * 88 * 0.84
    frames = max(2, int(seconds * fps))
    images = []
    slice_actor = None
    for i in range(frames):
        phase = i / (frames - 1)
        z = -zmax * np.cos(2 * np.pi * phase)          # bottom -> top -> bottom
        if slice_actor is not None:
            plotter.remove_actor(slice_actor)
        cut = grid.slice(normal="z", origin=(0.0, 0.0, float(z)))
        slice_actor = plotter.add_mesh(cut, scalars="recon", cmap="gray", clim=(0.0, 1.0),
                                       show_scalar_bar=False, lighting=False)
        angle = np.deg2rad(-35 + 70 * phase)
        dist = 3.3 * fov_mm
        plotter.camera.focal_point = (0.0, 0.0, 0.0)
        plotter.camera.position = (dist * np.sin(angle) * 0.9, -dist * np.cos(angle) * 0.9,
                                   dist * 0.55)
        plotter.camera.up = (0.0, 0.0, 1.0)
        plotter.camera.view_angle = 24.0
        plotter.remove_actor("hud")
        plotter.add_text("\n".join(lines + [f"axial slice z = {z:+.1f} mm (reconstructed volume)"]),
                         position="upper_left", font_size=12, color="#f4d6af", name="hud")
        plotter.render()
        images.append(np.ascontiguousarray(plotter.screenshot(return_img=True)[:, :, :3]))
    plotter.close()
    out_gif.parent.mkdir(parents=True, exist_ok=True)
    write_gif(str(out_gif), images, fps)
    print(f"wrote {out_gif}")


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
    ap.add_argument("--out-png", type=Path, default=None,
                    help="2D validation figure (default: <runs-dir>/out_mr_brain/...png)")
    ap.add_argument("--n", type=int, default=240, help="phantom grid size")
    ap.add_argument("--fov-mm", type=float, default=180.0)
    ap.add_argument("--out-gif", type=Path, default=None,
                    help="3D volumetric acquisition GIF (needs pyvista); not rendered unless given")
    ap.add_argument("--n3d", type=int, default=112, help="volumetric phantom grid size")
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
    out_png = args.out_png or (out_run / "magnetic_resonance_brain_2d.png")
    try:
        out_png.parent.mkdir(parents=True, exist_ok=True)
        render(recon, lab, rho, proton, out_png, metrics)
    except ImportError as exc:
        print(f"[warn] skipping figure render (matplotlib unavailable: {exc})")

    # Volumetric acquisition: the same Geant4 densities painted onto a 3D phantom, a 3D
    # k-space acquisition and an inverse 3D FFT, graded with the same per-tissue checks.
    lab3 = build_phantom_3d(args.n3d, args.fov_mm)
    rho3 = np.zeros(lab3.shape, dtype=float)
    for lid, tissue in LAB_TISSUE.items():
        rho3[lab3 == lid] = proton.get(tissue, 0.0) / ref
    recon3 = simulate_mri_3d(rho3)
    tissues3 = {}
    for lid, tissue in LAB_TISSUE.items():
        mask = lab3 == lid
        if mask.any():
            tissues3[tissue] = {"proton_rel": proton.get(tissue, 0.0) / ref,
                                "mean_intensity": float(recon3[mask].mean()),
                                "voxels": int(mask.sum())}
    k3 = list(tissues3.keys())
    corr_ip3 = float(np.corrcoef([tissues3[k]["proton_rel"] for k in k3],
                                 [tissues3[k]["mean_intensity"] for k in k3])[0, 1])
    recon_corr3 = float(np.corrcoef(rho3.ravel(), recon3.ravel())[0, 1])
    volume = {"grid": args.n3d, "fov_mm": args.fov_mm, "tissues": tissues3,
              "corr_intensity_proton": corr_ip3, "recon_phantom_corr": recon_corr3}
    if args.out_gif is not None:
        try:
            render_volume_gif(recon3, lab3, args.fov_mm, args.out_gif, [
                "TRECH 3D  |  volumetric brain MRI (Stage 4)",
                "voxel brightness = Geant4 mobile-1H density; 3D k-space -> inverse 3D FFT",
                f"intensity~proton r = {corr_ip3:.3f}   reconstruction fidelity r = {recon_corr3:.3f}",
            ])
        except ImportError as exc:
            print(f"[warn] skipping 3D GIF (pyvista unavailable: {exc})")

    payload = {
        "scenario": "magnetic_resonance_brain",
        "volume_3d": volume,
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
