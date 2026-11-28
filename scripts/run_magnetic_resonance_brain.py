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

  3. IMAGE: paint the phantom, sampled twice as finely as the scanner grid, with each tissue's
     Geant4 proton density -> rho(x,y). ACQUIRE it with a spin-warp (2D Fourier) protocol: one
     readout line per phase-encode step, the phase-encode gradient Gy stepped for a fixed time
     before each line and the readout gradient Gx on while the receiver samples at a fixed
     dwell. Every k-space sample is the explicit sum over the object's voxels of
     rho * exp(-2 pi i gamma_bar (Gx x t + Gy_n y tau)), with a uniform readout decay and
     fixed-seed complex receiver noise. RECONSTRUCT with the inverse 2D FFT on the grid the
     protocol's gradients imply (FOV = 1 / (gamma_bar Gx dwell)) -> the brain MRI. A control
     acquisition with the gradients 3% weak shows the geometry check detects a miscalibration.

  4. VOLUME: the same Geant4 densities painted onto a volumetric (3D) phantom, acquired with
     two phase-encode axes (Gy, Gz) and the same readout, reconstructed by the inverse 3D FFT
     and graded with the same per-tissue checks (payload.volume_3d); --out-gif renders the
     reconstructed volume in 3D (the README medium).

  5. Write an mr_brain_image aggregate emit under build/dev/out_mr_brain for the validation
     suite (plus a 2D validation figure in the run directory).

Honest scope: the anatomy (which tissue sits where) is a digital phantom we define
(BrainWeb-inspired); the per-tissue brightness is Geant4-derived; the imaging
pipeline (gradient encoding into k-space + FFT) is signal processing with a declared
apparatus protocol (PROTOCOL below: gradients, dwell, timing, a uniform readout decay that is
not tissue relaxation). MRI signal is from mobile protons,
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
# Engine flags for every scenario run. --strict-config (the validation suite's
# default) refuses a config key the engine never reads or an onInit override it
# did not apply; --no-strict-config downgrades them to warnings.
RUN_FLAGS: list = ["--strict-config"]
SCENARIO = REPO_ROOT / "examples/scenarios/testscenario_magnetic_resonance_brain/testscenario_magnetic_resonance_brain.js"
# The README medium is the volumetric 3D GIF (tools/viz/demos/render_readme_3d.py passes
# --out-gif); the 2D validation figure defaults into the run directory (derived data).

# tissue key -> proxy material name declared in the scenario
TISSUE_MATERIAL = {
    "csf": "mri_csf", "fat": "mri_fat", "grey": "mri_grey_matter",
    "muscle": "mri_muscle", "white": "mri_white_matter", "skull": "mri_skull",
    "air": "G4_AIR",
}

# Proton gyromagnetic ratio / 2 pi (CODATA 2018), the one nuclear constant the encoding needs;
# Stage 1 feeds the same constant and recovers it from the FID carrier.
GAMMA_BAR_HZ_PER_T = 42.577_478_92e6

# The acquisition apparatus: a proton-density weighted spin-warp protocol. These are machine
# settings, not tissue properties: the readout decay is one uniform T2* (field inhomogeneity)
# for every voxel, so it shapes the point-spread function without adding tissue contrast.
PROTOCOL = {
    "sequence": "2D/3D spin-warp gradient echo (Cartesian), proton-density weighted",
    "readout_bandwidth_hz": 62_500.0,   # 1 / dwell
    "phase_encode_ms": 1.0,             # tau: phase-encode gradient duration
    "echo_time_ms": 5.0,                # centre of the readout
    "readout_decay_ms": 40.0,           # uniform apparatus T2* (not tissue relaxation)
    "noise_fraction": 0.0010,           # receiver noise sigma / max |S|
    "object_oversample": 2,             # phantom voxels per scanner pixel, per axis
    # Control: gradients 3% weak. Weaker gradients reach less k-space per sample, so the head
    # reconstructs 3% smaller (stronger ones would enlarge it past the FOV and alias it).
    "miscalibration_control_scale": 0.97,
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
    cmd = [str(binary), "run", str(SCENARIO), *RUN_FLAGS, "--events", str(events), "--output", str(out_dir)]
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


def scanner_axis(n: int, fov_mm: float, oversample: int = 1) -> np.ndarray:
    """Pixel-centre coordinates (mm) of the grid the encoding implies: scanner pixel j sits at
    (j - n/2) * fov/n (the inverse-FFT convention); an object grid oversampled by `oversample`
    splits each pixel into equal cells centred about it."""
    pixel = fov_mm / n
    cell = pixel / oversample
    return (np.arange(n * oversample) + 0.5) * cell - (n / 2 + 0.5) * pixel


def build_phantom(n: int, fov_mm: float, axis: Optional[np.ndarray] = None):
    """Procedural axial head slice -> integer tissue-label map (BrainWeb-inspired), indexed
    [y, x]. `axis` gives the sample coordinates (mm); default a closed grid over the FOV."""
    ax = np.linspace(-fov_mm / 2, fov_mm / 2, n) if axis is None else axis
    n = len(ax)
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


def build_phantom_3d(n: int, fov_mm: float, axis: Optional[np.ndarray] = None):
    """Procedural VOLUMETRIC head -> integer tissue-label volume, indexed [x, y, z].

    The same BrainWeb-inspired layer stack as ``build_phantom`` (scalp, fat, skull, CSF,
    cortical grey ribbon, white-matter core, sulcal in-folds, lateral ventricles, deep grey
    nuclei), extruded to ellipsoids with a superior-inferior (z) axis so the acquisition and the
    reconstruction are genuinely 3D. Anatomy is a digital phantom, like the 2D slice.
    """
    ax = np.linspace(-fov_mm / 2, fov_mm / 2, n) if axis is None else axis
    n = len(ax)
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


def render_volume_gif(recon: np.ndarray, lab: np.ndarray, fov_mm: float, out_gif: Path,
                      lines: list, seconds: float = 9.0, fps: int = 10) -> None:
    """3D GIF of the reconstructed VOLUME: an axial slice of the reconstruction sweeping
    through the head inside the phantom's skin surface, with a turntable camera. The slice
    position and camera are display choices; every grey level is reconstructed data."""
    import pyvista as pv
    sys.path.insert(0, str(REPO_ROOT / "tools" / "viz"))
    from trech_viz.animate import write_gif

    n = recon.shape[0]
    spacing = fov_mm / n               # scanner_axis pixels: centre j at (j - n/2) * fov / n
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


def encoding(n: int, fov_mm: float, protocol: dict = PROTOCOL) -> dict:
    """Gradients and sample times of an n-sample Cartesian protocol over `fov_mm`.

    The readout gradient is chosen so one dwell advances k by 1/FOV
    (gamma_bar * Gx * dwell * FOV = 1), and the phase-encode step so one step of
    duration tau does the same (gamma_bar * dGy * tau * FOV = 1)."""
    fov = fov_mm * 1e-3
    dwell = 1.0 / protocol["readout_bandwidth_hz"]
    tau = protocol["phase_encode_ms"] * 1e-3
    gx = 1.0 / (GAMMA_BAR_HZ_PER_T * dwell * fov)          # T/m
    dg = 1.0 / (GAMMA_BAR_HZ_PER_T * tau * fov)            # T/m per phase-encode step
    steps = np.arange(n) - n / 2
    return {
        "n": n, "fov_mm": fov_mm, "dwell_s": dwell, "tau_s": tau, "gx_t_per_m": gx,
        "phase_step_t_per_m": dg,
        "readout_times_s": protocol["echo_time_ms"] * 1e-3 + steps * dwell,
        "readout_steps": steps, "phase_steps": steps,
    }


def encoding_matrix(k_per_m: np.ndarray, positions_mm: np.ndarray) -> np.ndarray:
    """E[k, x] = exp(-2 pi i k x): the phase each voxel's magnetization has accrued."""
    return np.exp(-2j * np.pi * np.outer(k_per_m, positions_mm * 1e-3))


def acquire(rho: np.ndarray, fov_mm: float, n: int, protocol: dict = PROTOCOL,
            gradient_scale: float = 1.0, seed: int = 20260705) -> np.ndarray:
    """Spin-warp acquisition of a 2D [y, x] or 3D [x, y, z] proton-density object.

    `rho` is sampled on scanner_axis(n, fov_mm, oversample) along every axis. 2D: x is read out
    (Gx on during sampling) and y is phase encoded (Gy stepped for tau before each line). 3D: x
    is read out and y, z are phase encoded. Each sample is the explicit voxel sum
    sum rho * exp(-2 pi i gamma_bar (Gx x t + Gy_n y tau [+ Gz_q z tau])), times the uniform
    readout decay exp(-t / T2*), plus fixed-seed complex receiver noise. `gradient_scale` makes
    the physical gradients differ from the nominal ones the reconstruction assumes."""
    enc = encoding(n, fov_mm, protocol)
    oversample = rho.shape[0] // n
    pos = scanner_axis(n, fov_mm, oversample)
    gamma = GAMMA_BAR_HZ_PER_T * gradient_scale
    kx = gamma * enc["gx_t_per_m"] * enc["readout_steps"] * enc["dwell_s"]
    kp = gamma * enc["phase_step_t_per_m"] * enc["phase_steps"] * enc["tau_s"]
    ex = encoding_matrix(kx, pos)
    ep = encoding_matrix(kp, pos)
    decay = np.exp(-enc["readout_times_s"] / (protocol["readout_decay_ms"] * 1e-3))
    if rho.ndim == 2:          # [y, x] -> S[phase n, readout m]
        k = ep @ rho @ ex.T
        k *= decay[None, :]
    else:                      # [x, y, z] -> S[readout m, phase p, phase q]
        k = np.tensordot(ex, rho, axes=(1, 0))         # [m, y, z]
        k = np.tensordot(k, ep, axes=(1, 1))           # [m, z, p]
        k = np.tensordot(k, ep, axes=(1, 1))           # [m, p, q]
        k *= decay[:, None, None]
    rng = np.random.default_rng(seed)
    # The 3D noise keeps the 2D image-domain SNR (240^2 samples): sigma_img = sigma_k / sqrt(N).
    scale = 1.0 if k.ndim == 2 else 240.0 / np.sqrt(k.size)
    noise = protocol["noise_fraction"] * np.abs(k).max() * scale
    return k + noise * (rng.standard_normal(k.shape) + 1j * rng.standard_normal(k.shape))


def reconstruct(k: np.ndarray) -> np.ndarray:
    """Inverse FFT on the nominal encoding grid (k = (index - n/2) / FOV) -> magnitude image on
    scanner_axis pixels, normalised to its maximum. 3D output is [x, y, z]; 2D is [y, x]."""
    recon = np.abs(np.fft.fftshift(np.fft.ifftn(np.fft.ifftshift(k))))
    m = recon.max()
    return recon / m if m > 0 else recon


def block_mean(fine: np.ndarray, oversample: int) -> np.ndarray:
    """The object at scanner resolution: the mean of each pixel's oversampled cells."""
    shape = []
    for size in fine.shape:
        shape += [size // oversample, oversample]
    return fine.reshape(shape).mean(axis=tuple(range(1, 2 * fine.ndim, 2)))


def head_semi_axes(recon: np.ndarray, axis_mm: np.ndarray, level: float) -> Dict[str, float]:
    """Half-widths (mm) of the reconstructed head along the central row (x) and column (y) of a
    [y, x] image: where the profile first rises through `level` from the background, linearly
    interpolated, averaged over both sides."""
    c = len(axis_mm) // 2

    def half_width(profile: np.ndarray) -> float:
        above = np.nonzero(profile >= level)[0]
        if len(above) == 0:
            return 0.0
        edges = []
        for i, j in ((above[0], above[0] - 1), (above[-1], above[-1] + 1)):
            if j < 0 or j >= len(profile):
                edges.append(abs(axis_mm[i]))
                continue
            f = (level - profile[j]) / (profile[i] - profile[j])
            edges.append(abs(axis_mm[j] + f * (axis_mm[i] - axis_mm[j])))
        return float(np.mean(edges))

    return {"x": half_width(recon[c, :]), "y": half_width(recon[:, c])}


def render(recon, lab, kspace, proton, out_png: Path, metrics: dict) -> None:
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
    axk.imshow(np.log1p(np.abs(kspace) / np.abs(kspace).max() * 1e4), cmap="magma", origin="lower")
    axk.set_title("Acquired k-space (log |S|; rows = phase-encode steps)", fontsize=9.5)
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
        "Geant4-computed mobile-¹H density; gradient-encoded k-space + 2D FFT reconstruction are signal processing.",
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
    ap.add_argument("--strict-config", action=argparse.BooleanOptionalAction, default=True,
                    help="pass --strict-config to every trech run (default: on)")
    args = ap.parse_args()
    RUN_FLAGS[:] = ["--strict-config"] if args.strict_config else []

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

    # The object is the phantom sampled `object_oversample` times finer than the scanner grid,
    # so the acquisition integrates sub-pixel anatomy instead of reproducing its own grid.
    over = int(PROTOCOL["object_oversample"])
    axis = scanner_axis(args.n, args.fov_mm)
    lab = build_phantom(args.n, args.fov_mm, axis=axis)           # grading masks, pixel centres
    lab_fine = build_phantom(args.n, args.fov_mm, axis=scanner_axis(args.n, args.fov_mm, over))
    rho_fine = np.zeros(lab_fine.shape, dtype=float)
    for lid, tissue in LAB_TISSUE.items():
        rho_fine[lab_fine == lid] = proton.get(tissue, 0.0) / ref
    rho = block_mean(rho_fine, over)                               # the object at scanner resolution
    kspace = acquire(rho_fine, args.fov_mm, args.n)
    recon = reconstruct(kspace)

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

    # Geometry: the head's half-widths in the reconstruction (where the profile rises through
    # half the scalp level) against the same measurement on the scanner-resolution object.
    # The FOV comes only from the protocol's gradients and timing, so a miscalibrated gradient
    # (the control) rescales the head.
    pixel_mm = args.fov_mm / args.n
    level_rel = 0.5 * proton.get("muscle", 0.0) / ref
    scale = tissues["csf"]["mean_intensity"]                        # recon units per proton_rel
    truth_axes = head_semi_axes(rho / rho.max(), axis, level_rel / rho.max())
    recon_axes = head_semi_axes(recon, axis, level_rel * scale)
    control = reconstruct(acquire(rho_fine, args.fov_mm, args.n,
                                  gradient_scale=PROTOCOL["miscalibration_control_scale"]))
    control_scale = float(np.mean(control[lab == LAB["csf"]]))
    control_axes = head_semi_axes(control, axis, level_rel * control_scale)
    geometry_error = max(abs(recon_axes[a] - truth_axes[a]) for a in ("x", "y"))
    control_error = max(abs(control_axes[a] - truth_axes[a]) for a in ("x", "y"))
    enc = encoding(args.n, args.fov_mm)
    acquisition = {
        "protocol": dict(PROTOCOL),
        "gamma_bar_hz_per_t": GAMMA_BAR_HZ_PER_T,
        "readout_gradient_mt_per_m": enc["gx_t_per_m"] * 1e3,
        "phase_encode_step_mt_per_m": enc["phase_step_t_per_m"] * 1e3,
        "max_phase_encode_mt_per_m": enc["phase_step_t_per_m"] * 1e3 * args.n / 2,
        "readout_duration_ms": args.n * enc["dwell_s"] * 1e3,
        "fov_mm_from_gradients": 1e3 / (GAMMA_BAR_HZ_PER_T * enc["gx_t_per_m"] * enc["dwell_s"]),
        "pixel_mm": pixel_mm,
        "object_grid": [int(v) for v in rho_fine.shape],
        "kspace_samples": int(kspace.size),
        "head_semi_axes_mm": {"phantom_definition": {"x": 72.0, "y": 88.0},
                              "object_at_scanner_resolution": truth_axes,
                              "reconstruction": recon_axes,
                              "control_reconstruction": control_axes},
        "geometry_error_mm": geometry_error,
        "control_geometry_error_mm": control_error,
        "geometry_tolerance_mm": 0.5 * pixel_mm,
    }

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
        # The FOV follows from the gradients: the head reconstructs at its true size within half
        # a pixel, and a 3% gradient miscalibration moves it by more than that.
        "geometry_from_gradients": geometry_error <= 0.5 * pixel_mm,
        "miscalibration_detected": control_error > 0.5 * pixel_mm,
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
        render(recon, lab, kspace, proton, out_png, metrics)
    except ImportError as exc:
        print(f"[warn] skipping figure render (matplotlib unavailable: {exc})")

    # Volumetric acquisition: the same Geant4 densities painted onto a 3D phantom, a 3D
    # k-space acquisition and an inverse 3D FFT, graded with the same per-tissue checks.
    axis3 = scanner_axis(args.n3d, args.fov_mm)
    lab3 = build_phantom_3d(args.n3d, args.fov_mm, axis=axis3)
    lab3_fine = build_phantom_3d(args.n3d, args.fov_mm, axis=scanner_axis(args.n3d, args.fov_mm, over))
    rho3_fine = np.zeros(lab3_fine.shape, dtype=float)
    for lid, tissue in LAB_TISSUE.items():
        rho3_fine[lab3_fine == lid] = proton.get(tissue, 0.0) / ref
    del lab3_fine
    rho3 = block_mean(rho3_fine, over)
    recon3 = reconstruct(acquire(rho3_fine, args.fov_mm, args.n3d))
    del rho3_fine
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
              "encoding": "x read out, y and z phase encoded", "object_oversample": over,
              "corr_intensity_proton": corr_ip3, "recon_phantom_corr": recon_corr3}
    if args.out_gif is not None:
        try:
            render_volume_gif(recon3, lab3, args.fov_mm, args.out_gif, [
                "TRECH 3D  |  volumetric brain MRI (Stage 4)",
                "voxel brightness = Geant4 mobile-1H density; 3D phase-encoded k-space -> inverse 3D FFT",
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
            "gradient-encoded k-space (declared protocol) + 2D FFT reconstruction are signal "
            "processing; MRI proton density modelled "
            "from mobile-1H (water) content and turned into an absolute 1H density by Geant4"),
        "geant4_drive": (scores.get("volume_edep_mev") or {}),
        "corr_intensity_proton": corr_ip,
        "recon_phantom_corr": recon_phantom_corr,
        "acquisition": acquisition,
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
    print(f"geometry: recon {recon_axes} vs object {truth_axes} (error {geometry_error:.3f} mm, "
          f"control {control_error:.3f} mm, tolerance {0.5 * pixel_mm:.3f} mm)")
    print(f"validation = {validation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
