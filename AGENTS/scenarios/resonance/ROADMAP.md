# Magnetic resonance and MRI — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Magnetic-resonance (MRI/NMR) track — standing objective

Build up a magnetic-resonance experiment the TRECH way: Geant4 + material physics supply
everything that is genuinely measurable, and the "know-what" (Larmor constant, tissue relaxation)
is used only to grade the gap-to-truth.

- **[Stage 1 landed 2026-07-04]** `examples/scenarios/testscenario_magnetic_resonance/testscenario_magnetic_resonance.js`: a
  5 cm³ water cube, a static-field + swept-RF apparatus, and detection of the free-induction-decay
  "output" signal. Geant4 builds the phantom + a copper receiver-coil volume and — through the new
  **material-composition engine surface** (`materialProbe`/`ctx.materials`, `MaterialProbe.{hpp,cpp}`)
  — supplies the ¹H (proton) number density that sets the equilibrium magnetization; the deterministic
  hook layer runs the Bloch spin dynamics. The Larmor line is **discovered** from the FID carrier
  (feeding only the proton gyromagnetic ratio γ + the machine field B0 — no water-specific know-what):
  γ/2π recovered **42.5768 MHz/T** vs CODATA 42.5775 (0.001%), Geant4 water proton density
  **6.686e22/cm³** = literature (0.006%), T2* recovered to 0.1%. Guarded by `magnetic_resonance_water`
  (category `resonance`, 7/7, incl. a `material_probes`↔`ctx.materials` cross-check). Honest scope:
  Geant4 does not simulate nuclear spin — the spin dynamics are the hook-layer physics-for-comparison.
- **[Stage 2 landed 2026-07-04]** virtual tissues with **REAL Geant4 photon emission** (no C++):
  shared scenario `testscenario_magnetic_resonance_tissues.js` + multi-run driver
  `scripts/run_magnetic_resonance_tissues.py`. Per NIST tissue the driver reads the Geant4-computed
  ¹H number density (`material_probes` — an ignorant material fact) and emits a **proportional** number
  of excitation primaries; Geant4 then produces **every consequent photon** and a NaI detector shell
  scores the REAL deposited energy (`receiver_coil volume_edep_mev`). The detected per-tissue signal is
  a genuine Monte-Carlo tally whose emission count came from Geant4's own proton prediction, and it
  reproduces MRI proton-density contrast — cortical bone **0.60× water** (proton ratio 0.583; the gap is
  the radiographic photon-yield term), corr(signal, proton density) **0.9995**, byte-reproducible.
  Guarded by `magnetic_resonance_tissue_contrast` (5/5). Honest scope: the excitation-per-proton is a
  labelled proxy (Geant4 can't make nuclear spins radiate RF); REAL = the Geant4-set emission count +
  the Geant4-transport detection tally.
- **[Stage 3 landed 2026-07-05]** spatial encoding → an **actual 1D image line** (no C++):
  `examples/scenarios/testscenario_magnetic_resonance_imaging/testscenario_magnetic_resonance_imaging.js`. Geant4 builds a real
  multi-tissue phantom (a row of NIST-tissue voxels along the readout axis, incl. an **air gap** →
  black and **cortical bone** → dark) with real transport, and supplies each voxel's ¹H density via
  `ctx.materials`. The hook layer applies a readout gradient (`ω(x)=γ(B0+Gx·x)`), synthesizes the
  quadrature readout and **DFT-reconstructs the proton-density profile**: positions recovered from
  peak frequency to **0.001 mm**, amplitude↔proton corr **1.0**, air gap 0.01 (black) / cortical bone
  0.59 (dark) — a recognizable image, byte-reproducible. Guarded by `magnetic_resonance_image_line`
  (6/6).
- **[Stage 4 landed 2026-07-05]** a full **2D brain MRI image** (no C++):
  `examples/scenarios/testscenario_magnetic_resonance_brain/testscenario_magnetic_resonance_brain.js` + `scripts/run_magnetic_resonance_brain.py`.
  A procedural, [BrainWeb](https://brainweb.bic.mni.mcgill.ca/brainweb/anatomic_normal_20.html)-inspired
  axial head phantom (skull, scalp/fat, CSF, cortical grey-matter ribbon, white-matter core, lateral
  ventricles, deep grey nuclei) supplies the anatomy; **each pixel's brightness is the Geant4-computed
  mobile-¹H (proton) density** of its tissue (declared as water-content proxy materials, so Geant4
  turns the biological water fraction into an absolute ¹H number density); a 2D k-space acquisition +
  FFT reconstruct the image. Result: a genuine proton-density MRI — bright CSF/ventricles, grey > white
  matter, bright fat, dark skull, black background — with per-tissue intensity↔proton-density
  **r = 0.998** and reconstruction fidelity **r = 0.966**, byte-reproducible. Rendered
  `tools/viz/demos/magnetic_resonance_brain.png` (README hero). Guarded by
  `magnetic_resonance_brain_image` (7/7). Honest scope: the anatomy is a digital phantom and the
  k-space/FFT is signal processing; the contrast is Geant4-derived.
- **[optional future]** T1/T2-weighted sequences (relaxation contrast, needs a Geant4-anchored
  relaxation proxy), 2-D phase encoding from acquired k-space, and real BrainWeb data ingestion remain
  open MRI extensions.
